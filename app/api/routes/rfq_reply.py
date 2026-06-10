import json
import threading
import time
import urllib3
from datetime import datetime
from fastapi import APIRouter
from app.core.config import settings
from app.models.rfq_models import RFQReplyPayload
from app.db.bids_repo import (
    insert_reply,
    update_reply,
    get_pending_for_scheduler,
    insert_bid_header,
    insert_bid_lines,
    mark_all_sent_for_rfq,
    mark_failed,
    send_expiry_reminder_emails,
)
from app.services.notification_service import notify_new_rfq
from app.db.base import get_connection, get_connection
from app.core.config import settings
SCHEMA=settings.DB_SCHEMA
VENDOR_USER_TABLE = f"{SCHEMA}.HIQ_VENDORPORTALUSER"
OTP_TABLE = f"{SCHEMA}.HIQ_VENDOROTP"
LOGIN_LOG_TABLE = f"{SCHEMA}.HIQ_VENDORLOGINLOG"
REFRESH_TOKEN_TABLE = f"{SCHEMA}.HIQ_VENDORREFRESHTOKEN"
VEN_NOT=f"{SCHEMA}.HIQ_VENDORNOTIFICATION"
RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VENDORRFQREPLIES"
RFQ_BID_SUB=f"{SCHEMA}.HIQ_VENDORBIDSUBMISSIONHEADER"
RFQ_LINEBID=f"{SCHEMA}.HIQ_VENDORBIDSUBMISSIONLINE"


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(prefix="/rfq", tags=["RFQ Reply"])
STATUS_DRAFT_ONLY=3

# ══════════════════════════════════════════════════════════
# API — VENDOR SUBMITS RFQ REPLY
# Direct INSERT into HIQ_VENDORRFQREPLIES (Azure SQL)
# No D365 call here
# ══════════════════════════════════════════════════════════

@router.post("/reply")
def submit_rfq_reply(payload: RFQReplyPayload):
    """
    Vendor submits RFQ bid.
    Inserts into HIQ_VENDORRFQREPLIES with SUBMISSIONSTATUS=0 (Pending).
    Scheduler picks it up at midnight.
    """
    data = payload.dict()
    try:
        record_id = insert_reply(data)
        return {"ok": True, "id": record_id, "message": "Bid saved."}
    except Exception as e:
        print(f"[SUBMIT] Error: {e}")
        return {"ok": False, "message": str(e)}


@router.put("/update")
def update_rfq_reply(payload: RFQReplyPayload):
    """
    Vendor updates existing bid before scheduler runs.
    Updates HIQ_VENDORRFQREPLIES payload.
    """
    data = payload.dict()
    try:
        record_id = update_reply(data)
        return {"ok": True, "id": record_id, "message": "Bid updated."}
    except Exception as e:
        print(f"[UPDATE] Error: {e}")
        return {"ok": False, "message": str(e)}


# ══════════════════════════════════════════════════════════
# SCHEDULER — MOVE DATA BETWEEN AZURE SQL TABLES
#
# Step 1: Read HIQ_VENDORRFQREPLIES where SUBMISSIONSTATUS=0
# Step 2: INSERT into HIQ_VENDORBIDSUBMISSIONHEADER
# Step 3: INSERT into HIQ_VENDORBIDSUBMISSIONLINE
# Step 4: UPDATE HIQ_VENDORRFQREPLIES → SUBMISSIONSTATUS=1
#
# D365 batch job reads from HEADER+LINE on their own schedule.
# No D365 API call from this scheduler.
# ══════════════════════════════════════════════════════════
def has_valid_lines(payload: dict) -> bool:
    """
    Returns True if at least ONE line has
    lineStatus=True AND unitPrice > 0.
    If ALL lines are draft or zero price → returns False.
    """
    items = payload.get("Item", []) or payload.get("rfqItems", [])

    for item in items:

        line_status = item.get("lineStatus", True)

        if isinstance(line_status, str):
            line_status = line_status.lower() == "true"

        unit_price = float(item.get("unitPrice") or 0)

        if line_status and unit_price > 0:
            return True  # at least one valid line found

    return False  # all lines are draft or zero price
