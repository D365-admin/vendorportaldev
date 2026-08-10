from __future__ import annotations

import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

import pyodbc
from jose import jwt

from app.core.config import settings
from app.db.base import (
    get_connection,
    get_secondary_connection,
)


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

# Cloud / primary database schema.
PRIMARY_SCHEMA = settings.DB_SCHEMA

# Secondary database schema.
SECONDARY_SCHEMA = getattr(
    settings,
    "SECONDARY_DB_SCHEMA",
    settings.DB_SCHEMA,
)

# Prospect and registration data are stored only in secondary DB.
PROSPECT_TABLE = (
    f"[{SECONDARY_SCHEMA}].[d365_VendorProspect]"
)

REGISTRATION_TABLE = (
    f"[{SECONDARY_SCHEMA}].[HIQ_VendorRegistration]"
)

# OTP remains in cloud / primary DB.
OTP_TABLE = (
    f"[{PRIMARY_SCHEMA}].[HIQ_VendorOTP]"
)


# ============================================================
# EXCEPTIONS
# ============================================================

class VendorNotFoundError(LookupError):
    pass


class DuplicateVendorEmailError(ValueError):
    pass


class OtpValidationError(ValueError):
    pass


# ============================================================
# COMMON HELPERS
# ============================================================

def _clean_email(
    email: str,
) -> str:
    """
    Normalize an email address before using it in a query.
    """

    value = str(
        email or ""
    ).strip().lower()

    if not value:
        raise ValueError(
            "EMAIL is required"
        )

    if len(value) > 255:
        raise ValueError(
            "EMAIL cannot exceed 255 characters"
        )

    return value


def _fetch_one(
    cursor: pyodbc.Cursor,
) -> dict[str, Any]:
    """
    Convert the current cursor row into a dictionary.
    """

    row = cursor.fetchone()

    if row is None:
        return {}

    if not cursor.description:
        return {}

    columns = [
        column[0]
        for column in cursor.description
    ]

    return dict(
        zip(
            columns,
            row,
        )
    )


def _normalize_prospect_id(
    value: Any,
) -> str:
    """
    Normalize ProspectId before returning it or using it in a query.
    """

    prospect_id = str(
        value or ""
    ).strip().upper()

    if not prospect_id:
        raise VendorNotFoundError(
            "The vendor prospect does not have a valid ProspectId"
        )

    return prospect_id


def _generate_otp() -> str:
    """
    Generate a cryptographically secure six-digit OTP.
    """

    return str(
        secrets.randbelow(900000)
        + 100000
    )


# ============================================================
# SECONDARY DATABASE HELPERS
# ============================================================

def _fetch_vendor_by_email(
    cursor: pyodbc.Cursor,
    email: str,
) -> dict[str, Any]:
    """
    Fetch vendor prospect information from the secondary database only.
    """

    cursor.execute(
        f"""
        SELECT
            ProspectSeq,
            ProspectId,
            VendorAccount,
            Name,
            Email,
            VendGroup
        FROM {PROSPECT_TABLE}
        WHERE LOWER(
            LTRIM(
                RTRIM(Email)
            )
        ) = ?
        ORDER BY ProspectSeq DESC
        """,
        email,
    )

    rows = cursor.fetchall()

    if not rows:
        raise VendorNotFoundError(
            "No vendor prospect was found for this email"
        )

    if len(rows) > 1:
        raise DuplicateVendorEmailError(
            "Multiple vendor prospects are mapped to this email. "
            "Please contact the administrator."
        )

    columns = [
        column[0]
        for column in cursor.description
    ]

    return dict(
        zip(
            columns,
            rows[0],
        )
    )


def _fetch_vendor_registration_state(
    cursor: pyodbc.Cursor,
    prospect_id: str,
) -> dict[str, Any]:
    """
    Fetch vendor onboarding status from the secondary database only.

    The invitation process must create HIQ_VendorRegistration first.
    """

    cursor.execute(
        f"""
        SELECT TOP 1
            IsDraft,
            Status
        FROM {REGISTRATION_TABLE}
        WHERE ProspectId = ?
        """,
        prospect_id,
    )

    registration = _fetch_one(
        cursor
    )

    if not registration:
        raise VendorNotFoundError(
            "Vendor invitation registration was not found for "
            f"ProspectId {prospect_id}. Send the invitation first."
        )

    status_value = str(
        registration.get("Status")
        or "INVITED"
    ).strip().upper()

    return {
        "ISDRAFT": int(
            registration.get("IsDraft")
            or 0
        ),
        "STATUS": status_value,
    }


