import json

from app.db.base import get_connection
from app.utils.date_utils import format_utc_iso
from app.utils.remainingdate import calculate_days_left
from app.core.config import settings


SCHEMA = settings.DB_SCHEMA
RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"


# ============================================================
# FETCH RFQ DETAIL
# ============================================================
def fetch_rfq_detail(
    rfq_id: str,
    vendor_account: str
):

    # ========================================================
    # HEADER QUERY
    # ========================================================
    header_query = f"""
        SELECT
            C.RFQCASEID,
            T.RFQID,
            C.NAME AS DOCUMENT_TITLE,
            C.EXPIRYDATETIME AS CLOSING_DATE,
            C.CREATEDDATETIME AS ISSUE_DATE,
            C.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,
            PT.DESCRIPTION AS PAYMENT_TERM,
            PM.NAME AS METHOD_OF_PAYMENT,
            DM.TXT AS MODE_OF_DELIVERY,
            DT.TXT AS DELIVERY_TERM,
            T.HIQ_TERMSANDCONDITIONS

        FROM {SCHEMA}.D365_PURCHRFQCASETABLE C WITH (NOLOCK)

        INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T WITH (NOLOCK)
            ON T.RFQCASEID = C.RFQCASEID
            AND T.VENDACCOUNT = ?

        LEFT JOIN {SCHEMA}.D365_PAYMTERM PT WITH (NOLOCK)
            ON C.PAYMENT = PT.PAYMTERMID

        LEFT JOIN {SCHEMA}.D365_PAYMMODETABLE PM WITH (NOLOCK)
            ON C.PAYMMODE = PM.PAYMMODE

        LEFT JOIN {SCHEMA}.D365_DLVMODE DM WITH (NOLOCK)
            ON C.DLVMODE = DM.CODE

        LEFT JOIN {SCHEMA}.D365_DLVTERM DT WITH (NOLOCK)
            ON C.DLVTERM = DT.CODE

        WHERE T.RFQID = ?
    """

    # ========================================================
    # LINE QUERY
    # ========================================================
    lines_query = f"""
        SELECT
            RL.LINENUM,
            RL.ITEMID AS MATERIAL_CODE,
            IT.NAME AS MATERIAL_DESCRIPTION,
            RL.QTYORDERED AS QUANTITY,
            RL.PURCHUNIT AS UOM,
            RL.HIQ_TARGETPRICE AS TARGETPRICE,
            RL.HIQ_COMMENTS AS COMMENTS,
            RL.CURRENCYCODE,
            RL.DELIVERYDATE AS LINE_DELIVERY_DATE

        FROM {SCHEMA}.D365_PURCHRFQLINE RL WITH (NOLOCK)

        LEFT JOIN {SCHEMA}.D365_INVENTTABLE IT WITH (NOLOCK)
            ON IT.ITEMID = RL.ITEMID

        INNER JOIN {SCHEMA}.D365_PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
            ON AVL.ITEMID = RL.ITEMID
            AND AVL.PDSAPPROVEDVENDOR = ?
            AND AVL.VALIDFROM <= GETUTCDATE()
            AND AVL.VALIDTO >= GETUTCDATE()

        WHERE RL.RFQID = ?

        ORDER BY RL.LINENUM
    """

    # ========================================================
    # DRAFT QUERY
    # ========================================================
    draft_query = f"""
        SELECT TOP 1
            PAYLOADJSON,
            SUBMISSIONSTATUS

        FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)

        WHERE RFQID = ?
          AND VENDORACCOUNT = ?
          AND SUBMISSIONSTATUS IN (0, 1)

        ORDER BY ID DESC
    """

    # ========================================================
    # EXECUTE QUERIES
    # ========================================================
    with get_connection() as conn:

        cursor = conn.cursor()

        # HEADER
        cursor.execute(header_query, (vendor_account, rfq_id))
        row = cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "RFQ not found"
            }

        cols = [c[0] for c in cursor.description]
        header = dict(zip(cols, row))

        # LINES
        cursor.execute(lines_query, (vendor_account, rfq_id))
        line_rows = cursor.fetchall()

        line_cols = [c[0] for c in cursor.description]
        lines = [dict(zip(line_cols, r)) for r in line_rows]

        # DRAFT
        cursor.execute(draft_query, (rfq_id, vendor_account))
        draft_row = cursor.fetchone()

    # ========================================================
    # PARSE DRAFT
    # ========================================================
    saved_price_map = {}
    saved_header = {}
    draft_submissionstatus = None

    if draft_row and draft_row[0]:

        draft_submissionstatus = draft_row[1]

        try:
            payload = json.loads(draft_row[0])

            saved_header = {
                "modeOfDelivery": payload.get("modeOfDelivery", ""),
                "DeliveryTerms": payload.get("DeliveryTerms", ""),
                "methodOfPayment": payload.get("methodOfPayment", ""),
                "termsOfPayment": payload.get("termsOfPayment", ""),
                "replyDeliveryDate": payload.get("replyDeliveryDate", ""),
                "replyDeliveryTerms": payload.get("replyDeliveryTerms", ""),
                "replyModeOfDelivery": payload.get("replyModeOfDelivery", ""),
                "vendorComments": payload.get("vendorComments", ""),
            }

            for item in payload.get("Item", []):

                line_number = item.get("lineNumber")

                if line_number is not None:

                    saved_price_map[int(line_number)] = {
                        "unit_price": item.get("unitPrice", 0),
                        "vendor_comments": item.get(
                            "vendorComments",
                            ""
                        ),
                        "lineStatus": item.get("lineStatus"),
                        "vendor_delivery_date": item.get(
                            "deliveryDate"
                        )
                    }

        except Exception as e:
            print("Draft parse error:", e)

    # ========================================================
    # BUILD ITEMS
    # ========================================================
    items = []

    for item in lines:

        line_number = int(item["LINENUM"])

        saved = saved_price_map.get(
            line_number,
            {}
        )

        unit_price = saved.get(
            "unit_price",
            0
        )

        # LINE STATUS
        if "lineStatus" in saved:
            line_status = saved.get("lineStatus")
        else:
            line_status = unit_price > 0

        # VENDOR DELIVERY DATE
        formatted_vendor_date = None

        try:
            vendor_date = saved.get(
                "vendor_delivery_date"
            )

            if vendor_date:
                formatted_vendor_date = format_utc_iso(
                    vendor_date
                )

        except Exception:
            formatted_vendor_date = None

        items.append({

            "sl_no":
                line_number,

            "material_description":
                item["MATERIAL_DESCRIPTION"],

            "material_code":
                item["MATERIAL_CODE"],

            "quantity":
                item["QUANTITY"],

            "uom":
                item["UOM"],

            "target_price":
                round(
                    float(
                        item["TARGETPRICE"] or 0
                    ),
                    2
                ),

            "comments":
                item["COMMENTS"],

            "unit_price":
                unit_price,

            "remarks":
                saved.get(
                    "vendor_comments",
                    ""
                ),

            "lineStatus":
                line_status,

            "currency":
                item.get(
                    "CURRENCYCODE"
                ),

            "rfq_delivery_date":
                format_utc_iso(
                    item.get(
                        "LINE_DELIVERY_DATE"
                    )
                ),

            "vendor_delivery_date":
                formatted_vendor_date
        })

    # ========================================================
    # HEADER DELIVERY DATE
    # ========================================================
    formatted_reply_delivery_date = None

    try:
        reply_date = saved_header.get(
            "replyDeliveryDate"
        )

        if reply_date:
            formatted_reply_delivery_date = (
                format_utc_iso(reply_date)
            )

    except Exception:
        formatted_reply_delivery_date = None

    # ========================================================
    # FINAL RESPONSE
    # ========================================================
    return {

        "success": True,

        "has_draft":
            bool(saved_price_map)
            and draft_submissionstatus == 0,

        "data": {

            "rfq_case_id":
                header["RFQCASEID"],

            "rfq_id":
                header["RFQID"],

            "document_title":
                header["DOCUMENT_TITLE"],

            "issue_date":
                format_utc_iso(
                    header["ISSUE_DATE"]
                ),

            "closing_date":
                format_utc_iso(
                    header["CLOSING_DATE"]
                ),

            "time_remaining":
                calculate_days_left(
                    header["CLOSING_DATE"]
                ),

            "expected_delivery_date":
                format_utc_iso(
                    header["EXPECTED_DELIVERY_DATE"]
                ),

            "payment_term":
                header["PAYMENT_TERM"] or "-",

            "method_of_payment":
                header["METHOD_OF_PAYMENT"] or "-",

            "delivery_term":
                header["DELIVERY_TERM"] or "-",

            "mode_of_delivery":
                header["MODE_OF_DELIVERY"] or "-",

            "termsandconditions":
                header["HIQ_TERMSANDCONDITIONS"],

            # SAVED HEADER VALUES
            "saved_mode_of_delivery":
                saved_header.get(
                    "modeOfDelivery",
                    ""
                ),

            "saved_delivery_terms":
                saved_header.get(
                    "DeliveryTerms",
                    ""
                ),

            "saved_method_of_payment":
                saved_header.get(
                    "methodOfPayment",
                    ""
                ),

            "saved_terms_of_payment":
                saved_header.get(
                    "termsOfPayment",
                    ""
                ),

            "saved_reply_delivery_date":
                formatted_reply_delivery_date,

            "saved_reply_delivery_terms":
                saved_header.get(
                    "replyDeliveryTerms",
                    ""
                ),

            "saved_reply_mode_of_delivery":
                saved_header.get(
                    "replyModeOfDelivery",
                    ""
                ),

            "saved_vendor_comments":
                saved_header.get(
                    "vendorComments",
                    ""
                ),

            "items":
                items
        }
    }