def _mark_draft_only(row_id: int):
    """
    Sets SUBMISSIONSTATUS=3 (Draft Only).
    Not an error — vendor saved all lines as draft.
    Will NOT be retried by scheduler.
    Will appear in Expired tab as 'Draft Only'.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE {RFQ_REPLIES_TABLE}
            SET    SUBMISSIONSTATUS = ?,
                   LASTERROR        = 'Draft only — no confirmed lines, not sent to D365.',
                   SENDTOD365AT     = GETUTCDATE(),
                   MODIFIEDDATETIME = GETUTCDATE(),
                   MODIFIEDBY       = 'SCHEDULER',
                   RECVERSION       = ISNULL(RECVERSION, 0) + 1
            WHERE  ID = ?
            """,
            STATUS_DRAFT_ONLY,
            row_id
        )
        conn.commit()
    print(f"[SCHEDULER] ID={row_id} → DRAFT ONLY (status=3, not an error)")
 
def release_expired_bids():
    print(f"\n[SCHEDULER] Starting at {datetime.now()}")
 
    pending = get_pending_for_scheduler()
 
    if not pending:
        print("[SCHEDULER] No pending bids.")
        return
 
    print(f"[SCHEDULER] {len(pending)} bids to process")
 
    for item in pending:
        row_id         = item["id"]
        payload        = item["payload"]
        rfq_id         = item["rfq_id"]
        vendor_account = item["vendor_account"]
        attempts       = item["attempts"]
 
        print(f"\n[SCHEDULER] ID={row_id} | RFQ={rfq_id} | Vendor={vendor_account}")
 
        # ── CHECK ITEMS EXIST ────────────────────────────────
        items_list = payload.get("Item", []) or payload.get("rfqItems", [])
        if not items_list:
            mark_failed(row_id, "No items in payload", attempts)
            print(f"[SCHEDULER] ID={row_id} FAILED — no items")
            continue
 
        # ── CHECK AT LEAST ONE VALID CONFIRMED LINE ──────────
        # If all lines are draft (lineStatus=false), this is NOT an error.
        # Vendor intentionally saved without confirming.
        # Set status=3 (Draft Only) — silent skip, shows in Expired tab.
        if not has_valid_lines(payload):
            _mark_draft_only(row_id)
            print(f"[SCHEDULER] ID={row_id} SKIPPED — all lines draft, no confirmed lines")
            continue
 
        # ── STEP 1: INSERT HIQ_VENDORBIDSUBMISSIONHEADER ─────
        try:
            header_id = insert_bid_header(
                rfq_replies_id=row_id,
                payload=payload
            )
            print(f"[SCHEDULER] Header → ID={header_id}")
        except Exception as e:
            mark_failed(row_id, f"Header insert failed: {str(e)[:500]}", attempts)
            print(f"[SCHEDULER] ID={row_id} HEADER FAILED: {e}")
            continue
 
        # ── STEP 2: INSERT HIQ_VENDORBIDSUBMISSIONLINE ───────
        try:
            line_count = insert_bid_lines(
                rfq_id=rfq_id,
                header_id=header_id,
                vendor_account=vendor_account,
                payload=payload
            )
            print(f"[SCHEDULER] Lines → {line_count} inserted")
        except Exception as e:
            mark_failed(row_id, f"Lines insert failed: {str(e)[:500]}", attempts)
            print(f"[SCHEDULER] ID={row_id} LINES FAILED: {e}")
            continue
 
        # ── STEP 3: MARK SENT ────────────────────────────────
        mark_all_sent_for_rfq(rfq_id, vendor_account)
        print(f"[SCHEDULER] ID={row_id} COMPLETE → SUBMISSIONSTATUS=1")
 
    print(f"[SCHEDULER] Done at {datetime.now()}\n")
 
