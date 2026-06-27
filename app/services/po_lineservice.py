from app.utils.date_utils import (
    format_utc_iso
)

from app.db.base import (
    get_connection
)
from app.core.config import settings
SCHEMA = settings.DB_SCHEMA

# ============================================================
# PURCHASE STATUS MAP
# ============================================================
PURCH_STATUS_MAP = {

    0: "Confirmed",

    1: "Confirmed",

    2: "Received",

    3: "Invoiced",

    4: "Cancelled"
}


# ============================================================
# FETCH DATA
# ============================================================
def fetch_po_details(
    purch_id: str,
    vendor_account: str
):

    query = f"""
        SELECT

            P.PURCHID,

            P.CREATEDDATETIME
                AS ISSUEDATE,

            P.PURCHSTATUS
                AS HEADERSTATUS,

            P.DOCUMENTSTATE,

            P.ORDERACCOUNT,

            (
                SELECT TOP 1
                    R.RFQID

                FROM {SCHEMA}.D365_PURCHRFQLINE R
                WITH (NOLOCK)

                WHERE R.PURCHID = P.PURCHID

            ) AS RFQID,

            (
                SELECT TOP 1
                    J.PURCHORDERDATE

                FROM {SCHEMA}.D365_VENDPURCHORDERJOUR J
                WITH (NOLOCK)

                WHERE J.PURCHID = P.PURCHID

                ORDER BY
                    J.PURCHORDERDATE DESC

            ) AS CONFIRMEDDATE,

            L.LINENUMBER,

            L.DELIVERYDATE
                AS LINEDELIVERYDATE,

            L.ITEMID
                AS ITEM,

            L.NAME
                AS DESCRIPTION,

            PC.NAME
                AS PROCUREMENTCATEGORY,

            L.QTYORDERED
                AS QTY,

            L.PURCHUNIT
                AS UOM,

            L.PURCHPRICE
                AS UNITPRICE,

            L.LINEAMOUNT
                AS NETAMOUNT,

            L.CURRENCYCODE

        FROM {SCHEMA}.D365_PURCHTABLE P
        WITH (NOLOCK)

        LEFT JOIN {SCHEMA}.D365_PURCHLINE L
        WITH (NOLOCK)
            ON L.PURCHID = P.PURCHID
            AND L.ISDELETED = 0

        LEFT JOIN {SCHEMA}.D365_ECORESCATEGORY PC
        WITH (NOLOCK)
            ON PC.RECID = L.PROCUREMENTCATEGORY

        WHERE P.PURCHID = ?
          AND P.ORDERACCOUNT = ?
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            query,
            purch_id,
            vendor_account
        )

        columns = [
            col[0]
            for col in cursor.description
        ]

        rows = cursor.fetchall()

        return [
            dict(zip(columns, row))
            for row in rows
        ]


# ============================================================
# MAIN SERVICE
# ============================================================
def get_po_details(
    purch_id: str,
    vendor_account: str
):

    data = fetch_po_details(
        purch_id,
        vendor_account
    )

    if not data:
        return None

    first_row = data[0]

    # ========================================================
    # TOTAL VALUE
    # ========================================================
    # total_value = sum(

    #     float(
    #         row["NETAMOUNT"] or 0
    #     )

    #     for row in data
    # )
    total_value = round(sum(
        float(row["NETAMOUNT"] or 0)
        for row in data
    ), 2)

    # ========================================================
    # HEADER STATUS
    # ========================================================
    document_state = int(
        first_row.get(
            "DOCUMENTSTATE"
        ) or 0
    )

    purch_status = int(
        first_row.get(
            "HEADERSTATUS"
        ) or 0
    )

    if document_state != 40:

        header_status = "Open"

    else:

        header_status = PURCH_STATUS_MAP.get(
            purch_status,
            "Unknown"
        )

    # ========================================================
    # HEADER
    # ========================================================
    header = {

        "po_number":
            first_row["PURCHID"],

        "rfq_number":
            first_row["RFQID"],

        "header_status":
            header_status,

        "issue_date":
            format_utc_iso(
                first_row["ISSUEDATE"]
            ),

        "confirmed_date":
            format_utc_iso(
                first_row["CONFIRMEDDATE"]
            ),

        "total_value":
            total_value
    }

    # ========================================================
    # LINE ITEMS
    # ========================================================
    lines = []

    for row in data:

        lines.append({

            "line_number":
                row["LINENUMBER"],

            "item":
                row["ITEM"],

            "description":
                row["DESCRIPTION"],

            "procurement_category":
                row[
                    "PROCUREMENTCATEGORY"
                ],

            "quantity":
                float(
                    row["QTY"] or 0
                ),

            "uom":
                row["UOM"],

            "unit_price":
                float(
                    row["UNITPRICE"] or 0
                ),

            "net_amount":
                float(
                    row["NETAMOUNT"] or 0
                ),

            "expected_delivery_date":

                format_utc_iso(
                    row[
                        "LINEDELIVERYDATE"
                    ]
                )

                if row[
                    "LINEDELIVERYDATE"
                ]

                else None,

            "currency":
                row["CURRENCYCODE"]
        })

    return {

        "header":
            header,

        "lines":
            lines
    }

# from app.utils.date_utils import format_utc_iso,format_date
# from app.db.base import get_connection,get_connection


# # ---------------------------------------------------------
# # PurchStatus Enum Mapping
# # ---------------------------------------------------------
# PURCH_STATUS_MAP = {
#     0: "Confirmed",
#     1: "Confirmed",
#     2: "Received",
#     3: "Invoiced",
#     4: "Cancelled"
# }


# # ---------------------------------------------------------
# # Fetch Data From Database
# # ---------------------------------------------------------
# def fetch_po_details(purch_id: str, vendor_account: str):

#     query = """
#     SELECT
#         P.PURCHID,
#         P.CREATEDDATETIME AS ISSUEDATE,
#         P.PURCHSTATUS AS HEADERSTATUS,
#         P.DOCUMENTSTATE,   -- ✅ REQUIRED
#         P.ORDERACCOUNT,

