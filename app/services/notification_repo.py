# notification_repo.py

from typing import List, Dict, Any

from app.db.base import get_connection
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

VENDOR_NOTIFICATION_TABLE = (
    f"{SCHEMA}.HIQ_VENDORNOTIFICATION"
)

# =========================================================
# NOTIFICATION META
# =========================================================

NOTIF_META = {
    "NEW_RFQ": {
        "url": "/RFQs",
        "tab": "New",
    },

    "RFQ_EXPIRING": {
        "url": "/RFQs",
        "tab": "New",
    },

    "RFQ_ACCEPTED": {
        "url": "/RFQs",
        "tab": "Completed Bid Status",
        "bid_status": "accepted",
    },

    "RFQ_REJECTED": {
        "url": "/RFQs",
        "tab": "Completed Bid Status",
        "bid_status": "rejected",
    },

    "PO_CONFIRMED": {
        "url": "/POs",
    }
}

# =========================================================
# NOTIFICATION TYPE MAP
# =========================================================

NOTIF_TYPE_MAP = {
    "NEW_RFQ": 1,
    "RFQ_EXPIRING": 2,
    "PO_CONFIRMED": 3,
    "RFQ_ACCEPTED": 4,
    "RFQ_REJECTED": 5
}

NOTIF_TYPE_REVERSE = {
    v: k for k, v in NOTIF_TYPE_MAP.items()
}

# =========================================================
# ENRICH RESPONSE
# =========================================================

def _enrich(row: dict) -> dict:

    meta = NOTIF_META.get(
        row.get("notif_type", ""),
        {}
    )

    row["url"] = meta.get("url", "")
    row["tab"] = meta.get("tab", "")
    row["bid_status"] = meta.get("bid_status", None)

    return row


# =========================================================
# INSERT NOTIFICATION
# =========================================================

def insert_notification(
    vendor_account: str,
    notif_type: str,
    title: str,
    message: str,
    reference_id: str
):

    notif_type_int = NOTIF_TYPE_MAP.get(
        notif_type,
        0
    )

    if notif_type_int == 0:
        raise Exception(
            f"Invalid notification type: {notif_type}"
        )

    reference_id = str(reference_id)

    with get_connection() as conn:

        cur = conn.cursor()

        # ==========================================
        # DUPLICATE CHECK
        # ==========================================

        cur.execute(
            f"""
            SELECT 1
            FROM {VENDOR_NOTIFICATION_TABLE}

            WHERE VENDORACCOUNT = ?
              AND NOTIFTYPE = ?
              AND REFERENCEID = ?
            """,
            vendor_account,
            notif_type_int,
            reference_id
        )

        if cur.fetchone():
            return None

        # ==========================================
        # INSERT
        # ==========================================

        cur.execute(
            f"""
            INSERT INTO {VENDOR_NOTIFICATION_TABLE}
            (
                VENDORACCOUNT,
                NOTIFTYPE,
                TITLE,
                MESSAGE,
                REFERENCEID,
                ISREAD,
                READAT,
                CREATEDDATETIME
            )

            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?,
                0,
                NULL,
                GETDATE()
            )
            """,
            vendor_account,
            notif_type_int,
            title,
            message,
            reference_id
        )

        conn.commit()

        print(
            f"[NOTIFICATION INSERTED] "
            f"{vendor_account} | {reference_id}"
        )

        return True


# =========================================================
# GET UNREAD
# =========================================================

def get_unread_notifications(
    vendor_account: str
) -> List[Dict[str, Any]]:

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT
                ID,
                NOTIFTYPE,
                TITLE,
                MESSAGE,
                REFERENCEID,
                CREATEDDATETIME

            FROM {VENDOR_NOTIFICATION_TABLE}

            WHERE VENDORACCOUNT = ?
              AND ISREAD = 0

            ORDER BY CREATEDDATETIME DESC
            """,
            vendor_account
        )

        cols = [
            c[0].lower()
            for c in cur.description
        ]

        result = []

        for r in cur.fetchall():

            row = dict(zip(cols, r))

            row["notif_type"] = (
                NOTIF_TYPE_REVERSE.get(
                    row["notiftype"],
                    str(row["notiftype"])
                )
            )

            row = _enrich(row)

            result.append(row)

        return result


# =========================================================
# GET ALL
# =========================================================

def get_all_notifications(
    vendor_account: str
) -> List[Dict[str, Any]]:

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT
                ID,
                NOTIFTYPE,
                TITLE,
                MESSAGE,
                REFERENCEID,
                ISREAD,
                READAT,
                CREATEDDATETIME

            FROM {VENDOR_NOTIFICATION_TABLE}

            WHERE VENDORACCOUNT = ?

            ORDER BY CREATEDDATETIME DESC
            """,
            vendor_account
        )

        cols = [
            c[0].lower()
            for c in cur.description
        ]

        result = []

        for r in cur.fetchall():

            row = dict(zip(cols, r))

            row["notif_type"] = (
                NOTIF_TYPE_REVERSE.get(
                    row["notiftype"],
                    str(row["notiftype"])
                )
            )

            row = _enrich(row)

            result.append(row)

        return result