def _fetch_vendor_login_context(
    email: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    """
    Fetch prospect and registration state from the secondary DB.

    No OTP data is read here.
    """

    with get_connection()as connection:
        cursor = connection.cursor()

        try:
            vendor = _fetch_vendor_by_email(
                cursor=cursor,
                email=email,
            )

            prospect_id = _normalize_prospect_id(
                vendor.get("ProspectId")
            )

            registration_state = (
                _fetch_vendor_registration_state(
                    cursor=cursor,
                    prospect_id=prospect_id,
                )
            )

            return (
                vendor,
                registration_state,
            )

        finally:
            cursor.close()


# ============================================================
# JWT
# ============================================================

def _create_access_token(
    vendor: dict[str, Any],
) -> tuple[str, datetime]:
    """
    Create a JWT using vendor information fetched from the secondary DB.
    """

    current_time = datetime.now(
        timezone.utc
    )

    expires_at = (
        current_time
        + timedelta(
            minutes=settings.JWT_EXPIRE_MINUTES
        )
    )

    prospect_id = _normalize_prospect_id(
        vendor.get("ProspectId")
    )

    token_payload = {
        "sub": prospect_id,
        "prospect_seq": int(
            vendor["ProspectSeq"]
        ),
        "prospect_id": prospect_id,
        "vendor_account": vendor.get(
            "VendorAccount"
        ),
        "name": vendor.get(
            "Name"
        ),
        "email": vendor.get(
            "Email"
        ),
        "token_type": "access",
        "iat": current_time,
        "exp": expires_at,
    }

    access_token = jwt.encode(
        token_payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return (
        access_token,
        expires_at,
    )


# ============================================================
# EMAIL
# ============================================================

def _send_otp_email(
    recipient_email: str,
    otp: str,
) -> None:
    """
    Send the OTP through the configured SMTP server.
    """

    sender_email = (
        getattr(
            settings,
            "MAIL_FROM",
            None,
        )
        or settings.MAIL_USERNAME
    )

    message = EmailMessage()

    message["Subject"] = (
        "Vendor Portal Login OTP"
    )

    message["From"] = (
        f"Vendor Onboarding Team "
        f"<{sender_email}>"
    )

    message["To"] = recipient_email

    message.set_content(
        f"""
Hello,

Your Vendor Onboarding Portal login OTP is:

{otp}

This OTP is valid for {settings.OTP_EXPIRE_MINUTES} minutes.

Please do not share this OTP with anyone.

Regards,
Vendor Onboarding Team
""".strip()
    )

    with smtplib.SMTP(
        settings.MAIL_SERVER,
        settings.MAIL_PORT,
        timeout=30,
    ) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()

        smtp.login(
            settings.MAIL_USERNAME,
            settings.MAIL_PASSWORD,
        )

        smtp.send_message(
            message
        )


# ============================================================
# REQUEST OTP
# ============================================================

def request_vendor_otp(
    email: str,
) -> dict[str, Any]:
    """
    Request OTP workflow:

    1. Fetch prospect and registration from secondary DB.
    2. Store OTP in cloud/primary DB.
    3. Send OTP through SMTP.
    """

    normalized_email = _clean_email(
        email
    )

    # Read vendor and registration from secondary DB.
    vendor, registration_state = (
        _fetch_vendor_login_context(
            email=normalized_email
        )
    )

    prospect_seq = int(
        vendor["ProspectSeq"]
    )

    prospect_id = _normalize_prospect_id(
        vendor.get("ProspectId")
    )

    otp = _generate_otp()

    # OTP operations use cloud/primary DB only.
    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            # Lock the latest OTP row for this prospect sequence.
            # SecondsPassed is calculated inside SQL Server so Python
            # and SQL Server timezone differences cannot affect it.
            cursor.execute(
                f"""
                SELECT TOP 1
                    ID,
                    CREATEDDATETIME,
                    DATEDIFF
                    (
                        SECOND,
                        CREATEDDATETIME,
                        SYSUTCDATETIME()
                    ) AS SecondsPassed
                FROM {OTP_TABLE}
                WITH
                (
                    UPDLOCK,
                    HOLDLOCK
                )
                WHERE USERID = ?
                ORDER BY ID DESC
                """,
                prospect_seq,
            )

            recent_otp = cursor.fetchone()

            if recent_otp is not None:
                seconds_passed = max(
                    int(
                        recent_otp[2]
                        or 0
                    ),
                    0,
                )

                if seconds_passed < 60:
                    remaining_seconds = max(
                        60 - seconds_passed,
                        1,
                    )

                    raise OtpValidationError(
                        "Please wait "
                        f"{remaining_seconds} seconds "
                        "before requesting another OTP"
                    )

            # Invalidate every previous unused OTP.
            cursor.execute(
                f"""
                UPDATE {OTP_TABLE}
                SET
                    ISUSED = 1,
                    MODIFIEDDATETIME =
                        SYSUTCDATETIME(),
                    MODIFIEDBY = 'PORTAL',
                    RECVERSION =
                        ISNULL(RECVERSION, 0) + 1
                WHERE USERID = ?
                  AND ISUSED = 0
                """,
                prospect_seq,
            )

            # USERID currently stores ProspectSeq.
            cursor.execute(
                f"""
                INSERT INTO {OTP_TABLE}
                (
                    OTPCODE,
                    USERID,
                    ISUSED,
                    ATTEMPTS,
                    EXPIRESAT,
                    RECVERSION,
                    CREATEDDATETIME,
                    CREATEDBY,
                    MODIFIEDDATETIME,
                    MODIFIEDBY
                )
                VALUES
                (
                    ?,
                    ?,
                    0,
                    0,
                    DATEADD
                    (
                        MINUTE,
                        ?,
                        SYSUTCDATETIME()
                    ),
                    1,
                    SYSUTCDATETIME(),
                    'PORTAL',
                    NULL,
                    NULL
                )
                """,
                otp,
                prospect_seq,
                settings.OTP_EXPIRE_MINUTES,
            )

            # Send to the normalized email already verified
            # against secondary d365_VendorProspect.
            _send_otp_email(
                recipient_email=normalized_email,
                otp=otp,
            )

            connection.commit()

            return {
                "SUCCESS": True,
                "MESSAGE": (
                    "OTP sent successfully to the "
                    "registered email address"
                ),
                "EMAIL": normalized_email,
                "PROSPECT_ID": prospect_id,
                "ISDRAFT": registration_state[
                    "ISDRAFT"
                ],
                "STATUS": registration_state[
                    "STATUS"
                ],
                "OTP_EXPIRES_IN_SECONDS": (
                    settings.OTP_EXPIRE_MINUTES
                    * 60
                ),
            }

        except Exception:
            connection.rollback()
            raise

        finally:
            cursor.close()


# ============================================================
# VERIFY OTP
# ============================================================

def verify_vendor_otp(
    email: str,
    otp: str,
) -> dict[str, Any]:
    """
    Verify OTP workflow:

    1. Fetch prospect and registration from secondary DB.
    2. Verify OTP in cloud/primary DB.
    3. Create JWT using secondary prospect data.
    """

    normalized_email = _clean_email(
        email
    )

    submitted_otp = str(
        otp or ""
    ).strip()

    if (
        len(submitted_otp) != 6
        or not submitted_otp.isdigit()
    ):
        raise OtpValidationError(
            "OTP must contain exactly six digits"
        )

    # Read vendor and registration from secondary DB.
    vendor, registration_state = (
        _fetch_vendor_login_context(
            email=normalized_email
        )
    )

    prospect_seq = int(
        vendor["ProspectSeq"]
    )

    prospect_id = _normalize_prospect_id(
        vendor.get("ProspectId")
    )

    # Verify OTP in cloud/primary DB only.
    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT TOP 1
                    ID,
                    OTPCODE,
                    ISUSED,
                    ATTEMPTS,
                    EXPIRESAT,
                    CASE
                        WHEN EXPIRESAT <
                             SYSUTCDATETIME()
                        THEN 1
                        ELSE 0
                    END AS IsExpired
                FROM {OTP_TABLE}
                WITH
                (
                    UPDLOCK,
                    ROWLOCK
                )
                WHERE USERID = ?
                ORDER BY ID DESC
                """,
                prospect_seq,
            )

            otp_row = cursor.fetchone()

            if otp_row is None:
                raise OtpValidationError(
                    "OTP was not requested"
                )

            otp_id = int(
                otp_row[0]
            )

            stored_otp = str(
                otp_row[1]
                or ""
            ).strip()

            is_used = bool(
                otp_row[2]
            )

            attempts = int(
                otp_row[3]
                or 0
            )

            is_expired = bool(
                otp_row[5]
            )

            if is_used:
                raise OtpValidationError(
                    "OTP has already been used"
                )

            if attempts >= settings.OTP_MAX_ATTEMPTS:
                cursor.execute(
                    f"""
                    UPDATE {OTP_TABLE}
                    SET
                        ISUSED = 1,
                        MODIFIEDDATETIME =
                            SYSUTCDATETIME(),
                        MODIFIEDBY = 'PORTAL',
                        RECVERSION =
                            ISNULL(RECVERSION, 0) + 1
                    WHERE ID = ?
                    """,
                    otp_id,
                )

                connection.commit()

                raise OtpValidationError(
                    "Maximum OTP attempts exceeded"
                )

            if is_expired:
                cursor.execute(
                    f"""
                    UPDATE {OTP_TABLE}
                    SET
                        ISUSED = 1,
                        MODIFIEDDATETIME =
                            SYSUTCDATETIME(),
                        MODIFIEDBY = 'PORTAL',
                        RECVERSION =
                            ISNULL(RECVERSION, 0) + 1
                    WHERE ID = ?
                    """,
                    otp_id,
                )

                connection.commit()

                raise OtpValidationError(
                    "OTP has expired"
                )

            if stored_otp != submitted_otp:
                new_attempts = attempts + 1

                cursor.execute(
                    f"""
                    UPDATE {OTP_TABLE}
                    SET
                        ATTEMPTS = ?,

                        ISUSED =
                            CASE
                                WHEN ? >= ?
                                THEN 1
                                ELSE 0
                            END,

                        MODIFIEDDATETIME =
                            SYSUTCDATETIME(),

                        MODIFIEDBY = 'PORTAL',

                        RECVERSION =
                            ISNULL(RECVERSION, 0) + 1

                    WHERE ID = ?
                    """,
                    new_attempts,
                    new_attempts,
                    settings.OTP_MAX_ATTEMPTS,
                    otp_id,
                )

                connection.commit()

                remaining_attempts = max(
                    settings.OTP_MAX_ATTEMPTS
                    - new_attempts,
                    0,
                )

                raise OtpValidationError(
                    "Invalid OTP. "
                    f"{remaining_attempts} attempts remaining."
                )

            # OTP is correct. Mark it as used.
            cursor.execute(
                f"""
                UPDATE {OTP_TABLE}
                SET
                    ISUSED = 1,
                    MODIFIEDDATETIME =
                        SYSUTCDATETIME(),
                    MODIFIEDBY = 'PORTAL',
                    RECVERSION =
                        ISNULL(RECVERSION, 0) + 1
                WHERE ID = ?
                  AND ISUSED = 0
                """,
                otp_id,
            )

            if cursor.rowcount != 1:
                raise OtpValidationError(
                    "OTP could not be used. Please request a new OTP."
                )

            access_token, expires_at = (
                _create_access_token(
                    vendor=vendor
                )
            )

            connection.commit()

            return {
                "SUCCESS": True,
                "MESSAGE": (
                    "OTP verified successfully"
                ),
                "ACCESS_TOKEN": access_token,
                "TOKEN_TYPE": "bearer",
                "EXPIRES_AT": (
                    expires_at.isoformat()
                ),
                "ISDRAFT": registration_state[
                    "ISDRAFT"
                ],
                "STATUS": registration_state[
                    "STATUS"
                ],
                "VENDOR": {
                    "PROSPECT_SEQ": vendor.get(
                        "ProspectSeq"
                    ),
                    "PROSPECT_ID": prospect_id,
                    "VENDOR_ACCOUNT": vendor.get(
                        "VendorAccount"
                    ),
                    "NAME": vendor.get(
                        "Name"
                    ),
                    "EMAIL": vendor.get(
                        "Email"
                    ),
                
                    "VEND_GROUP": vendor.get(
                        "VendGroup"
                    ),
                },
            }

        except OtpValidationError:
            # Validation branches that update OTP state commit
            # their changes before raising.
            raise

        except Exception:
            connection.rollback()
            raise

        finally:
            cursor.close()



# from __future__ import annotations

# import secrets
# import smtplib
# from datetime import datetime, timedelta, timezone
# from email.message import EmailMessage
# from typing import Any

# import pyodbc
# from jose import jwt

# from app.core.config import settings
# from app.db.base import get_connection


# DB_SCHEMA = settings.DB_SCHEMA

# PROSPECT_TABLE = (
#     f"[{DB_SCHEMA}].[d365_VendorProspect]"
# )

# OTP_TABLE = (
#     f"[{DB_SCHEMA}].[HIQ_VendorOTP]"
# )
# REGISTRATION_TABLE = (
#     f"[{DB_SCHEMA}].[HIQ_VendorRegistration]"
# )

# # ============================================================
# # EXCEPTIONS
# # ============================================================

# class VendorNotFoundError(LookupError):
#     pass


# class DuplicateVendorEmailError(ValueError):
#     pass


# class OtpValidationError(ValueError):
#     pass


# # ============================================================
# # COMMON HELPERS
# # ============================================================

# def _clean_email(
#     email: str,
# ) -> str:

#     value = (
#         email or ""
#     ).strip().lower()

#     if not value:
#         raise ValueError(
#             "EMAIL is required"
#         )

#     return value


# def _fetch_vendor_by_email(
#     cursor: pyodbc.Cursor,
#     email: str,
# ) -> dict[str, Any]:

#     cursor.execute(
#         f"""
#         SELECT
#             ProspectSeq,
#             ProspectId,
#             VendorAccount,
#             Name,
#             Currency,
#             Email,
#             VendGroup
#         FROM {PROSPECT_TABLE}
#         WHERE LOWER(
#             LTRIM(
#                 RTRIM(Email)
#             )
#         ) = ?
#         ORDER BY ProspectSeq DESC
#         """,
#         email,
#     )

#     rows = cursor.fetchall()

#     if not rows:
#         raise VendorNotFoundError(
#             "No vendor prospect was found for this email"
#         )

#     if len(rows) > 1:
#         raise DuplicateVendorEmailError(
#             "Multiple vendor prospects are mapped to this "
#             "email. Please contact the administrator."
#         )

#     columns = [
#         description[0]
#         for description in cursor.description
#     ]

#     return dict(
#         zip(
#             columns,
#             rows[0],
#         )
#     )


# def _generate_otp() -> str:
#     """
#     Generates a six-digit OTP from 100000 to 999999.
#     """

#     return str(
#         secrets.randbelow(
#             900000
#         )
#         + 100000
#     )


# # ============================================================
# # JWT
# # ============================================================

# def _create_access_token(
#     vendor: dict[str, Any],
# ) -> tuple[str, datetime]:

#     current_time = datetime.now(
#         timezone.utc
#     )

#     expires_at = (
#         current_time
#         + timedelta(
#             minutes=(
#                 settings
#                 .JWT_EXPIRE_MINUTES
#             )
#         )
#     )

#     token_payload = {
#         "sub": str(
#             vendor["ProspectId"]
#         ),
#         "prospect_seq": int(
#             vendor["ProspectSeq"]
#         ),
#         "prospect_id": (
#             vendor.get(
#                 "ProspectId"
#             )
#         ),
#         "vendor_account": (
#             vendor.get(
#                 "VendorAccount"
#             )
#         ),
#         "name": vendor.get(
#             "Name"
#         ),
#         "email": vendor.get(
#             "Email"
#         ),
#         "token_type": "access",
#         "iat": current_time,
#         "exp": expires_at,
#     }

#     access_token = jwt.encode(
#         token_payload,
#         settings.JWT_SECRET_KEY,
#         algorithm=(
#             settings.JWT_ALGORITHM
#         ),
#     )

#     return (
#         access_token,
#         expires_at,
#     )


# # ============================================================
# # EMAIL
# # ============================================================

# def _send_otp_email(
#     recipient_email: str,
#     otp: str,
# ) -> None:

#     message = EmailMessage()

#     message["Subject"] = (
#         "Vendor Portal Login OTP"
#     )

#     message["From"] = (
#         f"{settings.MAIL_USERNAME} "
#         f"<{settings.MAIL_FROM}>"
#     )

#     message["To"] = recipient_email

#     message.set_content(
#         f"""
# Hello,

# Your Vendor Onboarding Portal login OTP is:

# {otp}

# This OTP is valid for {settings.OTP_EXPIRE_MINUTES} minutes.

# Please do not share this OTP with anyone.

# Regards,
# Vendor Onboarding Team
# """.strip()
#     )

#     with smtplib.SMTP(
#         settings.MAIL_SERVER,
#         settings.MAIL_PORT,
#         timeout=30,
#     ) as smtp:

#         smtp.ehlo()
#         smtp.starttls()
#         smtp.ehlo()

#         smtp.login(
#             settings.MAIL_USERNAME,
#             settings.MAIL_PASSWORD,
#         )

#         smtp.send_message(
#             message
#         )


# # ============================================================
# # REQUEST OTP
# # ============================================================

# def request_vendor_otp(
#     email: str,
# ) -> dict[str, Any]:

#     normalized_email = (
#         _clean_email(email)
#     )

#     otp = _generate_otp()

#     with get_connection() as connection:
#         cursor = connection.cursor()

#         try:
#             vendor = _fetch_vendor_by_email(
#                 cursor=cursor,
#                 email=normalized_email,
#             )

#             prospect_seq = int(
#                 vendor["ProspectSeq"]
#             )

#             # Prevent requesting another OTP within 60 seconds.
#             cursor.execute(
#                 f"""
#                 SELECT TOP 1
#                     CREATEDDATETIME
#                 FROM {OTP_TABLE}
#                 WHERE USERID = ?
#                 ORDER BY ID DESC
#                 """,
#                 prospect_seq,
#             )

#             recent_otp = cursor.fetchone()

#             if (
#                 recent_otp is not None
#                 and recent_otp[0] is not None
#             ):
#                 created_datetime = (
#                     recent_otp[0]
#                 )

#                 seconds_passed = (
#                     datetime.now()
#                     - created_datetime
#                 ).total_seconds()

#                 if seconds_passed < 60:
#                     remaining_seconds = int(
#                         60 - seconds_passed
#                     )

#                     raise OtpValidationError(
#                         "Please wait "
#                         f"{remaining_seconds} seconds "
#                         "before requesting another OTP"
#                     )

#             # Mark all previous unused OTPs as used.
#             cursor.execute(
#                 f"""
#                 UPDATE {OTP_TABLE}
#                 SET
#                     ISUSED = 1,
#                     MODIFIEDDATETIME = GETDATE(),
#                     MODIFIEDBY = 'PORTAL',
#                     RECVERSION =
#                         ISNULL(RECVERSION, 0) + 1
#                 WHERE USERID = ?
#                   AND ISUSED = 0
#                 """,
#                 prospect_seq,
#             )

#             # Store the OTP directly without hashing.
#             cursor.execute(
#                 f"""
#                 INSERT INTO {OTP_TABLE}
#                 (
#                     OTPCODE,
#                     USERID,
#                     ISUSED,
#                     ATTEMPTS,
#                     EXPIRESAT,
#                     RECVERSION,
#                     CREATEDDATETIME,
#                     CREATEDBY,
#                     MODIFIEDDATETIME,
#                     MODIFIEDBY
#                 )
#                 VALUES
#                 (
#                     ?,
#                     ?,
#                     0,
#                     0,
#                     DATEADD(
#                         MINUTE,
#                         ?,
#                         GETDATE()
#                     ),
#                     1,
#                     GETDATE(),
#                     'PORTAL',
#                     NULL,
#                     NULL
#                 )
#                 """,
#                 otp,
#                 prospect_seq,
#                 settings.OTP_EXPIRE_MINUTES,
#             )

#             # Send OTP to the registered email.
#             _send_otp_email(
#                 recipient_email=(
#                     normalized_email
#                 ),
#                 otp=otp,
#             )

#             connection.commit()

#             return {
#                 "SUCCESS": True,
#                 "MESSAGE": (
#                     "OTP sent successfully to the "
#                     "registered email address"
#                 ),
#                 "EMAIL": normalized_email,
#                 "OTP_EXPIRES_IN_SECONDS": (
#                     settings.OTP_EXPIRE_MINUTES
#                     * 60
#                 ),
#             }

#         except Exception:
#             connection.rollback()
#             raise


# # ============================================================
# # VERIFY OTP
# # ============================================================
# def _fetch_vendor_registration_state(
#     cursor: pyodbc.Cursor,
#     prospect_id: str,
# ) -> dict[str, Any]:
#     """
#     Fetch onboarding IsDraft and Status for the vendor.

#     When no registration row exists yet, return the
#     default onboarding state.
#     """

#     cursor.execute(
#         f"""
#         SELECT TOP 1
#             IsDraft,
#             Status
#         FROM {REGISTRATION_TABLE}
#         WHERE ProspectId = ?
#         """,
#         prospect_id,
#     )

#     row = cursor.fetchone()

#     if row is None:
#         return {
#             "ISDRAFT": 0,
#             "STATUS": "Not Started",
#         }

#     return {
#         "ISDRAFT": int(
#             row[0]
#             or 0
#         ),
#         "STATUS": (
#             str(row[1]).strip()
#             if row[1] is not None
#             else "Draft"
#         ),
#     }
# def verify_vendor_otp(
#     email: str,
#     otp: str,
# ) -> dict[str, Any]:

#     normalized_email = (
#         _clean_email(email)
#     )

#     submitted_otp = (
#         otp or ""
#     ).strip()

#     if (
#         len(submitted_otp) != 6
#         or not submitted_otp.isdigit()
#     ):
#         raise OtpValidationError(
#             "OTP must contain exactly six digits"
#         )

#     with get_connection() as connection:
#         cursor = connection.cursor()

#         try:
#             vendor = _fetch_vendor_by_email(
#                 cursor=cursor,
#                 email=normalized_email,
#             )

#             prospect_seq = int(
#                 vendor["ProspectSeq"]
#             )
#             prospect_id = str(
#                 vendor["ProspectId"]
#             ).strip().upper()

#             registration_state = (
#                 _fetch_vendor_registration_state(
#                     cursor=cursor,
#                     prospect_id=prospect_id,
#                 )
#             )

#             cursor.execute(
#                 f"""
#                 SELECT TOP 1
#                     ID,
#                     OTPCODE,
#                     ISUSED,
#                     ATTEMPTS,
#                     EXPIRESAT,
#                     CASE
#                         WHEN EXPIRESAT < GETDATE()
#                         THEN 1
#                         ELSE 0
#                     END AS IsExpired
#                 FROM {OTP_TABLE}
#                 WITH
#                 (
#                     UPDLOCK,
#                     ROWLOCK
#                 )
#                 WHERE USERID = ?
#                 ORDER BY ID DESC
#                 """,
#                 prospect_seq,
#             )

#             otp_row = cursor.fetchone()

#             if otp_row is None:
#                 raise OtpValidationError(
#                     "OTP was not requested"
#                 )

#             otp_id = int(
#                 otp_row[0]
#             )

#             stored_otp = str(
#                 otp_row[1]
#             ).strip()

#             is_used = bool(
#                 otp_row[2]
#             )

#             attempts = int(
#                 otp_row[3]
#                 or 0
#             )

#             is_expired = bool(
#                 otp_row[5]
#             )

#             if is_used:
#                 raise OtpValidationError(
#                     "OTP has already been used"
#                 )

#             if attempts >= (
#                 settings.OTP_MAX_ATTEMPTS
#             ):
#                 cursor.execute(
#                     f"""
#                     UPDATE {OTP_TABLE}
#                     SET
#                         ISUSED = 1,
#                         MODIFIEDDATETIME = GETDATE(),
#                         MODIFIEDBY = 'PORTAL',
#                         RECVERSION =
#                             ISNULL(RECVERSION, 0) + 1
#                     WHERE ID = ?
#                     """,
#                     otp_id,
#                 )

#                 connection.commit()

#                 raise OtpValidationError(
#                     "Maximum OTP attempts exceeded"
#                 )

#             if is_expired:
#                 cursor.execute(
#                     f"""
#                     UPDATE {OTP_TABLE}
#                     SET
#                         ISUSED = 1,
#                         MODIFIEDDATETIME = GETDATE(),
#                         MODIFIEDBY = 'PORTAL',
#                         RECVERSION =
#                             ISNULL(RECVERSION, 0) + 1
#                     WHERE ID = ?
#                     """,
#                     otp_id,
#                 )

#                 connection.commit()

#                 raise OtpValidationError(
#                     "OTP has expired"
#                 )

#             # Direct comparison with the plain OTP stored in DB.
#             if stored_otp != submitted_otp:
#                 new_attempts = (
#                     attempts + 1
#                 )

#                 cursor.execute(
#                     f"""
#                     UPDATE {OTP_TABLE}
#                     SET
#                         ATTEMPTS = ?,
#                         ISUSED =
#                             CASE
#                                 WHEN ? >= ?
#                                 THEN 1
#                                 ELSE 0
#                             END,
#                         MODIFIEDDATETIME = GETDATE(),
#                         MODIFIEDBY = 'PORTAL',
#                         RECVERSION =
#                             ISNULL(RECVERSION, 0) + 1
#                     WHERE ID = ?
#                     """,
#                     new_attempts,
#                     new_attempts,
#                     settings.OTP_MAX_ATTEMPTS,
#                     otp_id,
#                 )

#                 connection.commit()

#                 remaining_attempts = max(
#                     settings.OTP_MAX_ATTEMPTS
#                     - new_attempts,
#                     0,
#                 )

#                 raise OtpValidationError(
#                     "Invalid OTP. "
#                     f"{remaining_attempts} attempts remaining."
#                 )

#             # OTP is valid. Mark it as used.
#             cursor.execute(
#                 f"""
#                 UPDATE {OTP_TABLE}
#                 SET
#                     ISUSED = 1,
#                     MODIFIEDDATETIME = GETDATE(),
#                     MODIFIEDBY = 'PORTAL',
#                     RECVERSION =
#                         ISNULL(RECVERSION, 0) + 1
#                 WHERE ID = ?
#                 """,
#                 otp_id,
#             )

#             access_token, expires_at = (
#                 _create_access_token(
#                     vendor
#                 )
#             )

#             connection.commit()

#             return {
#                 "SUCCESS": True,
#                 "MESSAGE": (
#                     "OTP verified successfully"
#                 ),
#                 "ACCESS_TOKEN": access_token,
#                 "TOKEN_TYPE": "bearer",
#                 "EXPIRES_AT": (
#                     expires_at.isoformat()
#                 ),
#                 "ISDRAFT": registration_state["ISDRAFT"],
#                 "STATUS": registration_state["STATUS"],
#                 "VENDOR": {
#                     "PROSPECT_SEQ": (
#                         vendor.get(
#                             "ProspectSeq"
#                         )
#                     ),
#                     "PROSPECT_ID": (
#                         vendor.get(
#                             "ProspectId"
#                         )
#                     ),
#                     "VENDOR_ACCOUNT": (
#                         vendor.get(
#                             "VendorAccount"
#                         )
#                     ),
#                     "NAME": (
#                         vendor.get(
#                             "Name"
#                         )
#                     ),
#                     "EMAIL": (
#                         vendor.get(
#                             "Email"
#                         )
#                     ),
#                     "CURRENCY": (
#                         vendor.get(
#                             "Currency"
#                         )
#                     ),
#                     "VEND_GROUP": (
#                         vendor.get(
#                             "VendGroup"
#                         )
#                     ),
#                 },
#             }

#         except OtpValidationError:
#             # Some validation paths already commit their
#             # attempt or used-status update.
#             raise

#         except Exception:
#             connection.rollback()
#             raise