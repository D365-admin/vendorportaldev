from app.db.base import get_connection, get_d365_connection
from typing import Dict, Any, List
from app.services.rfq_submissionservice import fetch_submitted_rfqs
from app.services.rfq_inprogressservice import fetch_inprogress_rfqs
from datetime import datetime, timedelta
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"
def fetch_dashboard_metrics(vendor_account: str) -> Dict[str, Any]:

    # ============================================================
    # D365 DB
    # ============================================================
    with get_d365_connection() as conn:

        cur = conn.cursor()

        # ========================================================
        # 1. EXPIRING SOON
        # ========================================================
        cur.execute("""
            SELECT
                T.RFQID,
                L.EXPIRYDATETIME
            FROM PurchRFQCaseTable L WITH (NOLOCK)
            INNER JOIN PurchRFQTable T WITH (NOLOCK)
                ON T.RFQCASEID = L.RFQCASEID
               AND T.VENDACCOUNT = ?
            WHERE
                CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE)
                >=
                CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
            --AND
                --CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE)
                --<=
               -- CAST(DATEADD(MINUTE,330,DATEADD(DAY,7,GETUTCDATE())) AS DATE)
            AND EXISTS (
                SELECT 1
                FROM PurchRFQCaseLine CL WITH (NOLOCK)

                INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
                    ON AVL.ITEMID = CL.ITEMID
                   AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
                   AND AVL.VALIDFROM <= GETUTCDATE()
                   AND AVL.VALIDTO >= GETUTCDATE()

                WHERE CL.RFQCASEID = L.RFQCASEID
            )
        """, (vendor_account,))

        expiry_rows = cur.fetchall()

        expiring = len(expiry_rows)

        today = (datetime.utcnow()+timedelta(minutes=330)).date()
        tomorrow = today + timedelta(days=1)

        closing_today = 0
        closing_tomorrow = 0

        for r in expiry_rows:

            expiry = r[1]

            if not expiry:
                continue

            expiry_date = (expiry+timedelta(minutes=330)).date()

            if expiry_date == today:
                closing_today += 1

            elif expiry_date == tomorrow:
                closing_tomorrow += 1


        # ========================================================
        # 2. PO COUNT
        # ========================================================
        cur.execute("""
            SELECT COUNT(DISTINCT PURCHID)
            FROM PURCHTABLE WITH (NOLOCK)
            WHERE ORDERACCOUNT = ?
              AND DATAAREAID = 'hi-q'
        """, (vendor_account,))

        po_count = int(cur.fetchone()[0] or 0)


    # ============================================================
    # PORTAL DB
    # ============================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT DISTINCT
                RFQID,
                RFQCASEID
            FROM {RFQ_REPLIES_TABLE}  WITH (NOLOCK)
            WHERE VENDORACCOUNT = ?
              AND SUBMISSIONSTATUS = 0
        """, (vendor_account,))

        inprogress_rows = cur.fetchall()


    # ============================================================
    # D365 EXPIRY CHECK FOR INPROGRESS
    # ============================================================
    inprogress_count = 0
    closes_today = 0
    closes_tomorrow = 0

    if inprogress_rows:

        rfq_case_ids = [r[1] for r in inprogress_rows]

        placeholders = ",".join(["?"] * len(rfq_case_ids))

        with get_d365_connection() as conn:

            cur = conn.cursor()

            cur.execute(f"""
                SELECT
                    RFQCASEID,
                    EXPIRYDATETIME

                FROM PurchRFQCaseTable WITH (NOLOCK)

                WHERE RFQCASEID IN ({placeholders})

                  AND CAST(
                        DATEADD(MINUTE,330,EXPIRYDATETIME)
                        AS DATE
                      )

                      >=

                      CAST(
                        DATEADD(MINUTE,330,GETUTCDATE())
                        AS DATE
                      )
            """, rfq_case_ids)

            rows = cur.fetchall()

            inprogress_count = len(rows)

            for row in rows:

                expiry = row[1]

                if not expiry:
                    continue

                expiry_date = expiry.date()

                if expiry_date == today:
                    closes_today += 1

                elif expiry_date == tomorrow:
                    closes_tomorrow += 1


    # ============================================================
    # BIDS WON
    # ============================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT DISTINCT RFQID
            FROM {RFQ_REPLIES_TABLE}  WITH (NOLOCK)
            WHERE VENDORACCOUNT = ?
              AND SUBMISSIONSTATUS = 1
        """, (vendor_account,))

        submitted_rfqs = [
            r[0]
            for r in cur.fetchall()
        ]


    bids_won = 0

    if submitted_rfqs:

        placeholders = ",".join(["?"] * len(submitted_rfqs))

        with get_d365_connection() as conn:

            cur = conn.cursor()

            cur.execute(f"""
                SELECT COUNT(DISTINCT RFQID)
                FROM PURCHRFQLINE WITH (NOLOCK)
                WHERE STATUS = 4
                  AND DATAAREAID = 'hi-q'
                  AND RFQID IN ({placeholders})
            """, submitted_rfqs)

            bids_won = int(cur.fetchone()[0] or 0)


    # ============================================================
    # SUBTITLES
    # ============================================================
    if closing_today > 0:
        expiring_subtitle = f"{closing_today} closing today"

    elif closing_tomorrow > 0:
        expiring_subtitle = f"{closing_tomorrow} closing tomorrow"

    else:
        expiring_subtitle = "None closing today"


    if closes_today > 0:
        inprogress_subtitle = f"{closes_today} closing today"

    elif closes_tomorrow > 0:
        inprogress_subtitle = f"{closes_tomorrow} closing tomorrow"

    else:
        inprogress_subtitle = "No bids closing today"


    return {

        "expiring_soon": {
            "count": expiring,
            "subtitle": expiring_subtitle
        },

        "po_count": {
            "count": po_count,
            "subtitle": "Total purchase orders"
        },

        "bids_in_progress": {
            "count": inprogress_count,
            "subtitle": inprogress_subtitle
        },

        "bids_won": {
            "count": bids_won,
            "subtitle": "Total accepted bids"
        }
    }
