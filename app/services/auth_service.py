
import re
import secrets
import random
import logging
from datetime import datetime, timedelta, timezone

from app.services import auth_repo
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.services.email_service import send_email
from app.core.config import settings

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)


def _token_url(path: str, token: str) -> str:
    return f"{settings.FRONTEND_BASE_URL}{path}?token={token}"


# ══════════════════════════════════════════════════════════════
# SEND SET PASSWORD LINK
# CHANGE: insert_user_d365() → insert_portal_user()  (direct SQL)
# CHANGE: update_user_d365() → update_portal_user_status() (direct SQL)
# REMOVED: mark_vendor_invited() — D365 only, not needed here
# ══════════════════════════════════════════════════════════════
def send_set_password_link(identifier: str):

    # STEP 1: Get vendor from D365 master
    vendor = auth_repo.get_vendor_from_master(identifier)
    if not vendor:
        return {"ok": False, "message": "Vendor not found"}

    vendor_account = vendor["accountnum"]
    email          = vendor["email"]

    if not email:
        return {"ok": False, "message": "Vendor email not found"}

    # STEP 2: Check if portal user exists
    existing = auth_repo.get_portal_user(vendor_account)

    if not existing:
        # INSERT directly into Azure SQL — no D365 service call
        auth_repo.insert_portal_user(
            vendor_account=vendor_account,
            email=email,
            phone=None
        )
        logger.info("New portal user created for vendor: %s", vendor_account)
    else:
        # UPDATE status to Pending — no D365 service call
        auth_repo.update_portal_user_status(
            vendor_account=vendor_account,
            status=auth_repo.STATUS_MAP["Pending"]
        )
        logger.info("Existing portal user reset to Pending: %s", vendor_account)

    # STEP 3: Send email
    link = f"{settings.FRONTEND_BASE_URL}/SetPassword"
    send_email(
        email,
        "Set your Vendor Portal password",
        f"""
        <div style="font-family:Arial;padding:20px">
            <h2>Welcome to Vendor Portal</h2>
            <p>Please use the following credentials to login:</p>
            <p style="font-size:16px;">
                <strong>Username:</strong>
                <span style="font-weight:bold;color:#1F3864;">{email}</span>
            </p>
            <p>Click below to set your password:</p>
            <a href="{link}"
               style="background:#1F3864;color:white;
                      padding:10px 20px;text-decoration:none;
                      border-radius:5px;display:inline-block">
                Set Password
            </a>
        </div>
        """
    )

    return {"ok": True, "message": "Set password email sent"}
def start_set_password(identifier: str):

    user = auth_repo.get_user_by_email_or_phone(
        identifier
    )

    if not user:
        return {
            "ok": False,
            "message": "Email not found"
        }

    otp = f"{random.randint(100000, 999999)}"

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=2)
    )

    # DIRECT SQL INSERT
    auth_repo.insert_otp(
        user_id=user["id"],
        otp_code=otp,
        expires_at=expires_at
    )

    send_email(
        user["emailaddress"],
        "OTP for Set Password",
        f"""
        <div style="font-family:Arial;padding:20px">
            <h2>Vendor Portal OTP</h2>

            <p>Your OTP is:</p>

            <div style="
                font-size:32px;
                font-weight:bold;
                color:#1F3864;
                letter-spacing:8px;
                margin:20px 0;
            ">
                {otp}
            </div>

            <p>
                This OTP is valid for
                <b>2 minutes</b>.
            </p>
        </div>
        """
    )

    return {
        "ok": True,
        "message": "OTP sent to email"
    }
def verify_set_password_otp(
    identifier: str,
    otp_code: str
):

    user = auth_repo.get_user_by_email_or_phone(
        identifier
    )

    if not user:
        return {
            "ok": False,
            "message": "Invalid email"
        }

    row = auth_repo.get_valid_otp(
        user["id"],
        otp_code
    )

    if not row:
        return {
            "ok": False,
            "message": "Invalid or expired OTP"
        }

    auth_repo.mark_otp_used(
        otp_id=row["id"],
        current_attempts=row.get("attempts", 0)
    )

    return {
        "ok": True,
        "message": "OTP verified"
    }