# import json
# from datetime import datetime

# from app.db.base import get_connection
# from app.utils.date_utils import format_utc_iso
# from app.utils.remainingdate import calculate_days_left
# from app.core.config import settings


# SCHEMA = settings.DB_SCHEMA

# RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"


# # ============================================================
# # FETCH RFQ DETAIL
# # ============================================================
# def fetch_rfq_detail(
#     rfq_id: str,
#     vendor_account: str
# ):

#     # ========================================================
#     # HEADER QUERY
#     # ========================================================
#     header_query = f"""
#         SELECT
#             C.RFQCASEID,
#             T.RFQID,
#             C.NAME                  AS DOCUMENT_TITLE,
#             C.EXPIRYDATETIME        AS CLOSING_DATE,
#             C.CREATEDDATETIME       AS ISSUE_DATE,
#             C.DELIVERYDATE          AS EXPECTED_DELIVERY_DATE,
#             PT.DESCRIPTION          AS PAYMENT_TERM,
#             PM.NAME                 AS METHOD_OF_PAYMENT,
#             DM.TXT                  AS MODE_OF_DELIVERY,
#             DT.TXT                  AS DELIVERY_TERM,
#             T.HIQ_TERMSANDCONDITIONS

#         FROM {SCHEMA}.D365_PURCHRFQCASETABLE C WITH (NOLOCK)

