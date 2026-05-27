from app.db.base import (
    get_connection
)

from typing import (
    Dict,
    Any,
    List
)

from app.services.rfq_submissionservice import (
    fetch_submitted_rfqs
)

from app.services.rfq_inprogressservice import (
    fetch_inprogress_rfqs
)
from app.services.rfq_completedservice import (fetch_completed_rfqs)
from datetime import (
    datetime,
    timedelta
)

from app.core.config import (
    settings
)

import json


SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = (
    f"{SCHEMA}.HIQ_VendorRFQReplies"
)


# ============================================================
# APPROVED ITEMS
# ============================================================
def _get_approved_items(
    vendor_account: str
) -> List[str]:

    try:

        with get_connection() as conn:

            cur = conn.cursor()

            cur.execute("""
                SELECT

                    ITEMID

                FROM {SCHEMA}.D365_PDSAPPROVEDVENDORLIST
                WITH (NOLOCK)

                WHERE PDSAPPROVEDVENDOR = ?

                  AND VALIDFROM <= GETUTCDATE()

                  AND VALIDTO >= GETUTCDATE()
            """, (vendor_account,))

            return [

                str(r[0]).strip().upper()

                for r in cur.fetchall()
            ]

    except Exception as e:

        print(
            f"[APPROVED VENDOR] "
            f"fetch error for "
            f"{vendor_account}: {e}"
        )

        return []