# =========================================================
# GET UNREAD COUNT
# =========================================================

def get_unread_count(
    vendor_account: str
):

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT COUNT(*)

            FROM {VENDOR_NOTIFICATION_TABLE}

            WHERE VENDORACCOUNT = ?
              AND ISREAD = 0
            """,
            vendor_account
        )

        return int(cur.fetchone()[0])


# =========================================================
# GET BY ID
# =========================================================

def get_notification_by_id(
    notif_id: int
):

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT
                ID,
                VENDORACCOUNT,
                NOTIFTYPE,
                TITLE,
                MESSAGE,
                REFERENCEID,
                ISREAD,
                READAT,
                CREATEDDATETIME

            FROM {VENDOR_NOTIFICATION_TABLE}

            WHERE ID = ?
            """,
            notif_id
        )

        row = cur.fetchone()

        if not row:
            return {}

        cols = [
            c[0].lower()
            for c in cur.description
        ]

        data = dict(zip(cols, row))

        data["notif_type"] = (
            NOTIF_TYPE_REVERSE.get(
                data["notiftype"],
                str(data["notiftype"])
            )
        )

        return data


# =========================================================
# UPDATE SINGLE
# =========================================================

def update_notification(
    notif_id: int,
    is_read: int
):

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            f"""
            UPDATE {VENDOR_NOTIFICATION_TABLE}

            SET
                ISREAD = ?,

                READAT =
                    CASE
                        WHEN ? = 1
                        THEN GETDATE()
                        ELSE NULL
                    END

            WHERE ID = ?
            """,
            is_read,
            is_read,
            notif_id
        )

        conn.commit()


# =========================================================
# MARK SINGLE READ
# =========================================================

def mark_notification_read(
    notif_id: int
):

    update_notification(
        notif_id=notif_id,
        is_read=1
    )


# =========================================================
# MARK ALL READ
# =========================================================

def mark_all_read(
    vendor_account: str
):

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            f"""
            UPDATE {VENDOR_NOTIFICATION_TABLE}

            SET
                ISREAD = 1,
                READAT = GETDATE()

            WHERE VENDORACCOUNT = ?
              AND ISREAD = 0
            """,
            vendor_account
        )

        conn.commit()


# =========================================================
# DELETE SINGLE
# =========================================================

def delete_notification(
    notif_id: int
):

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            f"""
            DELETE
            FROM {VENDOR_NOTIFICATION_TABLE}

            WHERE ID = ?
            """,
            notif_id
        )

        conn.commit()


# =========================================================
# DELETE ALL READ
# =========================================================

def delete_all_read(
    vendor_account: str
):

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            f"""
            DELETE
            FROM {VENDOR_NOTIFICATION_TABLE}

            WHERE VENDORACCOUNT = ?
              AND ISREAD = 1
            """,
            vendor_account
        )

        conn.commit()
# import json
# from typing import List, Dict, Any
# from app.db.base import get_connection
# from app.core.config import settings
# from app.utils.date_utils import format_date
# NOTIF_META = {
#     "NEW_RFQ": {
#         "url":  "/RFQs",
#         "tab":  "New",
#     },
#     "RFQ_EXPIRING": {
#         "url":  "/RFQs",
#         "tab":  "New",
#     },
#     "RFQ_ACCEPTED": {
#         "url":  "/RFQs",
#         "tab":  "Completed Bid Status",
#         "bid_status": "accepted",
#     },
#     "RFQ_REJECTED": {
#         "url":  "/RFQs",
#         "tab":  "Completed Bid Status",
#         "bid_status": "rejected",
#     },
#     "PO_CONFIRMED": {
#         "url":  "/POs",
#     },
# }
# def _enrich(row: dict) -> dict:
#     """Add url, tab, bid_status based on notif_type."""
#     meta = NOTIF_META.get(row.get("notif_type", ""), {})
#     row["url"]        = meta.get("url", "")
#     row["tab"]        = meta.get("tab", "")
#     row["bid_status"] = meta.get("bid_status", None)