#         INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T WITH (NOLOCK)
#             ON T.RFQCASEID  = C.RFQCASEID
#            AND T.VENDACCOUNT = ?

#         LEFT JOIN {SCHEMA}.D365_PAYMTERM PT WITH (NOLOCK)
#             ON C.PAYMENT = PT.PAYMTERMID

#         LEFT JOIN {SCHEMA}.D365_PAYMMODETABLE PM WITH (NOLOCK)
#             ON C.PAYMMODE = PM.PAYMMODE

#         LEFT JOIN {SCHEMA}.D365_DLVMODE DM WITH (NOLOCK)
#             ON C.DLVMODE = DM.CODE

#         LEFT JOIN {SCHEMA}.D365_DLVTERM DT WITH (NOLOCK)
#             ON C.DLVTERM = DT.CODE

#         WHERE T.RFQID = ?
#     """

#     # ========================================================
#     # LINE QUERY
#     # ========================================================
#     lines_query = f"""
#         SELECT
#             RL.LINENUM,
#             RL.ITEMID               AS MATERIAL_CODE,
#             IT.NAME                 AS MATERIAL_DESCRIPTION,
#             RL.QTYORDERED           AS QUANTITY,
#             RL.PURCHUNIT            AS UOM,
#             RL.HIQ_TARGETPRICE      AS TARGETPRICE,
#             RL.HIQ_COMMENTS         AS COMMENTS,
#             RL.CURRENCYCODE,
#             RL.DELIVERYDATE         AS LINE_DELIVERY_DATE