def set_password_after_otp(
    identifier: str,
    new_password: str,
    ip: str = None
):

    if len(new_password) < 8:
        return {
            "ok": False,
            "message":
                "Password must be at least 8 characters"
        }

    user = auth_repo.get_user_by_email_or_phone(
        identifier
    )

    if not user:
        return {
            "ok": False,
            "message": "User not found"
        }

    # ============================================
    # HASH PASSWORD
    # ============================================
    password_hash = hash_password(
        new_password
    )

    # ============================================
    # UPDATE PASSWORD
    # ============================================
    auth_repo.update_password(
        user_id=user["id"],
        password_hash=password_hash
    )

    # ============================================
    # CREATE TOKENS
    # ============================================
    payload = {
        "sub": str(user["id"]),
        "vendor_account": user["vendoraccount"],
        "email": user["emailaddress"],
        "role": "VENDOR"
    }

    access_token = create_access_token(
        payload
    )

    refresh_token = create_refresh_token(
        payload
    )

    refresh_expires = (
        datetime.utcnow()
        + timedelta(days=7)
    )

    # ============================================
    # SAVE REFRESH TOKEN
    # ============================================
    auth_repo.save_refresh_token(
        user_id=user["id"],
        vendor_account=user["vendoraccount"],
        refresh_token=refresh_token,
        expires_at=refresh_expires,
        ip=ip
    )

    return {
        "ok": True,

        "message":
            "Password set successfully",

        "access_token":
            access_token,

        "refresh_token":
            refresh_token,

        "data": {

            "vendor_account":
                user["vendoraccount"],

            "name":
                user.get("name") or "",

            "email":
                user["emailaddress"],

            "vendor_id":
                user["id"]
        }
    }
# def set_password_after_otp(
#     identifier: str,
#     new_password: str
# ):

#     if len(new_password) < 8:
#         return {
#             "ok": False,
#             "message":
#                 "Password must be at least 8 characters"
#         }

#     user = auth_repo.get_user_by_email_or_phone(
#         identifier
#     )

#     if not user:
#         return {
#             "ok": False,
#             "message": "User not found"
#         }

#     password_hash = hash_password(
#         new_password
#     )

#     auth_repo.update_password(
#         user_id=user["id"],
#         password_hash=password_hash
#     )

#     return {
#         "ok": True,
#         "message":
#             "Password set successfully",

#         "data": {
#             "vendor_account":
#                 user["vendoraccount"],

#             "name":
#                 user.get("name") or ""
#         }
#     }
# # ══════════════════════════════════════════════════════════════
# SEND OTP
# CHANGE: send_otp_to_d365() → auth_repo.insert_otp() (direct SQL)
# REMOVED: get_next_otp_id() — not needed, ID is IDENTITY column
# REMOVED: get_db_utc_now() — use Python datetime with UTC
# ══════════════════════════════════════════════════════════════
def send_login_otp(identifier: str, channel: str):
    user = auth_repo.get_user_by_email_or_phone(identifier)

    if not user:
        return {"ok": False, "message": "Email not registered. Please contact admin."}

    if user["status"] == 0:
        return {"ok": False, "message": "Account not activated yet. Please contact admin."}

    if user["status"] == 2:
        return {"ok": False, "message": "Account disabled. Please contact admin."}

    otp        = f"{random.randint(100000, 999999)}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)

    # Direct INSERT into Azure SQL — no D365 service call
    otp_id = auth_repo.insert_otp(
        user_id    = user["id"],
        otp_code   = otp,
        expires_at = expires_at
    )
    logger.info("OTP inserted | user_id=%s | otp_id=%s", user["id"], otp_id)

    channel = channel.upper()

    if channel == "EMAIL":
        send_email(
            user["emailaddress"],
            "Your Vendor Portal OTP",
            f"""
            <div style="font-family:Arial;text-align:center;padding:32px">
              <h2>Your Login OTP</h2>
              <div style="font-size:44px;font-weight:bold;
                          letter-spacing:12px;color:#1F3864;margin:20px 0">
                {otp}
              </div>
              <p style="color:#888">Valid for <b>2 minutes</b>. Do not share.</p>
            </div>
            """
        )
        return {"ok": True, "message": f"OTP sent to {user['emailaddress']}"}

    elif channel == "SMS":
        phone = user.get("phonenumber") or ""
        if not phone:
            return {"ok": False, "message": "No phone number on file. Contact admin."}
        from app.services.sms_service import send_phone_otp
        send_phone_otp(phone, otp)
        return {"ok": True, "message": f"OTP sent to ****{phone[-4:]}"}

    else:
        return {"ok": False, "message": "Invalid channel. Use EMAIL or SMS."}