# def fetch_dashboard_metrics(vendor_account: str) -> Dict[str, Any]:
#     with get_connection() as conn:
#         cur = conn.cursor()

#         # ── 1. RFQs Expiring Soon ─────────────────────────────
#         cur.execute("""
#             SELECT
#                 COUNT(DISTINCT T.RFQID)         AS EXPIRING_SOON_COUNT,
#                 SUM(CASE
#                     WHEN CAST(L.EXPIRYDATETIME AS DATE) = CAST(GETDATE() AS DATE)
#                     THEN 1 ELSE 0
#                 END) AS CLOSING_TODAY,

#                 SUM(CASE
#                     WHEN CAST(L.EXPIRYDATETIME AS DATE) = CAST(DATEADD(DAY,1,GETDATE()) AS DATE)
#                     THEN 1 ELSE 0
#                 END) AS CLOSING_TOMORROW
                
#             FROM PurchRFQCaseTable L WITH (NOLOCK)

#             INNER JOIN PurchRFQTable T WITH (NOLOCK)
#                 ON  T.RFQCASEID   = L.RFQCASEID
#                 AND T.VENDACCOUNT = ?
#             WHERE CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) >= CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
# AND   CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) <= CAST(DATEADD(MINUTE,330,DATEADD(DAY,7,GETUTCDATE())) AS DATE)
#             --WHERE L.EXPIRYDATETIME >= GETUTCDATE()
#               --AND L.EXPIRYDATETIME <= DATEADD(DAY, 7, GETUTCDATE())

#               AND EXISTS (
#                   SELECT 1
#                   FROM PurchRFQCaseLine CL WITH (NOLOCK)
#                   INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                       ON  AVL.ITEMID            = CL.ITEMID
#                       AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                       AND AVL.VALIDFROM        <= GETUTCDATE()
#                       AND AVL.VALIDTO          >= GETUTCDATE()
#                   WHERE CL.RFQCASEID = L.RFQCASEID
#               )
#         """, (vendor_account,))

#         row               = cur.fetchone()
#         expiring          = int(row[0] or 0)
#         closing_today     = int(row[1] or 0)
#         closing_tomorrow  = int(row[2] or 0)

#         # ── 2. PO Count ───────────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(DISTINCT PT.PURCHID) AS PO_COUNT
#             FROM PURCHTABLE PT WITH (NOLOCK)
#             WHERE PT.ORDERACCOUNT = ?
#               AND PT.DATAAREAID   = 'hi-q'
#         """, (vendor_account,))

#         row      = cur.fetchone()
#         po_count = int(row[0] or 0)

#         # ── 3. Bids In Progress ───────────────────────────────
#         cur.execute("""
#            SELECT
#     COUNT(DISTINCT R.RFQ_ID) AS INPROGRESS_COUNT,

#     COUNT(DISTINCT CASE 
#         WHEN CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) = CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
#         --WHEN CAST(L.EXPIRYDATETIME AS DATE) = CAST(GETUTCDATE() AS DATE)
#         THEN R.RFQ_ID 
#     END) AS CLOSES_TODAY,

#     COUNT(DISTINCT CASE 
#         WHEN CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) = CAST(DATEADD(MINUTE,330,DATEADD(DAY,1,GETUTCDATE())) AS DATE)
#         --WHEN CAST(L.EXPIRYDATETIME AS DATE) = CAST(DATEADD(DAY,1,GETUTCDATE()) AS DATE)
#         THEN R.RFQ_ID 
#     END) AS CLOSES_TOMORROW

# FROM HIQ_VENDORRFQREPLIES R WITH (NOLOCK)

# LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
#     ON L.RFQCASEID = R.RFQ_CASE_ID

# WHERE R.VENDOR_ACCOUNT    = ?
#   AND R.SUBMISSION_STATUS = 0
#   AND CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) >= CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
#         """, (vendor_account,))