#         FROM {SCHEMA}.D365_PURCHRFQLINE RL WITH (NOLOCK)

#         LEFT JOIN {SCHEMA}.D365_INVENTTABLE IT WITH (NOLOCK)
#             ON IT.ITEMID = RL.ITEMID

#         INNER JOIN {SCHEMA}.D365_PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#             ON  AVL.ITEMID           = RL.ITEMID
#             AND AVL.PDSAPPROVEDVENDOR = ?
#             AND AVL.VALIDFROM        <= GETUTCDATE()
#             AND AVL.VALIDTO          >= GETUTCDATE()

#         WHERE RL.RFQID = ?

#         ORDER BY RL.LINENUM
#     """

#     # ========================================================
#     # DRAFT QUERY — fetch draft (0) OR confirmed (1)
#     # ========================================================
#     draft_query = f"""
#         SELECT TOP 1
#             PAYLOADJSON,
#             SUBMISSIONSTATUS

#         FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)

#         WHERE RFQID          = ?
#           AND VENDORACCOUNT  = ?
#           AND SUBMISSIONSTATUS IN (0, 1)

#         ORDER BY ID DESC
#     """

#     # ========================================================
#     # EXECUTE ALL QUERIES
#     # ========================================================
#     with get_connection() as conn:

#         cursor = conn.cursor()

#         # ── HEADER ──────────────────────────────────────────
#         cursor.execute(header_query, (vendor_account, rfq_id))

#         row = cursor.fetchone()

#         if not row:
#             return {
#                 "success": False,
#                 "message": "RFQ not found"
#             }

#         cols   = [c[0] for c in cursor.description]
#         header = dict(zip(cols, row))

#         # ── LINES ───────────────────────────────────────────
#         cursor.execute(lines_query, (vendor_account, rfq_id))

#         line_rows = cursor.fetchall()
#         line_cols = [c[0] for c in cursor.description]
#         lines     = [dict(zip(line_cols, r)) for r in line_rows]

#         # ── DRAFT ───────────────────────────────────────────
#         cursor.execute(draft_query, (rfq_id, vendor_account))

#         draft_row = cursor.fetchone()

#     # ========================================================
#     # PARSE SAVED DRAFT / CONFIRMED PAYLOAD
#     # ========================================================
#     saved_price_map      = {}
#     saved_header         = {}
#     draft_submissionstatus = None

#     if draft_row and draft_row[0]:

#         draft_submissionstatus = draft_row[1]

#         try:
#             payload = json.loads(draft_row[0])

#             # ── HEADER VALUES ────────────────────────────────
#             saved_header = {
#                 "modeOfDelivery":       payload.get("modeOfDelivery",       ""),
#                 "DeliveryTerms":        payload.get("DeliveryTerms",         ""),
#                 "methodOfPayment":      payload.get("methodOfPayment",       ""),
#                 "termsOfPayment":       payload.get("termsOfPayment",        ""),
#                 "replyDeliveryDate":    payload.get("replyDeliveryDate",     ""),
#                 "replyDeliveryTerms":   payload.get("replyDeliveryTerms",    ""),
#                 "replyModeOfDelivery":  payload.get("replyModeOfDelivery",   ""),
#                 "vendorComments":       payload.get("vendorComments",        ""),
#             }

#             # ── LINE VALUES ──────────────────────────────────
#             for item in payload.get("Item", []):

#                 line_number = item.get("lineNumber")

#                 if line_number is not None:

#                     saved_price_map[int(line_number)] = {
#                         "unit_price":          item.get("unitPrice",       0),
#                         "vendor_comments":     item.get("vendorComments",  ""),
#                         "lineStatus":          item.get("lineStatus"),
#                         "vendor_delivery_date": item.get("deliveryDate")   # ← "28/05/2026"
#                     }

#         except Exception as e:
#             print("Draft parse error:", e)

#     # ========================================================
#     # BUILD ITEMS
#     # ========================================================
#         items = []

#         for item in lines:

#             line_number = int(item["LINENUM"])

#             saved = saved_price_map.get(
#                 line_number,
#                 {}
#             )