#     return row
# NOTIF_TYPE_MAP = {

#     "NEW_RFQ":      1,
#     "RFQ_EXPIRING": 2,
#     "PO_CONFIRMED": 3,
#     "RFQ_ACCEPTED": 4,
#     "RFQ_REJECTED": 5
# }

# NOTIF_TYPE_REVERSE = {v: k for k, v in NOTIF_TYPE_MAP.items()}
# # {1: "NEW_RFQ", 2: "RFQ_EXPIRING", 3: "PO_CONFIRMED", 4: "RFQ_ACCEPTED", 5: "RFQ_REJECTED"}

# AX_RECID_BASE = 5637144576

# def get_next_notif_id(cursor) -> int:
#     cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 FROM HIQ_VendorNotification")
#     return int(cursor.fetchone()[0])

# def get_next_recid(cursor) -> int:
#     cursor.execute("SELECT ISNULL(MAX(RECID), ?) + 1 FROM HIQ_VendorNotification", AX_RECID_BASE)
#     return int(cursor.fetchone()[0])
# def insert_notification(
#     vendor_account: str,
#     notif_type: str,
#     title: str,
#     message: str,
#     reference_id: str
# ):
#     import requests
#     from datetime import datetime
#     from app.core.d365_auth import get_d365_token

#     def fmt_datetime_ms():
#         return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

#     notif_type_int = NOTIF_TYPE_MAP.get(notif_type, 0)

#     with get_connection() as conn:
#         cur = conn.cursor()

#         # STEP 1 — duplicate check (fast check)
#         cur.execute("""
#             SELECT 1
#             FROM HIQ_VendorNotification
#             WHERE VENDOR_ACCOUNT = ?
#               AND NOTIF_TYPE = ?
#               AND REFERENCE_ID = ?
#         """, (vendor_account, notif_type_int, str(reference_id)))

#         if cur.fetchone():
#             return None  # silent skip

#         # STEP 2 — generate ID
#         cur.execute("""
#             SELECT ISNULL(MAX(ID), 100000) + 1
#             FROM HIQ_VendorNotification
#         """)
#         new_id = int(cur.fetchone()[0])

#     token = get_d365_token()

#     body = {
#         "_request": {
#             "requestType": 4,
#             "id": new_id,
#             "vendorAccount": vendor_account,
#             "PortalNotifType": notif_type_int,
#             "title": title,
#             "message": message,
#             "isRead": 0,
#             "readAt": "1900-01-01 00:00:00.000",
#             "createdAt": fmt_datetime_ms(),
#             "referenceId": str(reference_id)
#         }
#     }

#     try:
#         resp = requests.post(
#             settings.D365_VENDOR_RFQREPLY,
#             headers={
#                 "Authorization": f"Bearer {token}",
#                 "Content-Type": "application/json"
#             },
#             json=body,
#             verify=False,
#             timeout=60
#         )

#         if resp.status_code >= 400:
#             raise Exception(resp.text)

#         return new_id

#     except Exception as e:
#         # 🔥 CRITICAL: ignore duplicate DB error
#         if "duplicate" in str(e).lower() or "unique" in str(e).lower():
#             return None
#         raise
# import requests
# from datetime import datetime
# from app.core.d365_auth import get_d365_token


# def fmt_datetime_ms():
#     return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# def update_notification_d365(
#     notif_id: int,
#     vendor_account: str,
#     notif_type: int,
#     title: str,
#     message: str,
#     reference_id: str,
#     is_read: int
# ):
#     token = get_d365_token()

#     body = {
#         "_request": {
#             "requestType": 4,
#             "id": int(notif_id),
#             "vendorAccount": vendor_account,
#             "PortalNotifType": int(notif_type),
#             "title": title,
#             "message": message,
#             "isRead": int(is_read),
#             "readAt": fmt_datetime_ms() if int(is_read) == 1 else "1900-01-01 00:00:00.000",
#             "createdAt": fmt_datetime_ms(),
#             "referenceId": str(reference_id)
#         }
#     }