# ══════════════════════════════════════════════════════════════
# VERIFY OTP
# CHANGE: update_otp_d365() → auth_repo.mark_otp_used() (direct SQL)
# CHANGE: log_login_d365()  → auth_repo.log_login()     (direct SQL)
# ══════════════════════════════════════════════════════════════
def verify_login_otp(identifier: str, channel: str, otp_code: str, ip: str = None):
    user = auth_repo.get_user_by_email_or_phone(identifier)

    if not user:
        return {"ok": False, "message": "Invalid OTP"}

    channel = channel.upper()
    row     = auth_repo.get_valid_otp(user["id"], otp_code)

    if not row:
        # Log failed attempt — direct SQL
        auth_repo.log_login(
            user_id = user["id"],
            method  = f"{channel}_OTP",
            status  = "FAILED",
            ip      = ip,
            reason  = "Invalid or expired OTP"
        )
        return {"ok": False, "message": "Invalid or expired OTP"}

    # Mark OTP used + increment attempts — direct SQL
    auth_repo.mark_otp_used(
        otp_id           = row["id"],
        current_attempts = row.get("attempts", 0)
    )

    # Log successful login — direct SQL
    auth_repo.log_login(
        user_id = user["id"],
        method  = f"{channel}_OTP",
        status  = "SUCCESS",
        ip      = ip,
        reason  = None
    )

    payload = {
        "sub":            str(user["id"]),
        "vendor_account": user["vendoraccount"],
        "email":          user["emailaddress"],
        "role":           "VENDOR"
    }

    access_token  = create_access_token(payload)
    refresh_token = create_refresh_token(payload)
    refresh_expires = datetime.utcnow() + timedelta(days=7)

    auth_repo.save_refresh_token(
        user_id=user["id"],
        vendor_account=user["vendoraccount"],
        refresh_token=refresh_token,
        expires_at=refresh_expires,
        ip=ip
    )
    return {
        "ok":            True,
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "data": {
            "vendor_account": user["vendoraccount"],
            "name":           user.get("name") or "",
            "email":          user["emailaddress"],
            "vendor_id":      user["id"]
        }
    }


# ══════════════════════════════════════════════════════════════
# LOGIN WITH PASSWORD
# CHANGE: log_login_d365() → auth_repo.log_login() (direct SQL)
# ══════════════════════════════════════════════════════════════
def login_with_password(identifier: str, password: str, ip: str = None):
    user = auth_repo.get_user_by_email_or_phone(identifier)

    if not user:
        return {"ok": False, "message": "Invalid credentials"}

    if user["status"] != 1 or not user.get("passwordhash"):
        return {"ok": False, "message": "Account not active or password not set"}

    if not verify_password(password, user["passwordhash"]):
        # Log failed — direct SQL
        auth_repo.log_login(
            user_id = user["id"],
            method  = "PASSWORD",
            status  = "FAILED",
            ip      = ip,
            reason  = "Wrong password"
        )
        return {"ok": False, "message": "Invalid credentials"}

    # Log success — direct SQL
    auth_repo.log_login(
        user_id = user["id"],
        method  = "PASSWORD",
        status  = "SUCCESS",
        ip      = ip,
        reason  = None
    )

    payload = {
        "sub":            str(user["id"]),
        "vendor_account": user["vendoraccount"],
        "email":          user["emailaddress"],
        "role":           "VENDOR"
    }

    # access_token  = create_access_token(payload)
    # refresh_token = create_refresh_token(payload)

    return {
        "ok":            True,
        # "access_token":  access_token,
        # "refresh_token": refresh_token,
        "data": {
            "vendor_account": user["vendoraccount"],
            "name":           user.get("name") or "",
            "email":          user["emailaddress"],
            "vendor_id":      user["id"]
        }
    }


# ══════════════════════════════════════════════════════════════
# SET PASSWORD (first time)
# No change needed here — already uses direct SQL via auth_repo
# ══════════════════════════════════════════════════════════════
def set_password(token: str, new_password: str):
    if len(new_password) < 8:
        return {"ok": False, "message": "Password must be at least 8 characters"}

    t = auth_repo.get_valid_token(token, "SET_PASSWORD")
    if not t:
        return {"ok": False, "message": "Invalid or expired token"}

    auth_repo.update_password(t["user_id"], hash_password(new_password))
    auth_repo.mark_token_used(t["id"])
    return {"ok": True, "message": "Password set successfully."}