# def release_expired_bids():
#     print(f"\n[SCHEDULER] Starting at {datetime.now()}")

#     pending = get_pending_for_scheduler()

#     if not pending:
#         print("[SCHEDULER] No pending bids.")
#         return

#     print(f"[SCHEDULER] {len(pending)} bids to process")

#     for item in pending:
#         row_id         = item["id"]
#         payload        = item["payload"]
#         rfq_id         = item["rfq_id"]
#         vendor_account = item["vendor_account"]
#         attempts       = item["attempts"]

#         print(f"\n[SCHEDULER] ID={row_id} | RFQ={rfq_id} | Vendor={vendor_account}")

#         # ── CHECK ITEMS EXIST ────────────────────────────────
#         items_list = payload.get("Item", []) or payload.get("rfqItems", [])
#         if not items_list:
#             mark_failed(row_id, "No items in payload", attempts)
#             print(f"[SCHEDULER] ID={row_id} FAILED — no items")
#             continue

#         # ── CHECK AT LEAST ONE VALID CONFIRMED LINE ──────────
#         if not has_valid_lines(payload):
#             mark_failed(
#                 row_id,
#                 "No confirmed lines with price > 0. All lines are draft.",
#                 attempts
#             )
#             print(f"[SCHEDULER] ID={row_id} FAILED — all lines draft or zero price")
#             continue

#         # ── STEP 1: INSERT HIQ_VENDORBIDSUBMISSIONHEADER ─────
#         try:
#             header_id = insert_bid_header(
#                 rfq_replies_id=row_id,
#                 payload=payload
#             )
#             print(f"[SCHEDULER] Header → ID={header_id}")
#         except Exception as e:
#             mark_failed(row_id, f"Header insert failed: {str(e)[:500]}", attempts)
#             print(f"[SCHEDULER] ID={row_id} HEADER FAILED: {e}")
#             continue

#         # ── STEP 2: INSERT HIQ_VENDORBIDSUBMISSIONLINE ───────
#         try:
#             line_count = insert_bid_lines(
#                 rfq_id=rfq_id,
#                 header_id=header_id,
#                 vendor_account=vendor_account,
#                 payload=payload
#             )
#             print(f"[SCHEDULER] Lines → {line_count} inserted")
#         except Exception as e:
#             mark_failed(row_id, f"Lines insert failed: {str(e)[:500]}", attempts)
#             print(f"[SCHEDULER] ID={row_id} LINES FAILED: {e}")
#             continue

#         # ── STEP 3: MARK SENT ────────────────────────────────
#         mark_all_sent_for_rfq(rfq_id, vendor_account)
#         print(f"[SCHEDULER] ID={row_id} COMPLETE → SUBMISSIONSTATUS=1")

#     print(f"[SCHEDULER] Done at {datetime.now()}\n")
# def release_expired_bids():
#     print(f"\n[SCHEDULER] Starting at {datetime.now()}")

#     pending = get_pending_for_scheduler()

#     if not pending:
#         print("[SCHEDULER] No pending bids.")
#         return

#     print(f"[SCHEDULER] {len(pending)} bids to process")

#     for item in pending:
#         row_id         = item["id"]
#         payload        = item["payload"]
#         rfq_id         = item["rfq_id"]
#         vendor_account = item["vendor_account"]
#         attempts       = item["attempts"]

#         print(f"\n[SCHEDULER] ID={row_id} | RFQ={rfq_id} | Vendor={vendor_account}")

#         # ── CHECK ITEMS EXIST ────────────────────────────────
#         items_list = payload.get("Item", []) or payload.get("rfqItems", [])
#         if not items_list:
#             mark_failed(row_id, "No items in payload", attempts)
#             print(f"[SCHEDULER] ID={row_id} FAILED — no items")
#             continue