#         (
#             SELECT TOP 1 R.RFQID
#             FROM PURCHRFQLINE R
#             WHERE R.PURCHID = P.PURCHID
#         ) AS RFQID,

#         (
#             SELECT TOP 1 J.PURCHORDERDATE
#             FROM VENDPURCHORDERJOUR J
#             WHERE J.PURCHID = P.PURCHID
#             ORDER BY J.PURCHORDERDATE DESC
#         ) AS CONFIRMEDDATE,

#         L.LINENUMBER,
#         L.DELIVERYDATE AS LINEDELIVERYDATE,
#         L.ITEMID AS ITEM,
#         PC.NAME AS PROCUREMENTCATEGORY,
#         L.NAME AS DESCRIPTION,
#         L.QTYORDERED AS QTY,
#         L.PURCHUNIT AS UOM,
#         L.PURCHPRICE AS UNITPRICE,
#         L.LINEAMOUNT AS NETAMOUNT,
#         L.CURRENCYCODE 

#     FROM PURCHTABLE P WITH (NOLOCK)

#     LEFT JOIN PURCHLINE L WITH (NOLOCK)
#         ON L.PURCHID = P.PURCHID
#         AND L.ISDELETED = 0 
#     LEFT JOIN EcoResCategory PC WITH (NOLOCK)
#         ON PC.RECID = L.PROCUREMENTCATEGORY

#     LEFT JOIN ECORESPRODUCT EP WITH (NOLOCK)
#         ON EP.DISPLAYPRODUCTNUMBER = L.ITEMID

#     WHERE P.PURCHID = ?
#       AND P.ORDERACCOUNT = ?
#     """
#     with get_connection() as conn:
#     # with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute(query, purch_id, vendor_account)

#         columns = [col[0] for col in cursor.description]
#         rows = cursor.fetchall()

#         return [dict(zip(columns, row)) for row in rows]


# # ---------------------------------------------------------
# # Main Service Function
# # ---------------------------------------------------------
# def get_po_details(purch_id: str, vendor_account: str):

#     data = fetch_po_details(purch_id, vendor_account)

#     if not data:
#         return None

#     first_row = data[0]

#     # ---------------------------------------------------------
#     # TOTAL VALUE
#     # ---------------------------------------------------------
#     total_value = sum(float(row["NETAMOUNT"] or 0) for row in data)

#     # ---------------------------------------------------------
#     # 🔥 HEADER STATUS USING DOCUMENTSTATE
#     # ---------------------------------------------------------
#     document_state = int(first_row.get("DOCUMENTSTATE") or 0)
#     purch_status   = int(first_row.get("HEADERSTATUS") or 0)

#     if document_state != 40:
#         header_status = "Open"
#     else:
#         header_status = PURCH_STATUS_MAP.get(purch_status, "Unknown")

#     # ---------------------------------------------------------
#     # HEADER
#     # ---------------------------------------------------------
#     header = {
#         "po_number": first_row["PURCHID"],
#         "rfq_number": first_row["RFQID"],
#         "header_status": header_status,
#         "issue_date": format_utc_iso(first_row["ISSUEDATE"]),
#         "confirmed_date": format_utc_iso(first_row["CONFIRMEDDATE"]),
#         "total_value": total_value
#     }

#     # ---------------------------------------------------------
#     # LINES (NO STATUS LOGIC)
#     # ---------------------------------------------------------
#     lines = []

#     for row in data:
#         lines.append({
#             "line_number": row["LINENUMBER"],
#             "item": row["ITEM"],
#             "description": row["DESCRIPTION"],
#             "procrument_category":row["PROCUREMENTCATEGORY"],
#             "quantity": float(row["QTY"] or 0),
#             "uom": row["UOM"],
#             "unit_price": float(row["UNITPRICE"] or 0),
#             "net_amount": float(row["NETAMOUNT"] or 0),
#             "expected_delivery_date": format_utc_iso(row["LINEDELIVERYDATE"]) if row["LINEDELIVERYDATE"] else None,
#             "currency": first_row["CURRENCYCODE"]
#         })

#     return {
#         "header": header,
#         "lines": lines
#     }