# ══════════════════════════════════════════════════════════════
# RESET PASSWORD
# No change needed — already uses direct SQL via auth_repo
# ══════════════════════════════════════════════════════════════
def forgot_password(identifier: str):
    user = auth_repo.get_user_by_email_or_phone(identifier)
    if not user:
        return {"ok": False, "message": "User not found"}

    token      = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    auth_repo.insert_token(user["id"], token, "RESET_PASSWORD", expires_at)

    link   = _token_url("/reset-password", token)
    result = send_email(
        user["emailaddress"],
        "Reset your Vendor Portal password",
        f"Reset link (valid 30m): <a href='{link}'>{link}</a>"
    )

    return {"ok": True, "email_sent": result, "sent_to": user["emailaddress"]}


def reset_password(token: str, new_password: str):
    if len(new_password) < 8:
        return {"ok": False, "message": "Password must be at least 8 characters"}

    t = auth_repo.get_valid_token(token, "RESET_PASSWORD")
    if not t:
        return {"ok": False, "message": "Invalid or expired token"}

    auth_repo.update_password(t["user_id"], hash_password(new_password))
    auth_repo.mark_token_used(t["id"])
    return {"ok": True, "message": "Password reset successfully."}


# ══════════════════════════════════════════════════════════════
# ADMIN CREATE VENDOR
# CHANGE: insert_user (was broken — now uses insert_portal_user)
# ══════════════════════════════════════════════════════════════
def admin_create_vendor(vendor_account: str, email: str, phone: str = None):
    existing_account = auth_repo.get_user_by_vendor_account(vendor_account)
    if existing_account:
        return {"ok": False, "message": f"Vendor {vendor_account} already exists"}

    existing_email = auth_repo.get_user_by_email_or_phone(email)
    if existing_email:
        return {"ok": False, "message": f"Email {email} already registered"}

    # Direct INSERT into Azure SQL
    auth_repo.insert_portal_user(vendor_account, email, phone)
    result = send_set_password_link(email)

    if result.get("ok"):
        return {"ok": True, "message": f"Vendor {vendor_account} created. Email sent to {email}."}
    else:
        return {"ok": True, "message": f"Vendor {vendor_account} created but email failed."}


# ══════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════
def detect_identifier_type(identifier: str) -> str:
    identifier = identifier.strip()
    if "@" in identifier:
        return "EMAIL"
    cleaned = re.sub(r"[\s\-\(\)]", "", identifier)
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if cleaned.isdigit():
        return "PHONE"
    return "UNKNOWN"

# import re, os, secrets, random
# from datetime import datetime, timedelta, timezone

# from app.services import auth_repo
# from app.core.security import hash_password, verify_password, create_access_token
# from app.services.email_service import send_email
# from app.core.config import settings
# from app.core.security import create_refresh_token
# import logging

# logger = logging.getLogger(__name__)

# # Optional (only if not already configured globally)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
# )
# def _token_url(path: str, token: str) -> str:
#     return f"{settings.FRONTEND_BASE_URL}{path}?token={token}"


# # ── Send Set Password Link ────────────────────────────────────
# from app.db.base import get_connection
# from app.core.config import settings
# from app.services.email_service import send_email
# from app.services import auth_repo


# def send_set_password_link(identifier: str):

#     # =========================
#     # STEP 1: GET VENDOR FROM MASTER
#     # =========================
#     vendor = auth_repo.get_vendor_from_master(identifier)

#     if not vendor:
#         return {"ok": False, "message": "Vendor not found"}

#     vendor_account = vendor["accountnum"]
#     email = vendor["email"]

#     if not email:
#         return {"ok": False, "message": "Vendor email not found"}

#     # =========================
#     # STEP 2: CHECK PORTAL USER
#     # =========================
#     existing = auth_repo.get_portal_user(vendor_account)
#     if not existing:
#         user_id = auth_repo.insert_user_d365(
#             vendor_account=vendor_account,
#             email=email,
#             phone=None
#         )
#     else:
#         auth_repo.update_user_d365(
#             user_id=existing["id"],
#             vendor_account=vendor_account,
#             updates={
#                 "PortalUserStatus": 0,
#                 "updatedAt": fmt_datetime_ms()
#             }
#         )
#     # if not existing:
#     #     # INSERT NEW USER (Pending)
#     #     auth_repo.insert_portal_user(
#     #         vendor_account=vendor_account,
#     #         email=email,
#     #         phone=None
#     #     )
#     # else:
#     #     # 👉 RESET STATUS TO PENDING
#     #     auth_repo.update_portal_user_status(
#     #         vendor_account,
#     #         auth_repo.STATUS_MAP["Pending"]
#     #     )

#     # OPTIONAL: mark vendor invited in D365
#     auth_repo.mark_vendor_invited(vendor_account)