#         # ── CHECK AT LEAST ONE VALID CONFIRMED LINE ──────────
#         # ← NEW: Don't send header if ALL lines are draft
#         if not has_valid_lines(payload):
#             mark_failed(
#                 row_id,
#                 "No confirmed lines with price > 0. All lines are draft.",
#                 attempts
#             )
#             print(f"[SCHEDULER] ID={row_id} FAILED — all lines are draft or zero price")
#             continue

#         # ── STEP 1: INSERT HIQ_VENDORBIDSUBMISSIONHEADER ─────
#         try:
#             header_id = insert_bid_header(
#                 rfq_replies_id=row_id,
#                 payload=payload
#             )
#             print(f"[SCHEDULER] Header → ID={header_id}")
#         except Exception as e:
#             mark_failed(row_id, f"Header insert failed: {str(e)[:500]}", attempts)
#             print(f"[SCHEDULER] ID={row_id} HEADER FAILED: {e}")
#             continue

#         # ── STEP 2: INSERT HIQ_VENDORBIDSUBMISSIONLINE ───────
#         try:
#             line_count = insert_bid_lines(
#                 rfq_id=rfq_id,
#                 header_id=header_id,
#                 vendor_account=vendor_account,
#                 payload=payload
#             )
#             print(f"[SCHEDULER] Lines → {line_count} inserted")
#         except Exception as e:
#             mark_failed(row_id, f"Lines insert failed: {str(e)[:500]}", attempts)
#             print(f"[SCHEDULER] ID={row_id} LINES FAILED: {e}")
#             continue

#         # ── STEP 3: MARK SENT ────────────────────────────────
#         mark_all_sent_for_rfq(rfq_id, vendor_account)
#         print(f"[SCHEDULER] ID={row_id} COMPLETE → SUBMISSIONSTATUS=1")

#     print(f"[SCHEDULER] Done at {datetime.now()}\n")
# def release_expired_bids():
#     """
#     Moves confirmed pending bids from HIQ_VENDORRFQREPLIES
#     into HIQ_VENDORBIDSUBMISSIONHEADER + HIQ_VENDORBIDSUBMISSIONLINE.
#     Updates SUBMISSIONSTATUS=1 on success.
#     """
#     print(f"\n[SCHEDULER] Starting at {datetime.now()}")

#     pending = get_pending_for_scheduler()

#     if not pending:
#         print("[SCHEDULER] No pending bids.")
#         return

#     print(f"[SCHEDULER] {len(pending)} bids to process")

#     for item in pending:
#         row_id         = item["id"]
#         payload        = item["payload"]
#         rfq_id         = item["rfq_id"]
#         vendor_account = item["vendor_account"]
#         attempts       = item["attempts"]

#         print(f"\n[SCHEDULER] ID={row_id} | RFQ={rfq_id} | Vendor={vendor_account}")

#         # Validate payload has items
#         items_list = payload.get("Item", []) or payload.get("rfqItems", [])
#         if not items_list:
#             mark_failed(row_id, "No items in payload", attempts)
#             print(f"[SCHEDULER] ID={row_id} FAILED — no items")
#             continue

#         # ── STEP 1: INSERT HIQ_VENDORBIDSUBMISSIONHEADER ──
#         try:
#             header_id = insert_bid_header(
#                 rfq_replies_id=row_id,
#                 payload=payload
#             )
#             print(f"[SCHEDULER] Header → ID={header_id}")
#         except Exception as e:
#             mark_failed(row_id, f"Header insert failed: {str(e)[:500]}", attempts)
#             print(f"[SCHEDULER] ID={row_id} HEADER FAILED: {e}")
#             continue

#         # ── STEP 2: INSERT HIQ_VENDORBIDSUBMISSIONLINE ────
#         try:
#             line_count = insert_bid_lines(
#                 rfq_id=rfq_id,
#                 header_id=header_id,
#                 vendor_account=vendor_account,
#                 payload=payload
#             )
#             print(f"[SCHEDULER] Lines → {line_count} inserted")
#         except Exception as e:
#             mark_failed(row_id, f"Lines insert failed: {str(e)[:500]}", attempts)
#             print(f"[SCHEDULER] ID={row_id} LINES FAILED: {e}")
#             continue