#     resp = requests.post(
#         settings.D365_VENDOR_RFQREPLY,
#         headers={
#             "Authorization": f"Bearer {token}",
#             "Content-Type": "application/json"
#         },
#         json=body,verify=False
#     )

#     print("NOTIFICATION UPDATE STATUS:", resp.status_code)
#     print("NOTIFICATION UPDATE RESPONSE:", resp.text)

#     if resp.status_code >= 400:
#         raise Exception(resp.text)

#     return resp.text
# # def insert_notification(vendor_account: str, notif_type: str,
# #                          title: str, message: str, reference_id: str):
# #     with get_connection() as conn:
# #         cur = conn.cursor()
# #         notif_type_int = NOTIF_TYPE_MAP.get(notif_type, 0)

# #         cur.execute("""
# #             SELECT COUNT(*) FROM HIQ_VendorNotification
# #             WHERE VENDOR_ACCOUNT = ?
# #             AND NOTIF_TYPE = ?
# #             AND REFERENCE_ID = ?
# #         """, (vendor_account, notif_type_int, reference_id))

# #         if cur.fetchone()[0] > 0:
# #             return None  # already exists, skip

# #         next_id = get_next_notif_id(cur)
# #         recid   = AX_RECID_BASE + next_id

# #         cur.execute("""
# #     INSERT INTO HIQ_VendorNotification
# #     (ID, VENDOR_ACCOUNT, NOTIF_TYPE, TITLE, MESSAGE, REFERENCE_ID, RECID, CREATED_AT)
# #     VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
# # """, (next_id, vendor_account, notif_type_int, title, message, reference_id, recid))
# #         conn.commit()
# #         return next_id

# # def insert_notification(vendor_account: str, notif_type: str,
# #                          title: str, message: str, reference_id: str):  # ← ref_id → reference_id
# #     with get_connection() as conn:
# #         cur = conn.cursor()
# #         next_id        = get_next_notif_id(cur)
# #         recid          = AX_RECID_BASE + next_id
# #         notif_type_int = NOTIF_TYPE_MAP.get(notif_type, 0)

# #         cur.execute("""
# #             INSERT INTO HIQ_VendorNotification
# #             (ID, VENDOR_ACCOUNT, NOTIF_TYPE, TITLE, MESSAGE, REFERENCE_ID, RECID)
# #             VALUES (?, ?, ?, ?, ?, ?, ?)
# #         """, (next_id, vendor_account, notif_type_int, title, message, reference_id, recid))
# #         #                                                                ↑ was ref_id
# #         conn.commit()
# #         return next_id

# # def insert_notification(vendor_account: str, notif_type: str,
# #                          title: str, message: str, REFERENCE_ID: str):
# #     with get_connection() as conn:
# #         cur = conn.cursor()
# #         next_id        = get_next_notif_id(cur)
# #         notif_type_int = NOTIF_TYPE_MAP.get(notif_type, 0)
# #           # ← "NEW_RFQ" → 1

# #         cur.execute("""
# #             INSERT INTO HIQ_VendorNotification
# #             (ID, VENDOR_ACCOUNT, NOTIF_TYPE, TITLE, MESSAGE, REFERENCE_ID, RECID)
# #             VALUES (?, ?, ?, ?, ?, ?, 0)
# #         """, (next_id, vendor_account, notif_type_int, title, message, REFERENCE_ID))
# #         conn.commit()
# #         return next_id


# def get_unread_notifications(vendor_account: str) -> List[Dict[str, Any]]:
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT ID, NOTIF_TYPE, TITLE, MESSAGE, REFERENCE_ID, CREATED_AT
#             FROM HIQ_VendorNotification
#             WHERE VENDOR_ACCOUNT = ?
#               AND IS_READ = 0
#             ORDER BY CREATED_AT DESC
#         """, (vendor_account,))
#         cols = [c[0].lower() for c in cur.description]
#         result = []
#         for r in cur.fetchall():
#             row = dict(zip(cols, r))
#             row["notif_type"] = NOTIF_TYPE_REVERSE.get(row["notif_type"], str(row["notif_type"]))  # ← 1 → "NEW_RFQ"
#             row=_enrich(row)
#             result.append(row)
#         return result