#             unit_price = saved.get(
#                 "unit_price",
#                 0
#             )

#             # ── LINE STATUS ──────────────────────────────────────
#             if "lineStatus" in saved:

#                 line_status = saved.get(
#                     "lineStatus"
#                 )

#             else:

#                 line_status = unit_price > 0

#             # ====================================================
#             # LINE DELIVERY DATE
#             # take ONLY line payload deliveryDate
#             # ====================================================
#             formatted_vendor_date = format_utc_iso(
#                 saved.get(
#                     "vendor_delivery_date"
#                 )
#             )

#             items.append({

#                 "sl_no":
#                     line_number,

#                 "material_description":
#                     item["MATERIAL_DESCRIPTION"],

#                 "material_code":
#                     item["MATERIAL_CODE"],

#                 "quantity":
#                     item["QUANTITY"],

#                 "uom":
#                     item["UOM"],

#                 "target_price":
#                     round(
#                         float(
#                             item["TARGETPRICE"] or 0
#                         ),
#                         2
#                     ),

#                 "comments":
#                     item["COMMENTS"],

#                 "unit_price":
#                     unit_price,

#                 "remarks":
#                     saved.get(
#                         "vendor_comments",
#                         ""
#                     ),

#                 "lineStatus":
#                     line_status,

#                 "currency":
#                     item.get(
#                         "CURRENCYCODE"
#                     ),

#                 "rfq_delivery_date":
#                     format_utc_iso(
#                         item.get(
#                             "LINE_DELIVERY_DATE"
#                         )
#                     ),

#                 # line-level payload date
#                 "vendor_delivery_date":
#                     formatted_vendor_date
#             })


#         # ========================================================
#         # HEADER DELIVERY DATE
#         # take ONLY payload.replyDeliveryDate
#         # ========================================================
#         formatted_reply_delivery_date = format_utc_iso(
#             saved_header.get(
#                 "replyDeliveryDate"
#             )
#         )


#         # ========================================================
#         # FINAL RESPONSE
#         # ========================================================
#         return {

#             "success": True,

#             "has_draft":
#                 bool(saved_price_map)
#                 and draft_submissionstatus == 0,

#             "data": {

#                 "rfq_case_id":
#                     header["RFQCASEID"],

#                 "rfq_id":
#                     header["RFQID"],

#                 "document_title":
#                     header["DOCUMENT_TITLE"],

#                 "issue_date":
#                     format_utc_iso(
#                         header["ISSUE_DATE"]
#                     ),

#                 "closing_date":
#                     format_utc_iso(
#                         header["CLOSING_DATE"]
#                     ),

#                 "time_remaining":
#                     calculate_days_left(
#                         header["CLOSING_DATE"]
#                     ),

#                 "expected_delivery_date":
#                     format_utc_iso(
#                         header[
#                             "EXPECTED_DELIVERY_DATE"
#                         ]
#                     ),

#                 "payment_term":
#                     header["PAYMENT_TERM"] or "-",

#                 "method_of_payment":
#                     header[
#                         "METHOD_OF_PAYMENT"
#                     ] or "-",

#                 "delivery_term":
#                     header[
#                         "DELIVERY_TERM"
#                     ] or "-",

#                 "mode_of_delivery":
#                     header[
#                         "MODE_OF_DELIVERY"
#                     ] or "-",

#                 "termsandconditions":
#                     header[
#                         "HIQ_TERMSANDCONDITIONS"
#                     ],

#                 # ====================================================
#                 # HEADER VALUES
#                 # ====================================================
#                 "saved_mode_of_delivery":
#                     saved_header.get(
#                         "modeOfDelivery",
#                         ""
#                     ),

#                 "saved_delivery_terms":
#                     saved_header.get(
#                         "DeliveryTerms",
#                         ""
#                     ),

#                 "saved_method_of_payment":
#                     saved_header.get(
#                         "methodOfPayment",
#                         ""
#                     ),

#                 "saved_terms_of_payment":
#                     saved_header.get(
#                         "termsOfPayment",
#                         ""
#                     ),

#                 # header payload date
#                 "saved_reply_delivery_date":
#                     formatted_reply_delivery_date,