#         # ── STEP 3: UPDATE HIQ_VENDORRFQREPLIES → STATUS=1 
#         mark_all_sent_for_rfq(rfq_id, vendor_account)
#         print(f"[SCHEDULER] ID={row_id} COMPLETE → SUBMISSIONSTATUS=1")

#     print(f"[SCHEDULER] Done at {datetime.now()}\n")


# ══════════════════════════════════════════════════════════
# SYNC NEW RFQ NOTIFICATIONS
# D365 read → Azure SQL write
# ══════════════════════════════════════════════════════════
def sync_new_rfq_notifications():

    print(
        "[NOTIF] "
        "Syncing new RFQ notifications..."
    )

    try:

        with get_connection() as conn:

            cur = conn.cursor()

            cur.execute(f"""
                SELECT

                    T.VENDACCOUNT,

                    C.RFQCASEID,

                    T.RFQID,

                    C.NAME

                FROM {SCHEMA}.D365_PURCHRFQCASETABLE C
                WITH (NOLOCK)

                INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T
                WITH (NOLOCK)

                    ON T.RFQCASEID
                        = C.RFQCASEID

                WHERE C.EXPIRYDATETIME
                        >= GETDATE()
            """)

            d365_rows = cur.fetchall()

        if not d365_rows:

            print(
                "[NOTIF] "
                "No active RFQs"
            )

            return

        with get_connection() as vp_conn:

            cur = vp_conn.cursor()

            cur.execute(f"""
                SELECT

                    VENDORACCOUNT,

                    REFERENCEID

                FROM {VEN_NOT}

                WHERE NOTIFTYPE = 1
            """)

            already_notified = {

                (
                    str(r[0])
                    .strip()
                    .upper(),

                    str(r[1])
                    .strip()
                    .upper()
                )

                for r in cur.fetchall()
            }

        for row in d365_rows:

            vendor_account = (
                str(row[0]).strip()
            )

            rfq_case_id = (
                str(row[1]).strip()
            )

            rfq_name = row[3] or ""

            key = (

                vendor_account.upper(),

                rfq_case_id.upper()
            )

            if key in already_notified:
                continue

            try:

                notify_new_rfq(

                    vendor_account,

                    rfq_case_id,

                    rfq_name
                )

                print(
                    f"[NOTIF] NEW_RFQ → "
                    f"{vendor_account} | "
                    f"{rfq_case_id}"
                )

            except Exception as e:

                print(
                    f"[NOTIF] Error "
                    f"{vendor_account} | "
                    f"{rfq_case_id}: {e}"
                )

    except Exception as e:

        print(
            f"[NOTIF] sync error: {e}"
        )

# def sync_new_rfq_notifications():
#     print("[NOTIF] Syncing new RFQ notifications...")

#     try:
#         with get_connection() as d365_conn:
#             cur = d365_conn.cursor()

#             cur.execute(
#                 """
#                 SELECT
#                     T.VENDACCOUNT,
#                     C.RFQCASEID,
#                     T.RFQID,
#                     C.NAME
#                 FROM PURCHRFQCASETABLE C WITH (NOLOCK)
#                 INNER JOIN PURCHRFQTABLE T WITH (NOLOCK)
#                     ON T.RFQCASEID = C.RFQCASEID
#                    AND T.DATAAREAID = C.DATAAREAID
#                 WHERE C.DATAAREAID = ?
#                   AND C.EXPIRYDATETIME >= GETDATE()
#                 """,
#                 settings.D365_COMPANY
#             )

#             d365_rows = cur.fetchall()

#         if not d365_rows:
#             print("[NOTIF] No active RFQs")
#             return