# ============================================================
# DASHBOARD METRICS
# ============================================================
def fetch_dashboard_metrics(
    vendor_account: str
) -> Dict[str, Any]:

    # ========================================================
    # RFQ EXPIRING
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT

                T.RFQID,

                L.EXPIRYDATETIME

            FROM {SCHEMA}.D365_PURCHRFQCASETABLE L
            WITH (NOLOCK)

            INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T
            WITH (NOLOCK)

                ON T.RFQCASEID = L.RFQCASEID
               AND T.VENDACCOUNT = ?

            WHERE CAST(
                    DATEADD(
                        MINUTE,
                        330,
                        L.EXPIRYDATETIME
                    ) AS DATE
                  )

                  >=

                  CAST(
                    DATEADD(
                        MINUTE,
                        330,
                        GETUTCDATE()
                    ) AS DATE
                  )

              AND EXISTS (

                    SELECT 1

                    FROM {SCHEMA}.D365_PURCHRFQCASELINE CL
                    WITH (NOLOCK)

                    INNER JOIN {SCHEMA}.D365_PDSAPPROVEDVENDORLIST AVL
                    WITH (NOLOCK)

                        ON AVL.ITEMID = CL.ITEMID
                       AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
                       AND AVL.VALIDFROM <= GETUTCDATE()
                       AND AVL.VALIDTO >= GETUTCDATE()

                    WHERE CL.RFQCASEID = L.RFQCASEID
              )
        """, (vendor_account,))

        expiry_rows = cur.fetchall()

        expiring = len(expiry_rows)

        today = (
            datetime.utcnow()
            + timedelta(minutes=330)
        ).date()

        tomorrow = (
            today + timedelta(days=1)
        )

        closing_today = 0

        closing_tomorrow = 0

        for r in expiry_rows:

            expiry = r[1]

            if not expiry:
                continue

            expiry_date = (
                expiry
                + timedelta(minutes=330)
            ).date()

            if expiry_date == today:

                closing_today += 1

            elif expiry_date == tomorrow:

                closing_tomorrow += 1


        # ====================================================
        # PO COUNT
        # ====================================================
        cur.execute(f"""
            SELECT

                COUNT(DISTINCT PURCHID)

            FROM {SCHEMA}.D365_PURCHTABLE
            WITH (NOLOCK)

            WHERE ORDERACCOUNT = ?
        """, (vendor_account,))

        po_count = int(
            cur.fetchone()[0] or 0
        )


    # ========================================================
    # PORTAL DB
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT DISTINCT

                RFQID,

                RFQCASEID

            FROM {RFQ_REPLIES_TABLE}
            WITH (NOLOCK)

            WHERE VENDORACCOUNT = ?
              AND SUBMISSIONSTATUS = 0
        """, (vendor_account,))

        inprogress_rows = cur.fetchall()


    # ========================================================
    # IN PROGRESS
    # ========================================================
    inprogress_count = 0

    closes_today = 0

    closes_tomorrow = 0

    if inprogress_rows:

        rfq_case_ids = [

            r[1]

            for r in inprogress_rows
        ]

        placeholders = ",".join(
            ["?"] * len(rfq_case_ids)
        )

        with get_connection() as conn:

            cur = conn.cursor()

            cur.execute(f"""
                SELECT

                    RFQCASEID,

                    EXPIRYDATETIME

                FROM D365_PURCHRFQCASETABLE
                WITH (NOLOCK)

                WHERE RFQCASEID IN ({placeholders})

                  AND CAST(
                        DATEADD(
                            MINUTE,
                            330,
                            EXPIRYDATETIME
                        ) AS DATE
                      )

                      >=

                      CAST(
                        DATEADD(
                            MINUTE,
                            330,
                            GETUTCDATE()
                        ) AS DATE
                      )
            """, rfq_case_ids)

            rows = cur.fetchall()

            inprogress_count = len(rows)

            for row in rows:

                expiry = row[1]

                if not expiry:
                    continue

                expiry_date = (
                    expiry
                    + timedelta(minutes=330)
                ).date()

                if expiry_date == today:

                    closes_today += 1

                elif expiry_date == tomorrow:

                    closes_tomorrow += 1


    # ========================================================
    # BIDS WON
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT DISTINCT

                RFQID

            FROM {RFQ_REPLIES_TABLE}
            WITH (NOLOCK)

            WHERE VENDORACCOUNT = ?
              AND SUBMISSIONSTATUS = 1
        """, (vendor_account,))

        submitted_rfqs = [

            r[0]

            for r in cur.fetchall()
        ]


    bids_won = 0

    if submitted_rfqs:

        placeholders = ",".join(
            ["?"] * len(submitted_rfqs)
        )

        with get_connection() as conn:

            cur = conn.cursor()

            cur.execute(f"""
                SELECT

                    COUNT(DISTINCT RFQID)

                FROM {SCHEMA}.D365_PURCHRFQLINE
                WITH (NOLOCK)

                WHERE STATUS = 4

                  AND RFQID IN ({placeholders})
            """, submitted_rfqs)

            bids_won = int(
                cur.fetchone()[0] or 0
            )


    # ========================================================
    # SUBTITLE
    # ========================================================
    if closing_today > 0:

        expiring_subtitle = (
            f"{closing_today} closing today"
        )

    elif closing_tomorrow > 0:

        expiring_subtitle = (
            f"{closing_tomorrow} closing tomorrow"
        )

    else:

        expiring_subtitle = (
            "None closing today"
        )


    if closes_today > 0:

        inprogress_subtitle = (
            f"{closes_today} closing today"
        )

    elif closes_tomorrow > 0:

        inprogress_subtitle = (
            f"{closes_tomorrow} closing tomorrow"
        )

    else:

        inprogress_subtitle = (
            "No bids closing today"
        )


    return {

        "expiring_soon": {

            "count":
                expiring,

            "subtitle":
                expiring_subtitle
        },

        "po_count": {

            "count":
                po_count,

            "subtitle":
                "Total purchase orders"
        },

        "bids_in_progress": {

            "count":
                inprogress_count,

            "subtitle":
                inprogress_subtitle
        },

        "bids_won": {

            "count":
                bids_won,

            "subtitle":
                "Total accepted bids"
        }
    }


# ============================================================
# RFQ SUMMARY
# ============================================================
def fetch_rfq_summary(
    vendor_account: str
) -> Dict[str, Any]:

    # ========================================================
    # PORTAL DB
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT

                RFQID,

                RFQCASEID,

                SUBMISSIONSTATUS,

                DRAFTLINECOUNT

            FROM {RFQ_REPLIES_TABLE}
            WITH (NOLOCK)

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

            partial_expired_caseids.add(
                rfq_caseid
            )


    # ========================================================
    # RFQ DATA
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT

                L.RFQCASEID,

                T.RFQID,

                L.EXPIRYDATETIME

            FROM {SCHEMA}.D365_PURCHRFQCASETABLE L
            WITH (NOLOCK)

            INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T
            WITH (NOLOCK)

                ON T.RFQCASEID = L.RFQCASEID
               AND T.VENDACCOUNT = ?

            WHERE EXISTS (

                SELECT 1

                FROM {SCHEMA}.D365_PURCHRFQCASELINE CL
                WITH (NOLOCK)

                INNER JOIN {SCHEMA}.D365_PDSAPPROVEDVENDORLIST AVL
                WITH (NOLOCK)

                    ON AVL.ITEMID = CL.ITEMID
                   AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
                   AND AVL.VALIDFROM <= GETUTCDATE()
                   AND AVL.VALIDTO >= GETUTCDATE()

                WHERE CL.RFQCASEID = L.RFQCASEID
            )
        """, (vendor_account,))

        rows = cur.fetchall()


    today = (
        datetime.utcnow()
        + timedelta(minutes=330)
    ).date()

    closing_limit = (
        today + timedelta(days=3)
    )

    new_count = 0

    closing_soon = 0

    expired = 0

    for row in rows:

        rfq_caseid = str(row[0]).strip().upper()

        rfq_id = str(row[1]).strip().upper()

        expiry = row[2]

        if not expiry:
            continue

        expiry_date = (
            expiry + timedelta(minutes=330)
        ).date()

        # ====================================================
        # NEW
        # ====================================================
        if (

            expiry_date >= today

            and

            rfq_id not in replied_rfq_ids
        ):

            new_count += 1


        # ====================================================
        # CLOSING SOON
        # ====================================================
        if (

            expiry_date >= today

            and

            expiry_date <= closing_limit
        ):

            closing_soon += 1


        # ====================================================
        # EXPIRED
        # ====================================================
        if expiry_date < today:

            if rfq_id not in replied_rfq_ids:

                expired += 1

            elif rfq_caseid in partial_expired_caseids:

                expired += 1


    submitted = len(
        fetch_submitted_rfqs(
            vendor_account
        )
    )

    inprogress_count = len(
        fetch_inprogress_rfqs(
            vendor_account
        )
    )

    total_active = (

        new_count

        + inprogress_count

        + submitted
    )

    total_rfq_count = len(rows)


    return {

        "total_active_rfqs": {

            "count":
                total_active,

            "subtitle":
                "New, In Progress and Submitted"
        },

        "rfqs_closing_soon": {

            "count":
                closing_soon,

            "subtitle":
                "Closing within 3 days"
        },

        "submitted_bids": {

            "count":
                submitted,

            "subtitle":
                "Total quotations you have submitted"
        },

        "Expired_bids": {

            "count":
                expired,

            "subtitle":
                "Oops! Bid window closed without your response"
        },

        "Total_RFQ_Counts": {

            "count":
                total_rfq_count,

            "subtitle":
                "Total RFQs Received"
        }
    }