# # from app.utils.date_utils import format_utc_iso
# # from app.db.base import get_connection
 
 
# # # ---------------------------------------------------------
# # # PurchStatus Enum Mapping (Header & Line Both Use Same)
# # # ---------------------------------------------------------
# # PURCH_STATUS_MAP = {
# #     0: "Confirmed",
# #     1: "Confirmed",
# #     2: "Received",
# #     3: "Invoiced",
# #     4: "cancelled"
# # }
 
# # # ---------------------------------------------------------
# # # Fetch Data From Database
# # # ---------------------------------------------------------
# # def fetch_po_details(purch_id: str, vendor_account: str):
 
# #     query = """
# #     SELECT
# #     P.PURCHID,
# #     P.CREATEDDATETIME AS ISSUEDATE,
# #     P.PURCHSTATUS AS HEADERSTATUS,
# #     P.ORDERACCOUNT,
# #     P.DOCUMENTSTATE,  
 
# #     -- Get RFQID safely
# #     (
# #         SELECT TOP 1 R.RFQID
# #         FROM PURCHRFQLINE R
# #         WHERE R.PURCHID = P.PURCHID
# #     ) AS RFQID,
 
# #     -- Get latest confirmed date safely
# #     (
# #         SELECT TOP 1 J.PURCHORDERDATE
# #         FROM VENDPURCHORDERJOUR J
# #         WHERE J.PURCHID = P.PURCHID
# #         ORDER BY J.PURCHORDERDATE DESC
# #     ) AS CONFIRMEDDATE,
 
# #     L.LINENUMBER,
# #     L.DELIVERYDATE AS LINEDELIVERYDATE,
# #     L.ITEMID AS ITEM,
# #     EP.SEARCHNAME AS DESCRIPTION,
# #     L.QTYORDERED AS QTY,
# #     L.PURCHUNIT AS UOM,
# #     L.PURCHPRICE AS UNITPRICE,
# #     L.LINEAMOUNT AS NETAMOUNT,
# #     L.PURCHSTATUS AS LINESTATUS,
# #     L.CURRENCYCODE 
 
# # FROM PURCHTABLE P WITH (NOLOCK)
 
# # LEFT JOIN PURCHLINE L WITH (NOLOCK)
# #     ON L.PURCHID = P.PURCHID
# #     AND L.ISDELETED = 0 
 
# # LEFT JOIN ECORESPRODUCT EP WITH (NOLOCK)
# #     ON EP.DISPLAYPRODUCTNUMBER = L.ITEMID
 
# # WHERE P.PURCHID = ?
# #   AND P.ORDERACCOUNT = ?
# # """
# #     with get_connection() as conn:
# #         cursor = conn.cursor()
# #         cursor.execute(query, purch_id, vendor_account)
 
# #         columns = [col[0] for col in cursor.description]
# #         rows = cursor.fetchall()
 
# #         return [dict(zip(columns, row)) for row in rows]
 
 
# # # ---------------------------------------------------------
# # # Main Service Function
# # # ---------------------------------------------------------
# # def get_po_details(purch_id: str, vendor_account: str):
 
# #     data = fetch_po_details(purch_id, vendor_account)
 
# #     if not data:
# #         return None
 
# #     first_row = data[0]
 
# #     # ---------------------------------------------------------
# #     # Calculate Total From Line Amounts
# #     # ---------------------------------------------------------
# #     total_value = sum(float(row["NETAMOUNT"] or 0) for row in data)
 
# #     # ---------------------------------------------------------
# #     # Header Section
# #     # ---------------------------------------------------------
# #     header = {
# #         "po_number": first_row["PURCHID"],
# #         "rfq_number": first_row["RFQID"],
# #         "header_status": PURCH_STATUS_MAP.get(
# #             first_row["HEADERSTATUS"], "Unknown"
# #         ),
# #         "issue_date": format_utc_iso(first_row["ISSUEDATE"]),
# #         "confirmed_date": format_utc_iso(first_row["CONFIRMEDDATE"]),
# #         "total_value": total_value
       
# #     }
 
# #     # ---------------------------------------------------------
# #     # Line Section (Delivery Date From Line Only)
# #     # ---------------------------------------------------------
# #     lines = []
 
# #     for row in data:
# #         lines.append({
# #             "line_number": row["LINENUMBER"],
# #             "item": row["ITEM"],
# #             "description": row["DESCRIPTION"],
# #             "quantity": float(row["QTY"] or 0),
# #             "uom": row["UOM"],
# #             "unit_price": float(row["UNITPRICE"] or 0),
# #             "net_amount": float(row["NETAMOUNT"] or 0),
# #             "expected_delivery_date": format_utc_iso(
# #                 row["LINEDELIVERYDATE"]
# #             ) if row["LINEDELIVERYDATE"] else None,
# #              "Currency":first_row["CURRENCYCODE"]
# #             # "line_status": PURCH_STATUS_MAP.get(
# #             #     row["LINESTATUS"], "Unknown"
# #             # )
# #         })
 
# #     return {
# #         "header": header,
# #         "lines": lines
# #     }
 