#         with get_connection() as vp_conn:
#             cur = vp_conn.cursor()

#             cur.execute(f"""
#                 SELECT
#                     VENDORACCOUNT,
#                     REFERENCEID
#                 FROM {VEN_NOT}
#                 WHERE NOTIFTYPE = 1
#             """)

#             already_notified = {
#                 (
#                     str(r[0]).strip().upper(),
#                     str(r[1]).strip().upper()
#                 )
#                 for r in cur.fetchall()
#             }

#         for row in d365_rows:
#             vendor_account = str(row[0]).strip()
#             rfq_case_id = str(row[1]).strip()
#             rfq_name = row[3] or ""

#             key = (
#                 vendor_account.upper(),
#                 rfq_case_id.upper()
#             )

#             if key in already_notified:
#                 continue

#             try:
#                 notify_new_rfq(
#                     vendor_account,
#                     rfq_case_id,
#                     rfq_name
#                 )

#                 print(
#                     f"[NOTIF] NEW_RFQ → "
#                     f"{vendor_account} | {rfq_case_id}"
#                 )

#             except Exception as e:
#                 print(
#                     f"[NOTIF] Error "
#                     f"{vendor_account} | {rfq_case_id}: {e}"
#                 )

#     except Exception as e:
#         print(f"[NOTIF] sync error: {e}")



# # ══════════════════════════════════════════════════════════
# # SYNC RFQ DECISION NOTIFICATIONS
# # D365 read line statuses → Azure SQL write notification
# ══════════════════════════════════════════════════════════
def sync_rfq_decision_notifications():

    from app.services.notification_service import (
        notify_rfq_accepted,
        notify_rfq_rejected,
    )

    print(
        "[DECISION] Syncing decision notifications..."
    )

    try:

        with get_connection() as conn:

            cur = conn.cursor()

            # ====================================================
            # FETCH SUBMITTED RFQS
            # ====================================================
            cur.execute(f"""
                SELECT DISTINCT

                    RFQID,

                    VENDORACCOUNT

                FROM {RFQ_REPLIES_TABLE}

                WHERE SUBMISSIONSTATUS = 1
            """)

            submitted = cur.fetchall()

    except Exception as e:

        print(
            f"[DECISION] Read error: {e}"
        )

        return

    if not submitted:
        return

    try:

        with get_connection() as conn:

            cur = conn.cursor()

            for rfq_id, vendor_account in submitted:

                try:

                    # ============================================
                    # FETCH LINE STATUS
                    # ============================================
                    cur.execute(f"""
                        SELECT

                            PL.STATUS

                        FROM {SCHEMA}.D365_PURCHRFQREPLYLINE RL
                        WITH (NOLOCK)

                        INNER JOIN {SCHEMA}.D365_PURCHRFQLINE PL
                        WITH (NOLOCK)

                            ON PL.RECID
                                = RL.RFQLINERECID

                        WHERE RL.RFQID = ?
                    """, (rfq_id,))

                    statuses = [

                        int(r[0])

                        for r in cur.fetchall()

                        if r[0] is not None
                    ]

                    if not statuses:
                        continue

                    # ============================================
                    # STILL UNDER REVIEW
                    # ============================================
                    if any(s < 3 for s in statuses):
                        continue

                    # ============================================
                    # ACCEPTED
                    # ============================================
                    if any(s == 4 for s in statuses):

                        notify_rfq_accepted(
                            vendor_account,
                            rfq_id
                        )

                        print(
                            f"[DECISION] ACCEPTED → "
                            f"{vendor_account} | {rfq_id}"
                        )

                    # ============================================
                    # REJECTED
                    # ============================================
                    else:

                        notify_rfq_rejected(
                            vendor_account,
                            rfq_id
                        )

                        print(
                            f"[DECISION] REJECTED → "
                            f"{vendor_account} | {rfq_id}"
                        )

                except Exception as e:

                    print(
                        f"[DECISION] Error "
                        f"{rfq_id}: {e}"
                    )

    except Exception as e:

        print(
            f"[DECISION] Connection error: {e}"
        )