#     # =========================
#     # STEP 3: SEND EMAIL
#     # =========================
#     link = f"{settings.FRONTEND_BASE_URL}/SetPassword"
#     send_email(
#     email,
#     "Set your Vendor Portal password",
#     f"""
#     <div style="font-family:Arial;padding:20px">

#         <h2>Welcome to Vendor Portal</h2>

#         <p>Please use the following credentials to login:</p>

#         <p style="font-size:16px;">
#             <strong>Username:</strong>
#             <span style="font-weight:bold;color:#1F3864;">
#                 {email}
#             </span>
#         </p>

#         <p>Click below to set your password:</p>

#         <a href="{link}" 
#            style="background:#1F3864;color:white;
#                   padding:10px 20px;text-decoration:none;
#                   border-radius:5px;display:inline-block">
#             Set Password
#         </a>

#     </div>
#     """
# )
    
#     return {"ok": True, "message": "Set password email sent"}

# from app.db.base import get_connection

# def get_next_otp_id():
#     q = "SELECT ISNULL(MAX(ID), 20000) + 1 FROM HIQ_VendorOtp"
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute(q)
#         return int(cur.fetchone()[0])
# import requests
# from app.core.d365_auth import get_d365_token
# from app.api.routes.rfq_reply import fmt_datetime_ms
# from app.core.config import settings
# def get_db_utc_now():
#     q = "SELECT GETDATE()"
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute(q)
#         return cur.fetchone()[0]
# def send_otp_to_d365(user_id: int, otp_code: str):

#     otp_id = get_next_otp_id()
#     token = get_d365_token() 
#     db_utc_now = get_db_utc_now()
#     expiry_utc = db_utc_now + timedelta(minutes=2)

#     headers = {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json"
#     }

#     body = {
#         "_request": {
#             "requestType": 1,
#             "id": int(otp_id),
#             "expiryDate": expiry_utc.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
#             # "expiryDate": fmt_datetime_ms(),
#             "attempts": 1,
#             "otpCode": otp_code,
#             "userId": str(user_id),
#             "isUsed": 0
#         }
#     }

#     # ✅ Logging instead of print
#     logger.info("D365 OTP INSERT START")
#     logger.info("URL: %s", settings.D365_VENDOR_RFQREPLY)
#     logger.info("USER ID: %s | OTP ID: %s", user_id, otp_id)
#     logger.debug("HEADERS: %s", headers)
#     logger.debug("BODY: %s", body)

#     resp = requests.post(
#         settings.D365_VENDOR_RFQREPLY,
#         headers=headers,
#         json=body,
#         verify=False
#     )

#     logger.info("D365 OTP INSERT STATUS: %s", resp.status_code)
#     logger.info("D365 OTP INSERT RESPONSE: %s", resp.text)

#     if resp.status_code >= 400:
#         logger.error("D365 OTP INSERT FAILED: %s", resp.text)
#         raise Exception(resp.text)

#     return otp_id
# def update_otp_d365(otp_id: int, user_id: int, current_attempts: int):

#     token = get_d365_token()

#     # ✅ STEP 1: Fetch OTP code from DB
#     from app.db.base import get_connection

#     otp_code = None

#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute(
#             "SELECT otp_code FROM HIQ_VendorOtp WHERE id = ?",
#             otp_id
#         )
#         row = cur.fetchone()
#         if row:
#             otp_code = row[0]

#     if not otp_code:
#         raise Exception(f"OTP code not found for OTP ID: {otp_id}")

#     # ✅ STEP 2: Prepare request
#     headers = {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json"
#     }

#     body = {
#         "_request": {
#             "requestType": 1,
#             "id": int(otp_id),

#             # ✅ REQUIRED for correct update
#             "otpCode": otp_code,
#             "userId": str(user_id),

#             # ✅ update fields
#             "isUsed": 1,
#             "attempts": int(current_attempts) + 1
#         }
#     }

#     logger.info("D365 OTP UPDATE START")
#     logger.info("OTP ID: %s | USER ID: %s", otp_id, user_id)
#     logger.info("OTP CODE: %s", otp_code)  # optional debug
#     logger.debug("BODY: %s", body)

#     # ✅ STEP 3: Call D365
#     resp = requests.post(
#         settings.D365_VENDOR_RFQREPLY,
#         headers=headers,
#         json=body,
#         verify=False
#     )

#     logger.info("D365 OTP UPDATE STATUS: %s", resp.status_code)
#     logger.info("D365 OTP UPDATE RESPONSE: %s", resp.text)

