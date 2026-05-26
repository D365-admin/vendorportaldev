from app.db.base import (
    get_connection
)

from app.utils.date_utils import (
    format_utc_iso
)
from app.core.config import settings
SCHEMA = settings.DB_SCHEMA

# ============================================================
# FETCH PO LIST
# ============================================================
def fetch_po_list(
    vendor_account: str
):

    query = f"""
        SELECT

            P.PURCHID,

            R.RFQID,

            P.DOCUMENTSTATE,

            P.CREATEDDATETIME,

            ISNULL(
                LT.TOTAL_AMOUNT,
                0
            ) AS TOTAL_AMOUNT,

            P.PURCHSTATUS

        FROM {SCHEMA}.D365_PURCHTABLE P
        WITH (NOLOCK)

        -- ====================================================
        -- PRE-AGGREGATE LINE AMOUNT
        -- ====================================================
        LEFT JOIN (

            SELECT

                PURCHID,

                SUM(LINEAMOUNT)
                    AS TOTAL_AMOUNT

            FROM {SCHEMA}.D365_PURCHLINE
            WITH (NOLOCK)

            GROUP BY PURCHID

        ) LT
            ON LT.PURCHID = P.PURCHID

        -- ====================================================
        -- SINGLE RFQID
        -- ====================================================
        LEFT JOIN (

            SELECT

                PURCHID,

                MAX(RFQID)
                    AS RFQID

            FROM {SCHEMA}.D365_PURCHRFQLINE
            WITH (NOLOCK)

            GROUP BY PURCHID

        ) R
            ON R.PURCHID = P.PURCHID

        WHERE P.ORDERACCOUNT = ?

        ORDER BY
            P.CREATEDDATETIME DESC
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            query,
            vendor_account
        )

        columns = [
            col[0]
            for col in cursor.description
        ]

        rows = cursor.fetchall()

        if not rows:
            return []

        return [
            dict(zip(columns, row))
            for row in rows
        ]


# ============================================================
# GET PO LIST
# ============================================================
def get_po_list(
    vendor_account: str
):

    data = fetch_po_list(
        vendor_account
    )

    if not data:
        return []

    result = []

    for row in data:

        # ====================================================
        # SAFE CONVERSION
        # ====================================================
        document_state = int(
            row.get(
                "DOCUMENTSTATE"
            ) or 0
        )

        purch_status = int(
            row.get(
                "PURCHSTATUS"
            ) or 0
        )

        # ====================================================
        # STATUS LOGIC
        # ====================================================
        if document_state != 40:

            final_status = "Open"

        else:

            if purch_status in (0, 1):

                final_status = "Confirmed"

            elif purch_status == 2:

                final_status = "Received"

            elif purch_status == 3:

                final_status = "Invoiced"

            elif purch_status == 4:

                final_status = "Cancelled"

            else:

                final_status = "Unknown"

        # ====================================================
        # RESPONSE
        # ====================================================
        result.append({

            "po_id":
                row.get("PURCHID"),

            "rfq_id":
                row.get("RFQID"),

            "created_date":
                format_utc_iso(
                    row.get(
                        "CREATEDDATETIME"
                    )
                ),

            "total_amount":
                float(
                    row.get(
                        "TOTAL_AMOUNT"
                    ) or 0
                ),

            "purch_state":
                final_status
        })

    return result


# ============================================================
# PO KPI
# ============================================================
def get_vendor_po_kpi(
    vendor_account: str
):

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT

                COUNT(*)
                    AS total_pos,

                -- ============================================
                -- OPEN
                -- ============================================
                SUM(

                    CASE

                        WHEN DOCUMENTSTATE != 40

                        THEN 1

                        ELSE 0

                    END

                ) AS open_pos,

                -- ============================================
                -- CONFIRMED
                -- ============================================
                SUM(

                    CASE

                        WHEN DOCUMENTSTATE = 40
                        AND PURCHSTATUS IN (0,1)

                        THEN 1

                        ELSE 0

                    END

                ) AS confirmed_pos,

                -- ============================================
                -- RECEIVED
                -- ============================================
                SUM(

                    CASE

                        WHEN DOCUMENTSTATE = 40
                        AND PURCHSTATUS = 2

                        THEN 1

                        ELSE 0

                    END

                ) AS received_pos,

                -- ============================================
                -- INVOICED
                -- ============================================
                SUM(

                    CASE

                        WHEN DOCUMENTSTATE = 40
                        AND PURCHSTATUS = 3

                        THEN 1

                        ELSE 0

                    END

                ) AS invoiced_pos,

                -- ============================================
                -- CANCELLED
                -- ============================================
                SUM(

                    CASE

                        WHEN DOCUMENTSTATE = 40
                        AND PURCHSTATUS = 4

                        THEN 1

                        ELSE 0

                    END

                ) AS cancelled_pos

            FROM {SCHEMA}.D365_PURCHTABLE
            WITH (NOLOCK)

            WHERE ORDERACCOUNT = ?
        """, (vendor_account,))

        row = cur.fetchone()

        return {

            "vendor_account":
                vendor_account,

            "total_pos":
                row[0] or 0,

            "open_pos":
                row[1] or 0,

            "confirmed_pos":
                row[2] or 0,

            "received_pos":
                row[3] or 0,

            "invoiced_pos":
                row[4] or 0,

            "cancelled_pos":
                row[5] or 0
        }