#         row              = cur.fetchone()
#         inprogress_count = int(row[0] or 0)
#         closes_today     = int(row[1] or 0)
#         closes_tomorrow  = int(row[2] or 0)

#         # ── 4. Bids Won ───────────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(DISTINCT R.RFQ_ID) AS BIDS_WON
#             FROM PURCHRFQLINE PL WITH (NOLOCK)

#             INNER JOIN PURCHRFQTABLE RT WITH (NOLOCK)
#                 ON  RT.RFQID      = PL.RFQID
#                 AND RT.DATAAREAID = 'hi-q'

#             INNER JOIN HIQ_VENDORRFQREPLIES R WITH (NOLOCK)
#                 ON  R.RFQ_ID        = RT.RFQID
#                 AND R.VENDOR_ACCOUNT = ?

#             WHERE PL.STATUS           = 4
#               AND PL.DATAAREAID       = 'hi-q'
#               AND R.SUBMISSION_STATUS = 1
#         """, (vendor_account,))

#         row      = cur.fetchone()
#         bids_won = int(row[0] or 0)

#     # ── Build subtitle strings ─────────────────────────────────
#     if closing_today > 0:
#         expiring_subtitle = f"{closing_today} closing today"
#     elif closing_tomorrow > 0:
#         expiring_subtitle = f"{closing_tomorrow} closing tomorrow"
#     else:
#         expiring_subtitle = "None closing today"

#     if closes_today > 0:
#         inprogress_subtitle = f"{closes_today} closing today"
#     elif closes_tomorrow > 0:
#         inprogress_subtitle = f"{closes_tomorrow} closing tomorrow"
#     else:
#         inprogress_subtitle = "No bids closing today"

#     return {
#         "expiring_soon": {
#             "count":    expiring,
#             "subtitle": expiring_subtitle
#         },
#         "po_count": {
#             "count":    po_count,
#             "subtitle": "Total purchase orders"
#         },
#         "bids_in_progress": {
#             "count":    inprogress_count,
#             "subtitle": inprogress_subtitle
#         },
#         "bids_won": {
#             "count":    bids_won,
#             "subtitle": "Total accepted bids"
#         }
#     }

from app.db.base import get_connection,get_d365_connection
from typing import Dict, Any, List
import json