# def sync_rfq_decision_notifications():
#     from app.services.notification_service import (
#         notify_rfq_accepted,
#         notify_rfq_rejected,
#     )

#     print("[DECISION] Syncing decision notifications...")

#     try:
#         with get_connection() as conn:
#             cur = conn.cursor()

#             cur.execute(f"""
#                 SELECT DISTINCT
#                     RFQID,
#                     VENDORACCOUNT
#                 FROM {RFQ_REPLIES_TABLE}
#                 WHERE SUBMISSIONSTATUS = 1
#             """)

#             submitted = cur.fetchall()

#     except Exception as e:
#         print(f"[DECISION] Read error: {e}")
#         return

#     if not submitted:
#         return

#     try:
#         with get_connection() as d365_conn:
#             cur = d365_conn.cursor()

#             for rfq_id, vendor_account in submitted:
#                 try:
#                     cur.execute(
#                         """
#                         SELECT PL.STATUS
#                         FROM PURCHRFQREPLYLINE RL WITH (NOLOCK)
#                         INNER JOIN PURCHRFQLINE PL WITH (NOLOCK)
#                             ON PL.RECID = RL.RFQLINERECID
#                            AND PL.DATAAREAID = ?
#                         WHERE RL.RFQID = ?
#                           AND RL.DATAAREAID = ?
#                         """,
#                         settings.D365_COMPANY,
#                         rfq_id,
#                         settings.D365_COMPANY
#                     )

#                     statuses = [
#                         int(r[0])
#                         for r in cur.fetchall()
#                         if r[0] is not None
#                     ]

#                     if not statuses:
#                         continue

#                     if any(s < 3 for s in statuses):
#                         continue

#                     if any(s == 4 for s in statuses):
#                         notify_rfq_accepted(
#                             vendor_account,
#                             rfq_id
#                         )

#                         print(
#                             f"[DECISION] ACCEPTED → "
#                             f"{vendor_account} | {rfq_id}"
#                         )

#                     else:
#                         notify_rfq_rejected(
#                             vendor_account,
#                             rfq_id
#                         )

#                         print(
#                             f"[DECISION] REJECTED → "
#                             f"{vendor_account} | {rfq_id}"
#                         )

#                 except Exception as e:
#                     print(
#                         f"[DECISION] Error "
#                         f"{rfq_id}: {e}"
#                     )

#     except Exception as e:
#         print(f"[DECISION] D365 error: {e}")


# ══════════════════════════════════════════════════════════
# BACKGROUND SCHEDULER THREAD
# ══════════════════════════════════════════════════════════

_scheduler_thread = None
_stop_event       = threading.Event()


def _scheduler_loop():
    last_run_date = None
    while not _stop_event.is_set():
        try:
            now = datetime.now()
            # if now.hour == 18 and now.minute == 10:
            # if now.hour == 0 and 5 <= now.minute <= 9:
            if now.hour == 10 and now.minute == 16:
                if last_run_date != now.date():
                    last_run_date = now.date()
                    print(f"\n{'='*50}")
                    print(f"[SCHEDULER] Midnight job — {now}")
                    print(f"{'='*50}")

                    release_expired_bids()          # VENDORRFQREPLIES → HEADER + LINE
                    sync_new_rfq_notifications()    # D365 RFQ → notifications
                    sync_rfq_decision_notifications()  # D365 decisions → notifications
                    send_expiry_reminder_emails()   # expiry reminder emails
        except Exception as e:
            print(f"[SCHEDULER] Error: {e}")
        time.sleep(60)


def start_scheduler():
    global _scheduler_thread
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()
    print("[SCHEDULER] Started — runs daily at midnight")


def stop_scheduler():
    _stop_event.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
    print("[SCHEDULER] Stopped")