# from app.db.base import get_connection,get_connection
# from app.utils.date_utils import format_utc_iso,format_date


# # ==========================================
# # FETCH FROM DB
# # ==========================================
# def fetch_po_list(vendor_account: str):
#     query = """
#         SELECT 
#     P.PURCHID,
#     R.RFQID,
#     P.DOCUMENTSTATE,
#     P.CREATEDDATETIME,
#     ISNULL(LT.TOTAL_AMOUNT, 0) AS TOTAL_AMOUNT,
#     P.PURCHSTATUS

# FROM PURCHTABLE P WITH (NOLOCK)

# -- PRE-AGGREGATE LINE AMOUNT (NO DUPLICATION)
# LEFT JOIN (
#     SELECT 
#         PURCHID,
#         SUM(LINEAMOUNT) AS TOTAL_AMOUNT
#     FROM PURCHLINE WITH (NOLOCK)
#     GROUP BY PURCHID
# ) LT ON LT.PURCHID = P.PURCHID

# -- GET SINGLE RFQID (IMPORTANT)
# LEFT JOIN (
#     SELECT 
#         PURCHID,
#         MAX(RFQID) AS RFQID
#     FROM PURCHRFQLINE WITH (NOLOCK)
#     GROUP BY PURCHID
# ) R ON R.PURCHID = P.PURCHID

# WHERE P.ORDERACCOUNT = ?

# ORDER BY P.CREATEDDATETIME DESC
#     """
#     with get_connection() as conn:
#     # with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute(query, vendor_account)

#         columns = [col[0] for col in cursor.description]
#         rows = cursor.fetchall()

#         if not rows:
#             return []

#         return [dict(zip(columns, row)) for row in rows]


# # ==========================================
# # BUSINESS LOGIC
# # ==========================================
# def get_po_list(vendor_account: str):
#     data = fetch_po_list(vendor_account)

#     if not data:
#         return []

#     result = []

#     for row in data:
#         # ✅ SAFE CONVERSION
#         document_state = int(row.get("DOCUMENTSTATE") or 0)
#         purch_status = int(row.get("PURCHSTATUS") or 0)

#         # ==========================================
#         # ✅ RULE LOGIC
#         # ==========================================
#         if document_state != 40:
#             final_status = "Open"
#         else:
#             if purch_status in (0, 1):
#                 final_status = "Confirmed"
#             elif purch_status == 2:
#                 final_status = "Received"
#             elif purch_status == 3:
#                 final_status = "Invoiced"
#             elif purch_status == 4:
#                 final_status = "Cancelled"
#             else:
#                 final_status = "Unknown"

#         # ==========================================
#         # RESPONSE FORMAT
#         # ==========================================
#         result.append({
#             "po_id": row.get("PURCHID"),
#             "rfq_id": row.get("RFQID"),
#             "created_date": format_utc_iso(row.get("CREATEDDATETIME")),
#             "total_amount": float(row.get("TOTAL_AMOUNT") or 0),
#             "purch_state": final_status
#         })

#     return result
# def get_vendor_po_kpi(vendor_account: str):
#     with get_connection() as conn:
#     # with get_connection() as conn:
#         cur = conn.cursor()

#         cur.execute("""
#             SELECT 
#                 COUNT(*) AS total_pos,

#                 -- OPEN (ONLY DOCUMENTSTATE)
#                 SUM(CASE 
#                     WHEN DOCUMENTSTATE != 40 THEN 1 
#                     ELSE 0 
#                 END) AS open_pos,

#                 -- CONFIRMED
#                 SUM(CASE 
#                     WHEN DOCUMENTSTATE = 40 AND PURCHSTATUS IN (0,1) THEN 1 
#                     ELSE 0 
#                 END) AS confirmed_pos,

#                 -- RECEIVED
#                 SUM(CASE 
#                     WHEN DOCUMENTSTATE = 40 AND PURCHSTATUS = 2 THEN 1 
#                     ELSE 0 
#                 END) AS received_pos,