def _get_approved_items(vendor_account: str) -> List[str]:
    try:
        # with get_connection() as conn:
        with get_d365_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT ITEMID
                FROM PDSAPPROVEDVENDORLIST WITH (NOLOCK)
                WHERE PDSAPPROVEDVENDOR = ?
                  AND DATAAREAID        = 'hi-q'
                  AND VALIDFROM        <= GETUTCDATE()
                  AND VALIDTO          >= GETUTCDATE()
            """, (vendor_account,))
            return [str(r[0]).strip().upper() for r in cur.fetchall()]
    except Exception as e:
        print(f"[APPROVED VENDOR] D365 fetch error for {vendor_account}: {e}")
        return []
from typing import Dict, Any
from app.db.base import get_connection, get_d365_connection
from app.services.rfq_submissionservice import fetch_submitted_rfqs
from app.services.rfq_inprogressservice import fetch_inprogress_rfqs


# ============================================================
# RFQ SUMMARY
# ============================================================
def fetch_rfq_summary(vendor_account: str) -> Dict[str, Any]:

    # ============================================================
    # STEP 1
    # PORTAL DB
    # ============================================================
    with get_connection() as conn:

        cur = conn.cursor()

        # ALL RFQ REPLIES
        cur.execute(f"""
            SELECT
                RFQID,
                RFQCASEID,
                SUBMISSIONSTATUS,
                DRAFTLINECOUNT

            FROM {RFQ_REPLIES_TABLE}  WITH (NOLOCK)

            WHERE VENDORACCOUNT = ?
        """, (vendor_account,))

        portal_rows = cur.fetchall()


    # ============================================================
    # MAPS
    # ============================================================
    replied_rfq_ids = set()
    submitted_rfq_ids = set()
    partial_expired_caseids = set()

    for r in portal_rows:

        rfq_id = str(r[0]).strip().upper()
        rfq_caseid = str(r[1]).strip().upper()

        replied_rfq_ids.add(rfq_id)

        if r[2] == 1:
            submitted_rfq_ids.add(rfq_id)

        if r[2] == 1 and (r[3] or 0) > 0:
            partial_expired_caseids.add(rfq_caseid)


    # ============================================================
    # STEP 2
    # D365 DB
    # ============================================================
    with get_d365_connection() as conn:

        cur = conn.cursor()

        cur.execute("""
            SELECT
                L.RFQCASEID,
                T.RFQID,
                L.EXPIRYDATETIME

            FROM PurchRFQCaseTable L WITH (NOLOCK)

            INNER JOIN PurchRFQTable T WITH (NOLOCK)
                ON T.RFQCASEID = L.RFQCASEID
               AND T.VENDACCOUNT = ?

            WHERE EXISTS (
                SELECT 1
                FROM PurchRFQCaseLine CL WITH (NOLOCK)

                INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
                    ON AVL.ITEMID = CL.ITEMID
                   AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
                   AND AVL.VALIDFROM <= GETUTCDATE()
                   AND AVL.VALIDTO >= GETUTCDATE()

                WHERE CL.RFQCASEID = L.RFQCASEID
            )
        """, (vendor_account,))

        rows = cur.fetchall()


    # ============================================================
    # COUNTS
    # ============================================================
    from datetime import datetime, timedelta

    # today = datetime.utcnow().date()
    today=(datetime.utcnow()+timedelta(minutes=330)).date()
    closing_limit = today + timedelta(days=3)

    new_count = 0
    closing_soon = 0
    expired = 0

    for row in rows:

        rfq_caseid = str(row[0]).strip().upper()
        rfq_id = str(row[1]).strip().upper()
        expiry = row[2]

        if not expiry:
            continue

        expiry_date = expiry.date()


        # ========================================================
        # NEW
        # ========================================================
        if (
            expiry_date >= today
            and rfq_id not in replied_rfq_ids
        ):
            new_count += 1


        # ========================================================
        # CLOSING SOON
        # ========================================================
        expiry_date=(expiry+timedelta(minutes=330)).date()
        if (
            expiry_date >= today
            and expiry_date <= closing_limit
        ):
            closing_soon += 1


        # ========================================================
        # EXPIRED
        # ========================================================
        if expiry_date < today:

            # no response
            if rfq_id not in replied_rfq_ids:
                expired += 1

            # partial submitted
            elif rfq_caseid in partial_expired_caseids:
                expired += 1


    # ============================================================
    # SUBMITTED
    # ============================================================
    submitted = len(fetch_submitted_rfqs(vendor_account))

    # ============================================================
    # INPROGRESS
    # ============================================================
    inprogress_count = len(fetch_inprogress_rfqs(vendor_account))

    # ============================================================
    # TOTAL ACTIVE
    # ============================================================
    total_active = (
        new_count
        + inprogress_count
        + submitted
    )

    # ============================================================
    # TOTAL RFQ COUNT
    # ============================================================
    total_rfq_count = len(rows)


    # ============================================================
    # RESPONSE
    # ============================================================
    return {

        "total_active_rfqs": {
            "count": total_active,
            "subtitle": "New, In Progress and Submitted"
        },

        "rfqs_closing_soon": {
            "count": closing_soon,
            "subtitle": "Closing within 3 days"
        },

        "submitted_bids": {
            "count": submitted,
            "subtitle": "Total quotations you have submitted"
        },

        "Expired_bids": {
            "count": expired,
            "subtitle": "Oops! Bid window closed without your response"
        },

        "Total_RFQ_Counts": {
            "count": total_rfq_count,
            "subtitle": "Total RFQs Received"
        }
    }


# ============================================================
# RFQ TAB COUNTS
# ============================================================
def fetch_rfq_counts(vendor_account: str) -> dict:

    # ============================================================
    # PORTAL DB
    # ============================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT
                RFQID,
                RFQCASEID,
                SUBMISSIONSTATUS,
                DRAFTLINECOUNT

            FROM {RFQ_REPLIES_TABLE}  WITH (NOLOCK)

            WHERE VENDORACCOUNT = ?
        """, (vendor_account,))

        portal_rows = cur.fetchall()


    replied_rfq_ids = set()
    submitted_rfq_ids = set()
    partial_expired_caseids = set()

    for r in portal_rows:

        rfq_id = str(r[0]).strip().upper()
        rfq_caseid = str(r[1]).strip().upper()

        replied_rfq_ids.add(rfq_id)

        if r[2] == 1:
            submitted_rfq_ids.add(rfq_id)

        if r[2] == 1 and (r[3] or 0) > 0:
            partial_expired_caseids.add(rfq_caseid)


    # ============================================================
    # D365 DB
    # ============================================================
    with get_d365_connection() as conn:

        cur = conn.cursor()

        cur.execute("""
            SELECT
                L.RFQCASEID,
                T.RFQID,
                L.EXPIRYDATETIME

            FROM PurchRFQCaseTable L WITH (NOLOCK)

            INNER JOIN PurchRFQTable T WITH (NOLOCK)
                ON T.RFQCASEID = L.RFQCASEID
               AND T.VENDACCOUNT = ?

            WHERE EXISTS (
                SELECT 1
                FROM PurchRFQCaseLine CL WITH (NOLOCK)

                INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
                    ON AVL.ITEMID = CL.ITEMID
                   AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
                   AND AVL.VALIDFROM <= GETUTCDATE()
                   AND AVL.VALIDTO >= GETUTCDATE()

                WHERE CL.RFQCASEID = L.RFQCASEID
            )
        """, (vendor_account,))

        rows = cur.fetchall()


    # ============================================================
    # COUNTS
    # ============================================================
    from datetime import datetime

    today = datetime.utcnow().date()

    new_count = 0
    expired_count = 0

    for row in rows:

        rfq_caseid = str(row[0]).strip().upper()
        rfq_id = str(row[1]).strip().upper()
        expiry = row[2]

        if not expiry:
            continue

        expiry_date = expiry.date()


        # ========================================================
        # NEW
        # ========================================================
        if (
            expiry_date >= today
            and rfq_id not in replied_rfq_ids
        ):
            new_count += 1


        # ========================================================
        # EXPIRED
        # ========================================================
        if expiry_date < today:

            if rfq_id not in replied_rfq_ids:
                expired_count += 1

            elif rfq_caseid in partial_expired_caseids:
                expired_count += 1


    # ============================================================
    # IN PROGRESS
    # ============================================================
    inprogress_count = len(
        fetch_inprogress_rfqs(vendor_account)
    )

    # ============================================================
    # SUBMITTED
    # ============================================================
    submitted_count = len(
        fetch_submitted_rfqs(vendor_account)
    )

    # ============================================================
    # COMPLETED
    # ============================================================
    completed_count = len(
        submitted_rfq_ids
    ) - submitted_count

    if completed_count < 0:
        completed_count = 0


    # ============================================================
    # TOTAL
    # ============================================================
    total_rfq_count = len(rows)


    # ============================================================
    # RESPONSE
    # ============================================================
    return {

        "new":
            new_count,

        "in_progress":
            inprogress_count,

        "submitted":
            submitted_count,

        "completed":
            completed_count,

        "expired":
            expired_count,

        "total":
            total_rfq_count
    }