# def get_all_notifications(vendor_account: str) -> List[Dict[str, Any]]:
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT ID, NOTIF_TYPE, TITLE, MESSAGE, REFERENCE_ID,
#                    IS_READ, READ_AT, CREATED_AT
#             FROM HIQ_VendorNotification
#             WHERE VENDOR_ACCOUNT = ?
#             ORDER BY CREATED_AT DESC
#         """, (vendor_account,))
#         cols = [c[0].lower() for c in cur.description]
#         result = []
#         for r in cur.fetchall():
#             row = dict(zip(cols, r))
#             row["notif_type"] = NOTIF_TYPE_REVERSE.get(row["notif_type"], str(row["notif_type"]))  # ← 1 → "NEW_RFQ"
#             row=_enrich(row)
#             result.append(row)
#         return result


# def get_unread_count(vendor_account: str) -> int:
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT COUNT(*)
#             FROM HIQ_VendorNotification
#             WHERE VENDOR_ACCOUNT = ?
#               AND IS_READ = 0
#         """, (vendor_account,))
#         return int(cur.fetchone()[0])

# def mark_notification_read(notif_id: int):
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT ID, VENDOR_ACCOUNT, NOTIF_TYPE, TITLE, MESSAGE, REFERENCE_ID
#             FROM HIQ_VendorNotification
#             WHERE ID = ?
#         """, (notif_id,))
#         row = cur.fetchone()

#         if not row:
#             return

#         update_notification_d365(
#             notif_id=row[0],
#             vendor_account=row[1],
#             notif_type=row[2],
#             title=row[3],
#             message=row[4],
#             reference_id=row[5],
#             is_read=1
#         )
# def mark_all_read(vendor_account: str):
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT ID, VENDOR_ACCOUNT, NOTIF_TYPE, TITLE, MESSAGE, REFERENCE_ID
#             FROM HIQ_VendorNotification
#             WHERE VENDOR_ACCOUNT = ?
#               AND IS_READ = 0
#         """, (vendor_account,))
#         rows = cur.fetchall()

#         for row in rows:
#             update_notification_d365(
#                 notif_id=row[0],
#                 vendor_account=row[1],
#                 notif_type=row[2],
#                 title=row[3],
#                 message=row[4],
#                 reference_id=row[5],
#                 is_read=1
#             )
# # def mark_notification_read(notif_id: int):
# #     with get_connection() as conn:
# #         cur = conn.cursor()
# #         cur.execute("""
# #             UPDATE HIQ_VendorNotification
# #             SET IS_READ = 1,
# #                 READ_AT = GETDATE()
# #             WHERE ID = ?
# #               AND IS_READ = 0
# #         """, (notif_id,))
# #         conn.commit()


# # def mark_all_read(vendor_account: str):
# #     with get_connection() as conn:
# #         cur = conn.cursor()
# #         cur.execute("""
# #             UPDATE HIQ_VendorNotification
# #             SET IS_READ = 1,
# #                 READ_AT = GETDATE()
# #             WHERE VENDOR_ACCOUNT = ?
# #               AND IS_READ = 0
# #         """, (vendor_account,))
# #         conn.commit()


# def get_notification_by_id(notif_id: int) -> Dict[str, Any]:
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT ID, VENDOR_ACCOUNT, NOTIF_TYPE, TITLE,
#                    MESSAGE, REFERENCE_ID, IS_READ, READ_AT, CREATED_AT
#             FROM HIQ_VendorNotification
#             WHERE ID = ?
#         """, (notif_id,))
#         row = cur.fetchone()
#         if not row:
#             return {}
#         cols = [c[0].lower() for c in cur.description]
#         data = dict(zip(cols, row))
#         data["notif_type"] = NOTIF_TYPE_REVERSE.get(data["notif_type"], str(data["notif_type"]))  # ← convert
#         return data


# def delete_notification(notif_id: int):
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             DELETE FROM HIQ_VendorNotification
#             WHERE ID = ?
#         """, (notif_id,))
#         conn.commit()


# def delete_all_read(vendor_account: str):
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             DELETE FROM HIQ_VendorNotification
#             WHERE VENDOR_ACCOUNT = ?
#               AND IS_READ = 1
#         """, (vendor_account,))
#         conn.commit() 