# ============================================================
# RFQ TAB COUNTS
# ============================================================
def fetch_rfq_counts(
    vendor_account: str
) -> dict:

    # ========================================================
    # PORTAL DB
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT

                RFQID,

                RFQCASEID,

                SUBMISSIONSTATUS,

                DRAFTLINECOUNT

            FROM {RFQ_REPLIES_TABLE}
            WITH (NOLOCK)

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

            partial_expired_caseids.add(
                rfq_caseid
            )


    # ========================================================
    # RFQ DATA
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT

                L.RFQCASEID,

                T.RFQID,

                L.EXPIRYDATETIME

            FROM {SCHEMA}.D365_PURCHRFQCASETABLE L
            WITH (NOLOCK)

            INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T
            WITH (NOLOCK)

                ON T.RFQCASEID = L.RFQCASEID
               AND T.VENDACCOUNT = ?

            WHERE EXISTS (

                SELECT 1

                FROM {SCHEMA}.D365_PURCHRFQCASELINE CL
                WITH (NOLOCK)

                INNER JOIN {SCHEMA}.D365_PDSAPPROVEDVENDORLIST AVL
                WITH (NOLOCK)

                    ON AVL.ITEMID = CL.ITEMID
                   AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
                   AND AVL.VALIDFROM <= GETUTCDATE()
                   AND AVL.VALIDTO >= GETUTCDATE()

                WHERE CL.RFQCASEID = L.RFQCASEID
            )
        """, (vendor_account,))

        rows = cur.fetchall()


    today = (
        datetime.utcnow()
        + timedelta(minutes=330)
    ).date()

    new_count = 0

    expired_count = 0

    for row in rows:

        rfq_caseid = str(row[0]).strip().upper()

        rfq_id = str(row[1]).strip().upper()

        expiry = row[2]

        if not expiry:
            continue

        expiry_date = (
            expiry + timedelta(minutes=330)
        ).date()

        # ====================================================
        # NEW
        # ====================================================
        if (

            expiry_date >= today

            and

            rfq_id not in replied_rfq_ids
        ):

            new_count += 1


        # ====================================================
        # EXPIRED
        # ====================================================
        if expiry_date < today:

            if rfq_id not in replied_rfq_ids:

                expired_count += 1

            elif rfq_caseid in partial_expired_caseids:

                expired_count += 1


    inprogress_count = len(
        fetch_inprogress_rfqs(
            vendor_account
        )
    )

    submitted_count = len(
        fetch_submitted_rfqs(
            vendor_account
        )
    )
    completed_count = len(
    fetch_completed_rfqs(
        vendor_account
    )
)


    

    # completed_count = (
    #     len(submitted_rfq_ids)
    #     - submitted_count
    # )

    # if completed_count < 0:

    #     completed_count = 0


    total_rfq_count = len(rows)


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