# def fetch_rfq_summary(vendor_account: str) -> Dict[str, Any]:

#     approved_items = _get_approved_items(vendor_account)

#     with get_connection() as conn:
#         cur = conn.cursor()

#         # ── 1. New ────────────────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(DISTINCT T.RFQID)
#             FROM PurchRFQCaseTable L WITH (NOLOCK)
#             INNER JOIN PurchRFQTable T WITH (NOLOCK)
#                 ON  T.RFQCASEID   = L.RFQCASEID
#                 AND T.VENDACCOUNT = ?
#             WHERE CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) >= CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
#            -- WHERE L.EXPIRYDATETIME >= GETUTCDATE()
#               AND NOT EXISTS (
#                   SELECT 1 FROM HIQ_VENDORRFQREPLIES R WITH (NOLOCK)
#                   WHERE R.RFQ_ID         = T.RFQID
#                     AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
#               )
#               AND EXISTS (
#                   SELECT 1
#                   FROM PurchRFQCaseLine CL WITH (NOLOCK)
#                   INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                       ON  AVL.ITEMID            = CL.ITEMID
#                       AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                       AND AVL.VALIDFROM        <= GETUTCDATE()
#                       AND AVL.VALIDTO          >= GETUTCDATE()
#                   WHERE CL.RFQCASEID = L.RFQCASEID
#               )
#         """, (vendor_account,))
#         new_count = int(cur.fetchone()[0] or 0)

#         # ── 2. In Progress ────────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(DISTINCT R.RFQ_ID)
#             FROM HIQ_VENDORRFQREPLIES R WITH (NOLOCK)
#             LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
#                 ON L.RFQCASEID = R.RFQ_CASE_ID
#             WHERE R.VENDOR_ACCOUNT    = ?
#               AND R.SUBMISSION_STATUS = 0
#             AND CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) >= CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
#             --AND CAST(L.EXPIRYDATETIME AS DATE) >= CAST(GETUTCDATE() AS DATE)
#         """, (vendor_account,))
#         inprogress_count = int(cur.fetchone()[0] or 0)

#         # ── 3. Submitted — EXACT SAME LOGIC as fetch_submitted_rfqs ──
#                # ── 3. Submitted — FIXED (MATCHES HEADER EXACTLY) ──
#         # submitted = 0

#         # # ✅ STEP 1: get UNIQUE RFQ IDs (FIX: DISTINCT)
#         # cur.execute("""
#         #     SELECT DISTINCT R.RFQ_ID
#         #     FROM HIQ_VENDORRFQREPLIES R WITH (NOLOCK)
#         #     WHERE R.VENDOR_ACCOUNT    = ?
#         #       AND R.SUBMISSION_STATUS = 1
#         # """, (vendor_account,))

#         # # ✅ FIX: deduplicate + normalize
#         # submitted_rfq_ids = list(set(
#         #     str(r[0]).strip().upper() for r in cur.fetchall()
#         # ))

#         # for rfq_id in submitted_rfq_ids:

#         #     # ✅ STEP 2: get latest payload
#         #     cur.execute("""
#         #         SELECT TOP 1 PAYLOAD_JSON
#         #         FROM HIQ_VENDORRFQREPLIES WITH (NOLOCK)
#         #         WHERE UPPER(RFQ_ID)         = UPPER(?)
#         #           AND UPPER(VENDOR_ACCOUNT) = UPPER(?)
#         #         ORDER BY ID DESC
#         #     """, (rfq_id, vendor_account))

#         #     payload_row = cur.fetchone()

#         #     # ✅ FIX: skip OLD RFQs (match header)
#         #     if not payload_row or not payload_row[0]:
#         #         continue

#         #     try:
#         #         payload = json.loads(payload_row[0])
#         #     except Exception:
#         #         continue

#         #     items_in_payload = payload.get("Item", [])

#         #     # check if lineStatus exists
#         #     has_line_status_field = any(
#         #         "lineStatus" in item for item in items_in_payload
#         #     )

#         #     if not has_line_status_field:
#         #         # OLD STRUCTURE → take all items
#         #         valid_items = set(
#         #             str(item.get("itemNumber") or "").strip().upper()
#         #             for item in items_in_payload
#         #             if item.get("itemNumber")
#         #         )
#         #     else:
#         #         # NEW STRUCTURE → only lineStatus=True
#         #         valid_items = set()
#         #         for item in items_in_payload:
#         #             ls = item.get("lineStatus")
#         #             if ls is True or str(ls).lower() == "true":
#         #                 iid = str(item.get("itemNumber") or "").strip().upper()
#         #                 if iid:
#         #                     valid_items.add(iid)

#         #     # skip if nothing valid
#         #     if not valid_items:
#         #         continue

#         #     # ✅ STEP 3: D365 check (STATUS < 3)
#         #     cur.execute("""
#         #         SELECT LTRIM(RTRIM(ITEMID)) AS ITEMID, STATUS
#         #         FROM PURCHRFQLINE WITH (NOLOCK)
#         #         WHERE RFQID      = ?
#         #           AND DATAAREAID = 'hi-q'
#         #     """, (rfq_id,))

#         #     lines = cur.fetchall()

#         #     is_submitted = any(
#         #         str(l[0]).strip().upper() in valid_items and l[1] < 3
#         #         for l in lines
#         #     )

#         #     if is_submitted:
#         #         submitted += 1
        
#         # ── total_active = new + inprogress + submitted ───────
#         submitted = len(fetch_submitted_rfqs(vendor_account))
#         total_active = new_count + inprogress_count + submitted

#         # ── 4. Closing Soon ───────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(DISTINCT T.RFQID)
#             FROM PurchRFQCaseTable L WITH (NOLOCK)
#             INNER JOIN PurchRFQTable T WITH (NOLOCK)
#                 ON  T.RFQCASEID   = L.RFQCASEID
#                 AND T.VENDACCOUNT = ?
#             WHERE DATEADD(MINUTE,330,L.EXPIRYDATETIME) >= DATEADD(MINUTE,330,GETUTCDATE())
#             AND DATEADD(MINUTE,330,L.EXPIRYDATETIME) <= DATEADD(MINUTE,330,DATEADD(DAY,3,GETUTCDATE()))
#            -- WHERE L.EXPIRYDATETIME >= GETUTCDATE()
#             --AND L.EXPIRYDATETIME <= DATEADD(DAY, 3, GETUTCDATE())
#               AND NOT EXISTS (
#                   SELECT 1 FROM HIQ_VENDORRFQREPLIES R WITH (NOLOCK)
#                   WHERE R.RFQ_ID          = T.RFQID
#                     AND R.VENDOR_ACCOUNT  = T.VENDACCOUNT
#                     AND R.SUBMISSION_STATUS = 1
#               )
#               AND EXISTS (
#                   SELECT 1
#                   FROM PurchRFQCaseLine CL WITH (NOLOCK)
#                   INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                       ON  AVL.ITEMID            = CL.ITEMID
#                       AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                       AND AVL.VALIDFROM        <= GETUTCDATE()
#                       AND AVL.VALIDTO          >= GETUTCDATE()
#                   WHERE CL.RFQCASEID = L.RFQCASEID
#               )
#         """, (vendor_account,))
#         closing_soon = int(cur.fetchone()[0] or 0)

#         # ── 5. Expired ────────────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(*)
#             FROM PurchRFQCaseTable L WITH (NOLOCK)
#             INNER JOIN PurchRFQTable T WITH (NOLOCK)
#                 ON  T.RFQCASEID   = L.RFQCASEID
#                 AND T.VENDACCOUNT = ?
#             --WHERE L.EXPIRYDATETIME < GETUTCDATE()
#             WHERE CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) < CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
#             AND (
#                 NOT EXISTS (
#                     SELECT 1
#                     FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
#                     WHERE R.RFQ_CASE_ID    = L.RFQCASEID
#                       AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
#                 )
#                 OR
#                 EXISTS (
#                     SELECT 1
#                     FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
#                     WHERE R.RFQ_CASE_ID       = L.RFQCASEID
#                       AND R.VENDOR_ACCOUNT    = T.VENDACCOUNT
#                       AND R.SUBMISSION_STATUS = 1
#                       AND R.DRAFTLINECOUNT    > 0
#                 )
#             )
#             AND EXISTS (
#                 SELECT 1
#                 FROM PurchRFQCaseLine CL WITH (NOLOCK)
#                 INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                     ON  AVL.ITEMID            = CL.ITEMID
#                     AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                     AND AVL.DATAAREAID        = L.DATAAREAID
#                 WHERE CL.RFQCASEID = L.RFQCASEID
#             )
#         """, (vendor_account,))
#         expired = int(cur.fetchone()[0] or 0)