#                 -- INVOICED
#                 SUM(CASE 
#                     WHEN DOCUMENTSTATE = 40 AND PURCHSTATUS = 3 THEN 1 
#                     ELSE 0 
#                 END) AS invoiced_pos,

#                 -- CANCELLED
#                 SUM(CASE 
#                     WHEN DOCUMENTSTATE = 40 AND PURCHSTATUS = 4 THEN 1 
#                     ELSE 0 
#                 END) AS cancelled_pos

#             FROM PURCHTABLE
#             WHERE DATAAREAID = 'hi-q'
#               AND ORDERACCOUNT = ?
#         """, (vendor_account,))

#         row = cur.fetchone()

#         return {
#             "vendor_account": vendor_account,
#             "total_pos": row[0] or 0,
#             "open_pos": row[1] or 0,
#             "confirmed_pos": row[2] or 0,
#             "received_pos": row[3] or 0,
#             "invoiced_pos": row[4] or 0,
#             "cancelled_pos": row[5] or 0
#         }

# # from app.db.base import get_connection
# # from app.utils.date_utils import format_utc_iso

# # def fetch_po_list(vendor_account: str):
# #     query = """
# #         SELECT 
# #     P.PURCHID,
# #     R.RFQID,
# #     --P.DOCUMENTSTATE,
# #     P.CREATEDDATETIME,
# #     SUM(L.LINEAMOUNT) AS TOTAL_AMOUNT,
# #     p.PURCHSTATUS

# # FROM PURCHTABLE P WITH (NOLOCK)

# # LEFT JOIN PURCHLINE L WITH (NOLOCK)
# #     ON L.PURCHID = P.PURCHID

# # LEFT JOIN PURCHRFQLINE R WITH (NOLOCK)
# #     ON R.PURCHID = P.PURCHID  
# # WHERE  P.ORDERACCOUNT = ? 
# # ---P.DOCUMENTSTATE in (40,30) 
# # GROUP BY 
# #     P.PURCHID,
# #     R.RFQID,
# #     P.DOCUMENTSTATE,
# #     p.PURCHSTATUS,
# #     P.CREATEDDATETIME 
# # ORDER BY P.CREATEDDATETIME DESC
# #     """

# #     with get_connection() as conn:
# #         cursor = conn.cursor()
# #         cursor.execute(query, vendor_account)

# #         columns = [col[0] for col in cursor.description]
# #         rows = cursor.fetchall()
# #         if not rows:
# #             return []  

# #         return [dict(zip(columns, row)) for row in rows]


# # def get_po_list(vendor_account: str):
# #     data = fetch_po_list(vendor_account)

# #     result = []
# #     if not data:
# #             return []  

# #     # DocumentState Mapping
# #     DOCUMENT_STATE_MAP = {
# #         0: "Draft",
# #         10: "InReview",
# #         20: "Rejected",
# #         30: "Approved",
# #         35: "InExternalReview",
# #         40: "Confirmed",
# #         50: "Finalized"
# #     }
# #     PURCH_STATUS_MAP = {
# #     0: "Confirmed",
# #     1: "Confirmed",
# #     2: "Received",
# #     3: "Invoiced",
# #     4: "cancelled"
# # }

# #     # for row in data:
# #     #     result.append({
# #     #         "po_id": row["PURCHID"],
# #     #         "rfq_id": row["RFQID"],
# #     #         "created_date": format_utc_iso(row["CREATEDDATETIME"]),
# #     #         # "status": DOCUMENT_STATE_MAP.get(row["DOCUMENTSTATE"], "Unknown"),
# #     #         "total_amount": float(row["TOTAL_AMOUNT"] or 0),
# #     #         "purch_state": PURCH_STATUS_MAP.get(row["PURCHSTATUS"])
# #     #     })

# #     # return result 

# #     for row in data:
# #         document_state = row.get("DOCUMENTSTATE")
# #         purch_status = row.get("PURCHSTATUS")

# #         # Rule: if document not confirmed → always Open
# #         if document_state != 40:
# #             final_status = "Open"
# #         else:
# #             # Only when document is confirmed (40)
# #             if purch_status in (0, 1):
# #                 final_status = "Confirmed"
# #             elif purch_status == 2:
# #                 final_status = "Received"
# #             elif purch_status == 3:
# #                 final_status = "Invoiced"
# #             elif purch_status == 4:
# #                 final_status = "cancelled"
# #             else:
# #                 final_status = "Unknown"

# #         result.append({
# #             "po_id": row["PURCHID"],
# #             "rfq_id": row["RFQID"],
# #             "created_date": format_utc_iso(row["CREATEDDATETIME"]),
# #             "total_amount": float(row["TOTAL_AMOUNT"] or 0),
# #             "purch_state": final_status
# #         })

# #     return result 
        