#     if resp.status_code >= 400:
#         logger.error("D365 OTP UPDATE FAILED: %s", resp.text)
#         raise Exception(resp.text)

#     return resp.text
# # def update_otp_d365(otp_id: int, user_id: int, current_attempts: int):

# #     token = get_d365_token()

# #     headers = {
# #         "Authorization": f"Bearer {token}",
# #         "Content-Type": "application/json"
# #     }

# #     body = {
# #         "_request": {
# #             "requestType": 1,
# #             "id": int(otp_id),
# #             "otpCode": "",
# #             "userId": str(user_id),
# #             "isUsed": 1,
# #             "attempts": int(current_attempts) + 1
# #         }
# #     }

# #     logger.info("D365 OTP UPDATE START")
# #     logger.info("OTP ID: %s | USER ID: %s", otp_id, user_id)
# #     logger.debug("BODY: %s", body)

# #     resp = requests.post(
# #         settings.D365_VENDOR_RFQREPLY,
# #         headers=headers,
# #         json=body,
# #         verify=False
# #     )

# #     logger.info("D365 OTP UPDATE STATUS: %s", resp.status_code)
# #     logger.info("D365 OTP UPDATE RESPONSE: %s", resp.text)

# #     if resp.status_code >= 400:
# #         logger.error("D365 OTP UPDATE FAILED: %s", resp.text)
# #         raise Exception(resp.text)

# #     return resp.text

# def start_set_password(identifier: str):
#     user = auth_repo.get_user_by_email_or_phone(identifier)

#     if not user:
#         return {"ok": False, "message": "Email not found"}

#     otp = f"{random.randint(100000, 999999)}"
#     expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)

#     # auth_repo.insert_otp(user["id"], otp, expires_at)
#     otp_id = send_otp_to_d365(
#     user_id=user["id"],
#     otp_code=otp
# )

#     send_email(
#         user["email_address"],
#         "OTP for Set Password",
#         f"Your OTP is <b>{otp}</b> (valid 2 minutes)"
#     )

#     return {"ok": True, "message": "OTP sent to email"}
# def verify_set_password_otp(identifier: str, otp_code: str):
#     user = auth_repo.get_user_by_email_or_phone(identifier)

#     if not user:
#         return {"ok": False, "message": "Invalid email"}

#     row = auth_repo.get_valid_otp(user["id"], otp_code)

#     if not row:
#         return {"ok": False, "message": "Invalid or expired OTP"}

#     # auth_repo.mark_otp_used(row["id"])
#     update_otp_d365(
#     otp_id=row["id"],
#     user_id=user["id"],
#     current_attempts=row.get("attempts", 1)
# )

#     return {"ok": True, "message": "OTP verified"}
# # def send_set_password_link(identifier: str):
# #     user = auth_repo.get_user_by_email_or_phone(identifier)
# #     if not user:
# #         return {"ok": False, "message": "User not found"}

# #     token      = secrets.token_urlsafe(32)
# #     expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
# #     auth_repo.insert_token(user["id"], token, "SET_PASSWORD", expires_at)

# #     link = _token_url("/set-password", token)
# #     send_email(
# #         user["email_address"],
# #         "Set your Vendor Portal password",
# #         f"Click to set your password (valid 48h): <a href='{link}'>{link}</a>"
# #     )
# #     return {"ok": True}


# # ── Set Password ──────────────────────────────────────────────
# # def set_password(token: str, new_password: str):
# #     if len(new_password) < 8:
# #         return {"ok": False, "message": "Password must be at least 8 characters"}

# #     t = auth_repo.get_valid_token(token, "SET_PASSWORD")
# #     if not t:
# #         return {"ok": False, "message": "Invalid or expired token"}

# #     auth_repo.update_password(t["user_id"], hash_password(new_password))
# #     auth_repo.mark_token_used(t["id"])
# #     return {"ok": True, "message": "Password set successfully. You can now login."}

# def set_password_after_otp(identifier: str, new_password: str):
#     if len(new_password) < 8:
#         return {
#             "ok": False,
#             "message": "Password must be at least 8 characters"
#         }

#     user = auth_repo.get_user_by_email_or_phone(identifier)

#     if not user:
#         return {
#             "ok": False,
#             "message": "User not found"
#         }

#     # HASH PASSWORD
#     password_hash = hash_password(new_password)

#     auth_repo.update_user_d365(
#         user_id=user["id"],
#         vendor_account=user["vendor_account"],
#         updates={
#             "passwordHash": password_hash,
#             "passwordSetAt": fmt_datetime_ms(),
#             "updatedAt": fmt_datetime_ms(),
#             "PortalUserStatus": 1
#         }
#     )
#     # password_hash = hash_password(new_password)