#         # ── 6. Total RFQ Count ────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(DISTINCT T.RFQID)
#             FROM PurchRFQCaseTable L WITH (NOLOCK)
#             INNER JOIN PurchRFQTable T WITH (NOLOCK)
#                 ON  T.RFQCASEID   = L.RFQCASEID
#                 AND T.VENDACCOUNT = ?
#             WHERE EXISTS (
#                 SELECT 1
#                 FROM PurchRFQCaseLine CL WITH (NOLOCK)
#                 INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                     ON  AVL.ITEMID            = CL.ITEMID
#                     AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                     AND AVL.VALIDFROM        <= GETUTCDATE()
#                     AND AVL.VALIDTO          >= GETUTCDATE()
#                 WHERE CL.RFQCASEID = L.RFQCASEID
#             )
#         """, (vendor_account,))
#         total_rfq_count = int(cur.fetchone()[0] or 0)

#     return {
#         "total_active_rfqs": {
#             "count":    total_active,
#             "subtitle": "New, In Progress and Submitted"
#         },
#         "rfqs_closing_soon": {
#             "count":    closing_soon,
#             "subtitle": "Closing within 3 days"
#         },
#         "submitted_bids": {
#             "count":    submitted,
#             "subtitle": "Total quotations you have submitted"
#         },
#         "Expired_bids": {
#             "count":    expired,
#             "subtitle": "Oops! Bid window closed without your response"
#         },
#         "Total_RFQ_Counts": {
#             "count":    total_rfq_count,
#             "subtitle": "Total RFQs Received"
#         }
#     }

# def fetch_rfq_counts(vendor_account: str) -> dict:
#     """
#     Returns count for all RFQ tabs in one API call:
#     New, In Progress, Submitted, Completed Bid Status, Expired
#     """

#     with get_connection() as conn:
#         cur = conn.cursor()

#         # ── NEW ───────────────────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(DISTINCT T.RFQID)
#             FROM PurchRFQCaseTable L WITH (NOLOCK)
#             INNER JOIN PurchRFQTable T WITH (NOLOCK)
#                 ON  T.RFQCASEID   = L.RFQCASEID
#                 AND T.VENDACCOUNT = ?
#             WHERE CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) >= CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
#             --WHERE CAST(L.EXPIRYDATETIME AS DATE) >= CAST(GETDATE() AS DATE)
#               AND EXISTS (
#                   SELECT 1
#                   FROM PurchRFQCaseLine CL WITH (NOLOCK)
#                   INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                       ON  AVL.ITEMID            = CL.ITEMID
#                       AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                       AND AVL.VALIDFROM        <= GETUTCDATE()
#                       AND AVL.VALIDTO          >= GETUTCDATE()
#                   WHERE CL.RFQCASEID = L.RFQCASEID
#               )
#               AND NOT EXISTS (
#                   SELECT 1
#                   FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
#                   WHERE R.RFQ_ID         = T.RFQID
#                     AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
#               )
#         """, (vendor_account,))
#         new_count = int(cur.fetchone()[0] or 0)

#         # ── IN PROGRESS ───────────────────────────────────────
#         # cur.execute("""
#         #     SELECT COUNT(DISTINCT T.RFQID)
#         #     FROM PurchRFQCaseTable L WITH (NOLOCK)
#         #     INNER JOIN PurchRFQTable T WITH (NOLOCK)
#         #         ON  T.RFQCASEID   = L.RFQCASEID
#         #         AND T.VENDACCOUNT = ?
#         #     INNER JOIN (
#         #         SELECT RFQ_ID, VENDOR_ACCOUNT,
#         #             ROW_NUMBER() OVER (
#         #                 PARTITION BY RFQ_ID, VENDOR_ACCOUNT
#         #                 ORDER BY ID DESC
#         #             ) AS RN,
#         #             SUBMISSION_STATUS
#         #         FROM HIQ_VendorRFQReplies WITH (NOLOCK)
#         #         WHERE SUBMISSION_STATUS IN (0, 2)
#         #     ) R
#         #         ON  R.RFQ_ID         = T.RFQID
#         #         AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
#         #         AND R.RN             = 1
#         #     WHERE (
#         #         L.EXPIRYDATETIME >= GETUTCDATE()
#         #         OR R.SUBMISSION_STATUS = 2
#         #     )
#         # """, (vendor_account,))
#         # inprogress_count = int(cur.fetchone()[0] or 0)
#         inprogress_count = len(fetch_inprogress_rfqs(vendor_account))