#                 "saved_reply_delivery_terms":
#                     saved_header.get(
#                         "replyDeliveryTerms",
#                         ""
#                     ),

#                 "saved_reply_mode_of_delivery":
#                     saved_header.get(
#                         "replyModeOfDelivery",
#                         ""
#                     ),

#                 "saved_vendor_comments":
#                     saved_header.get(
#                         "vendorComments",
#                         ""
#                     ),

#                 "items":
#                     items
#             }
#         }
# #     items = []

# #     for item in lines:

# #         line_number = int(item["LINENUM"])
# #         saved       = saved_price_map.get(line_number, {})
# #         unit_price  = saved.get("unit_price", 0)

# #         # ── LINE STATUS ──────────────────────────────────────
# #         if "lineStatus" in saved:
# #             line_status = saved.get("lineStatus")
# #         else:
# #             line_status = unit_price > 0

# #         # ── VENDOR DELIVERY DATE ─────────────────────────────
# #         vendor_date           = saved.get("vendor_delivery_date")
# #         formatted_vendor_date = None

# #         if vendor_date:
# #             try:
# #                 formatted_vendor_date = format_utc_iso(
# #     saved.get(
# #         "vendor_delivery_date"
# #     )
# # )
# #             except Exception:
# #                 formatted_vendor_date = None

# #         items.append({
# #             "sl_no":                line_number,
# #             "material_description": item["MATERIAL_DESCRIPTION"],
# #             "material_code":        item["MATERIAL_CODE"],
# #             "quantity":             item["QUANTITY"],
# #             "uom":                  item["UOM"],
# #             "target_price":         round(float(item["TARGETPRICE"] or 0), 2),
# #             "comments":             item["COMMENTS"],
# #             "unit_price":           unit_price,
# #             "remarks":              saved.get("vendor_comments", ""),
# #             "lineStatus":           line_status,
# #             "currency":             item.get("CURRENCYCODE"),
# #             "rfq_delivery_date":    format_utc_iso(item.get("LINE_DELIVERY_DATE")),
# #             "vendor_delivery_date": formatted_vendor_date,   # ← now populated correctly
# #         })

# #     # ========================================================
# #     # FINAL RESPONSE
# #     # ========================================================
# #     return {

# #         "success": True,

# #         # has_draft = True only when actual unsaved draft (status=0)
# #         "has_draft": bool(saved_price_map) and draft_submissionstatus == 0,

# #         "data": {
# #             "rfq_case_id":              header["RFQCASEID"],
# #             "rfq_id":                   header["RFQID"],
# #             "document_title":           header["DOCUMENT_TITLE"],
# #             "issue_date":               format_utc_iso(header["ISSUE_DATE"]),
# #             "closing_date":             format_utc_iso(header["CLOSING_DATE"]),
# #             "time_remaining":           calculate_days_left(header["CLOSING_DATE"]),
# #             "expected_delivery_date":   format_utc_iso(header["EXPECTED_DELIVERY_DATE"]),
# #             "payment_term":             header["PAYMENT_TERM"]       or "-",
# #             "method_of_payment":        header["METHOD_OF_PAYMENT"]  or "-",
# #             "delivery_term":            header["DELIVERY_TERM"]      or "-",
# #             "mode_of_delivery":         header["MODE_OF_DELIVERY"]   or "-",
# #             "termsandconditions":       header["HIQ_TERMSANDCONDITIONS"],

# #             # ── SAVED VALUES FROM DRAFT/CONFIRMED ────────────
# #             "saved_mode_of_delivery":       saved_header.get("modeOfDelivery",      ""),
# #             "saved_delivery_terms":         saved_header.get("DeliveryTerms",        ""),
# #             "saved_method_of_payment":      saved_header.get("methodOfPayment",      ""),
# #             "saved_terms_of_payment":       saved_header.get("termsOfPayment",       ""),
# #             "saved_reply_delivery_date":   formatted_vendor_date,
# #             "saved_reply_delivery_terms":   saved_header.get("replyDeliveryTerms",   ""),
# #             "saved_reply_mode_of_delivery": saved_header.get("replyModeOfDelivery",  ""),
# #             "saved_vendor_comments":        saved_header.get("vendorComments",       ""),

# #             "items": items,
# #         }
# #     }