#     # # UPDATE PASSWORD
#     # auth_repo.update_password(user["id"], password_hash)
    

#     return {
#         "ok": True,
#         "message": "Password set successfully",
#         "data": {
#             "vendor_account": user.get("vendor_account"),
#             "name": user.get("name")
#         }
#     }

# def forgot_password(identifier: str):
#     user = auth_repo.get_user_by_email_or_phone(identifier)
    
#     if not user:
#         # TEMPORARY — remove after debugging
#         return {"ok": False, "message": "DEBUG: User not found in DB"}
    
#     token      = secrets.token_urlsafe(32)
#     expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
#     auth_repo.insert_token(user["id"], token, "RESET_PASSWORD", expires_at)

#     link = _token_url("/reset-password", token)
#     result = send_email(      # ← capture result
#         user["email_address"],
#         "Reset your Vendor Portal password",
#         f"Reset link (valid 30m): <a href='{link}'>{link}</a>"
#     )
    
#     # TEMPORARY — remove after debugging
#     return {"ok": True, "email_sent": result, "sent_to": user["email_address"]}
# # ── Reset Password ────────────────────────────────────────────
# def reset_password(token: str, new_password: str):
#     if len(new_password) < 8:
#         return {"ok": False, "message": "Password must be at least 8 characters"}

#     t = auth_repo.get_valid_token(token, "RESET_PASSWORD")
#     if not t:
#         return {"ok": False, "message": "Invalid or expired token"}

#     auth_repo.update_password(t["user_id"], hash_password(new_password))
#     auth_repo.mark_token_used(t["id"])
#     return {"ok": True, "message": "Password reset successfully."}


# # ── Login with Password ───────────────────────────────────────
# def login_with_password(identifier: str, password: str, ip: str = None):
#     user = auth_repo.get_user_by_email_or_phone(identifier)
#     if not user:
#         return {"ok": False, "message": "Invalid credentials"}

#     if user["status"] != 1 or not user.get("password_hash"):
#         return {"ok": False, "message": "Account not active or password not set"}

#     # if not verify_password(password, user["password_hash"]):
#     #     auth_repo.log_login(user["id"], "PASSWORD", "FAILED", ip, "Wrong password")
#     if not verify_password(password, user["password_hash"]):
#         auth_repo.log_login_d365(user["id"], "PASSWORD", "FAILED", ip, "Wrong password")
#         return {"ok": False, "message": "Invalid credentials"}
    
#     auth_repo.log_login_d365(user["id"], "PASSWORD", "SUCCESS", ip, None)
#     # auth_repo.log_login(user["id"], "PASSWORD", "SUCCESS", ip, None)

#     token = create_access_token({
#         "sub":            str(user["id"]),
#         "vendor_account": user["vendor_account"],
#         "email":          user["email_address"],
#         "role":           "VENDOR"
#     })
#     payload = {
#     "sub": str(user["id"]),
#     "vendor_account": user["vendor_account"],
#     "email": user["email_address"],
#     "role": "VENDOR"
# }

#     # access_token = create_access_token(payload)
#     # refresh_token = create_refresh_token(payload)

#     return {
#         "ok": True,
#         # "access_token": access_token,
#         # "refresh_token": refresh_token,   # ✅ NEW
#         "data": {
#             "vendor_account": user["vendor_account"],
#             "name": user.get("name") or "",
#             "email": user["email_address"],
#             "vendor_id": user["id"]
#         }
#     }
    
# #     return {
# #     "ok": True,
# #     "access_token": token,
# #     "data": {
# #         "vendor_account": user["vendor_account"],
# #         "name": user.get("name") or user.get("vendor_name") or "",
# #         "email":user["email_address"],
# #         "vendor_id":user["id"]
# #     }
# # }


# # ── Send OTP ──────────────────────────────────────────────────

# def send_login_otp(identifier: str, channel: str):
#     user = auth_repo.get_user_by_email_or_phone(identifier)

#     if not user:
#         return {"ok": False, "message": "Email not registered. Please contact admin."}

#     if user["status"] == 0:
#         return {"ok": False, "message": "Account not activated yet. Please contact admin."}

#     if user["status"] == 3:
#         return {"ok": False, "message": "Account disabled. Please contact admin."}

#     otp        = f"{random.randint(100000, 999999)}"
#     expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
#     # auth_repo.insert_otp(user["id"], otp, expires_at)