#         # ── SUBMITTED ─────────────────────────────────────────  # ── FIXED
#         submitted_count = len(fetch_submitted_rfqs(vendor_account))
#             # cur.execute(f"""
#             #     SELECT COUNT(DISTINCT R.RFQ_ID)
#             #     FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
#             #     WHERE R.VENDOR_ACCOUNT    = ?
#             #       AND R.SUBMISSION_STATUS = 1
#             #       AND EXISTS (
#             #           SELECT 1
#             #           FROM PURCHRFQREPLYLINE RL WITH (NOLOCK)
#             #           INNER JOIN PURCHRFQLINE PL WITH (NOLOCK)
#             #               ON  PL.RECID      = RL.RFQLINERECID
#             #               AND PL.DATAAREAID = 'hi-q'
#             #           WHERE RL.RFQID      = R.RFQ_ID
#             #             AND RL.DATAAREAID = 'hi-q'
#             #             AND PL.STATUS     < 3
#             #             AND PL.ITEMID     IN ({placeholders})
#             #       )
#             # """, [vendor_account] + approved_items)
#             # submitted_count = int(cur.fetchone()[0] or 0)

#         # ── COMPLETED ─────────────────────────────────────────
#         cur.execute("""
#             SELECT COUNT(DISTINCT R.RFQ_ID)
#             FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
#             WHERE R.VENDOR_ACCOUNT    = ?
#               AND R.SUBMISSION_STATUS = 1
#               AND EXISTS (
#                   SELECT 1
#                   FROM PURCHRFQREPLYLINE RL WITH (NOLOCK)
#                   INNER JOIN PURCHRFQLINE PL WITH (NOLOCK)
#                       ON  PL.RECID      = RL.RFQLINERECID
#                       AND PL.DATAAREAID = 'hi-q'
#                   WHERE RL.RFQID      = R.RFQ_ID
#                     AND RL.DATAAREAID = 'hi-q'
#                     AND PL.STATUS     >= 3
#               )
#         """, (vendor_account,))
#         completed_count = int(cur.fetchone()[0] or 0)

#         # ── EXPIRED ───────────────────────────────────────────
#         cur.execute("""SELECT COUNT(*) AS EXPIRED_COUNT
# FROM PurchRFQCaseTable L WITH (NOLOCK)

# INNER JOIN PurchRFQTable T WITH (NOLOCK)
#     ON  T.RFQCASEID   = L.RFQCASEID
#     AND T.VENDACCOUNT = ?

# --WHERE L.EXPIRYDATETIME < GETUTCDATE()
# WHERE CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) < CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
# AND (
#     -- NO SUBMISSION
#     NOT EXISTS (
#         SELECT 1
#         FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
#         WHERE R.RFQ_CASE_ID    = L.RFQCASEID
#           AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
#     )

#     OR

#     -- PARTIAL SUBMISSION
#     EXISTS (
#         SELECT 1
#         FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
#         WHERE R.RFQ_CASE_ID    = L.RFQCASEID
#           AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
#           AND R.SUBMISSION_STATUS = 1
#           AND R.DRAFTLINECOUNT > 0
#     )
# )

# AND EXISTS (
#     SELECT 1
#     FROM PurchRFQCaseLine CL WITH (NOLOCK)
#     INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#         ON  AVL.ITEMID            = CL.ITEMID
#         AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#         AND AVL.DATAAREAID        = L.DATAAREAID
#     WHERE CL.RFQCASEID = L.RFQCASEID
# )

#         """, (vendor_account,))
#         expired_count = int(cur.fetchone()[0] or 0)

#         # ── TOTAL RFQ ───────────────────────────────────────
#         cur.execute("""
#         SELECT COUNT(DISTINCT T.RFQID)
#         FROM PurchRFQCaseTable L WITH (NOLOCK)
#         INNER JOIN PurchRFQTable T WITH (NOLOCK)
#             ON  T.RFQCASEID   = L.RFQCASEID
#             AND T.VENDACCOUNT = ?
#         WHERE EXISTS (
#             SELECT 1
#             FROM PurchRFQCaseLine CL WITH (NOLOCK)
#             INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                 ON  AVL.ITEMID            = CL.ITEMID
#                 AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                 AND AVL.VALIDFROM        <= GETUTCDATE()
#                 AND AVL.VALIDTO          >= GETUTCDATE()
#             WHERE CL.RFQCASEID = L.RFQCASEID
#         )
#     """, (vendor_account,))

#         total_rfq_count = int(cur.fetchone()[0] or 0) 

#     return {
#         "new":               new_count,
#         "in_progress":       inprogress_count,
#         "submitted":         submitted_count,
#         "completed":         completed_count,
#         "expired":           expired_count,
#         "total":             total_rfq_count
#     }