#     otp_id = send_otp_to_d365(
#     user_id=user["id"],
#     otp_code=otp
# )

    
#     channel = channel.upper()

#     if channel == "EMAIL":
#         send_email(
#             user["email_address"],
#             "Your Vendor Portal OTP",
#             f"""
#             <div style="font-family:Arial;text-align:center;padding:32px">
#               <h2>Your Login OTP</h2>
#               <div style="font-size:44px;font-weight:bold;
#                           letter-spacing:12px;color:#1F3864;margin:20px 0">
#                 {otp}
#               </div>
#               <p style="color:#888">Valid for <b>2 minutes</b>. Do not share.</p>
#             </div>
#             """
#         )
#         return {"ok": True, "message": f"OTP sent to {user['email_address']}"}

#     elif channel == "SMS":
#         phone = user.get("phone_number") or ""
#         if not phone:
#             return {"ok": False, "message": "No phone number on file. Contact admin."}
#         from app.services.sms_service import send_phone_otp
#         send_phone_otp(phone, otp)
#         return {"ok": True, "message": f"OTP sent to ****{phone[-4:]}"}

#     else:
#         return {"ok": False, "message": "Invalid channel. Use EMAIL or SMS."}

# # ── Verify OTP ────────────────────────────────────────────────
# def verify_login_otp(
#     identifier: str,
#     channel: str,
#     otp_code: str,
#     ip: str = None
# ):

#     user = auth_repo.get_user_by_email_or_phone(identifier)

#     if not user:
#         return {
#             "ok": False,
#             "message": "Invalid OTP"
#         }

#     channel = channel.upper()

#     row = auth_repo.get_valid_otp(
#         user["id"],
#         otp_code
#     )

#     if not row:

#         auth_repo.log_login_d365(
#             user["id"],
#             f"{channel}_OTP",
#             "FAILED",
#             ip,
#             "Invalid OTP"
#         )

#         return {
#             "ok": False,
#             "message": "Invalid or expired OTP"
#         }

#     update_otp_d365(
#         otp_id=row["id"],
#         user_id=user["id"],
#         current_attempts=row.get("attempts", 1)
#     )

#     auth_repo.log_login_d365(
#         user["id"],
#         f"{channel}_OTP",
#         "SUCCESS",
#         ip,
#         None
#     )

#     payload = {
#         "sub": str(user["id"]),
#         "vendor_account": user["vendor_account"],
#         "email": user["email_address"],
#         "role": "VENDOR"
#     }

#     access_token = create_access_token(payload)

#     refresh_token = create_refresh_token(payload)

#     return {
#         "ok": True,
#         "access_token": access_token,
#         "refresh_token": refresh_token,
#         "data": {
#             "vendor_account": user["vendor_account"],
#             "name": user.get("name") or user.get("vendor_name") or "",
#             "email": user["email_address"],
#             "vendor_id": user["id"]
#         }
#     }
#     # return {
#     #     "ok":             True,
#     #     "access_token":   jwt_token,      # ← Fix: was "token" before
#     #     "vendor_account": user["vendor_account"],
#     #     "vendor_id":      user["id"],
#     #     "email":          user["email_address"],
#     #     "vendor_name" :user["vendor_name"]
#     # }


# # ── Admin Create Vendor ───────────────────────────────────────
# def admin_create_vendor(vendor_account: str, email: str, phone: str = None):
#     existing_account = auth_repo.get_user_by_vendor_account(vendor_account)
#     if existing_account:
#         return {"ok": False, "message": f"Vendor {vendor_account} already exists"}

#     existing_email = auth_repo.get_user_by_email_or_phone(email)
#     if existing_email:
#         return {"ok": False, "message": f"Email {email} already registered"}

#     auth_repo.insert_user(vendor_account, email, phone)
#     result = send_set_password_link(email)

#     if result.get("ok"):
#         return {"ok": True, "message": f"Vendor {vendor_account} created. Email sent to {email}."}
#     else:
#         return {"ok": True, "message": f"Vendor {vendor_account} created but email failed."}


# # ── Detect Identifier Type ────────────────────────────────────
# def detect_identifier_type(identifier: str) -> str:
#     identifier = identifier.strip()
#     if "@" in identifier:
#         return "EMAIL"
#     cleaned = re.sub(r"[\s\-\(\)]", "", identifier)
#     if cleaned.startswith("+"):
#         cleaned = cleaned[1:]
#     if cleaned.isdigit():
#         return "PHONE"
#     return "UNKNOWN"

