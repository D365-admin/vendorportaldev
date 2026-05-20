import json

from app.db.base import (
    get_connection,
    get_d365_connection
)

from app.utils.date_utils import (
    format_utc_iso
)

from app.utils.remainingdate import (
    calculate_days_left
)
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"

def fetch_rfq_detail(
    rfq_id: str,
    vendor_account: str
):

    # ============================================================
    # D365 HEADER QUERY
    # ============================================================
    header_query = """
        SELECT
            L.RFQCASEID,

            T.RFQID,

            T.VENDACCOUNT,

            L.NAME AS DOCUMENT_TITLE,

            L.EXPIRYDATETIME AS CLOSING_DATE,

            L.CREATEDDATETIME AS ISSUE_DATE,

            L.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,

            PT.DESCRIPTION AS PAYMENT_TERM,

            PM.NAME AS METHOD_OF_PAYMENT,

            DM.TXT AS MODE_OF_DELIVERY,

            DT.TXT AS DELIVERY_TERM,

            T.HIQ_TERMSANDCONDITIONS

        FROM PurchRFQCaseTable L WITH (NOLOCK)

        INNER JOIN PurchRFQTable T WITH (NOLOCK)
            ON T.RFQCASEID = L.RFQCASEID
            AND T.VENDACCOUNT = ?

        LEFT JOIN PAYMTERM PT WITH (NOLOCK)
            ON L.PAYMENT = PT.PAYMTERMID

        LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
            ON L.PAYMMODE = PM.PAYMMODE

        LEFT JOIN DLVMODE DM WITH (NOLOCK)
            ON L.DLVMODE = DM.CODE

        LEFT JOIN DLVTERM DT WITH (NOLOCK)
            ON L.DLVTERM = DT.CODE

        WHERE T.RFQID = ?
    """


    # ============================================================
    # D365 LINE QUERY
    # ============================================================
    lines_query = """
        SELECT
            RL.LINENUM,

            RL.ITEMID AS MATERIAL_CODE,

            IT.NAMEALIAS AS MATERIAL_DESCRIPTION,

            RL.QTYORDERED AS QUANTITY,

            RL.PURCHUNIT AS UOM,

            RL.HIQ_TARGETPRICE AS TARGETPRICE,

            RL.HIQ_COMMENTS AS COMMENTS,

            RL.CURRENCYCODE,

            RL.DELIVERYDATE AS LINE_DELIVERY_DATE,

            RPL.DELIVERYDATE AS VENDORREPLY_DELIVERY_DATE

        FROM PurchRFQLine RL WITH (NOLOCK)

        LEFT JOIN PURCHRFQREPLYLINE RPL WITH (NOLOCK)
            ON RPL.RFQLINERECID = RL.RECID
            AND RPL.DATAAREAID = 'hi-q'

        LEFT JOIN INVENTTABLE IT WITH (NOLOCK)
            ON IT.ITEMID = RL.ITEMID

        INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
            ON AVL.ITEMID = RL.ITEMID
            AND AVL.PDSAPPROVEDVENDOR = ?

        WHERE RL.RFQID = ?

        ORDER BY RL.LINENUM
    """


    # ============================================================
    # VENDOR DB DRAFT QUERY
    # ============================================================
    draft_query = f"""
        SELECT TOP 1
            PAYLOADJSON

        FROM {RFQ_REPLIES_TABLE}  WITH (NOLOCK)

        WHERE RFQID = ?
          AND VENDORACCOUNT = ?

        ORDER BY ID DESC
    """


    # ============================================================
    # STEP 1
    # FETCH HEADER + LINES FROM D365 DB
    # ============================================================
    with get_d365_connection() as conn:

        cursor = conn.cursor()


        # HEADER
        cursor.execute(
            header_query,
            (vendor_account, rfq_id)
        )

        row = cursor.fetchone()

        if not row:

            return {
                "success": False,
                "message": "RFQ not found"
            }

        cols = [c[0] for c in cursor.description]

        header = dict(zip(cols, row))


        # LINES
        cursor.execute(
            lines_query,
            (vendor_account, rfq_id)
        )

        line_rows = cursor.fetchall()

        line_cols = [
            c[0]
            for c in cursor.description
        ]

        lines = [
            dict(zip(line_cols, r))
            for r in line_rows
        ]


    # ============================================================
    # STEP 2
    # FETCH DRAFT FROM VENDOR DB
    # ============================================================
    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            draft_query,
            (rfq_id, vendor_account)
        )

        draft_row = cursor.fetchone()


    # ============================================================
    # PARSE SAVED DRAFT
    # ============================================================
    saved_price_map = {}

    saved_header = {}


    if draft_row and draft_row[0]:

        try:

            payload = json.loads(draft_row[0])

            saved_header = {

                "modeOfDelivery":
                    payload.get("modeOfDelivery", ""),

                "DeliveryTerms":
                    payload.get("DeliveryTerms", ""),

                "methodOfPayment":
                    payload.get("methodOfPayment", ""),

                "termsOfPayment":
                    payload.get("termsOfPayment", ""),

                "replyDeliveryDate":
                    payload.get("replyDeliveryDate", ""),

                "replyDeliveryTerms":
                    payload.get("replyDeliveryTerms", ""),

                "replyModeOfDelivery":
                    payload.get("replyModeOfDelivery", ""),

                "vendorComments":
                    payload.get("vendorComments", ""),
            }


            for item in payload.get("Item", []):

                item_number = item.get("itemNumber")

                line_number = item.get("lineNumber")


                if item_number and line_number:

                    key = (
                        int(line_number),
                        str(item_number).strip().upper()
                    )

                    val = item.get("unitPrice")

                    saved_price_map[key] = {

                        "unit_price":
                            float(val)
                            if val not in [None, ""]
                            else "",

                        "net_amount":
                            float(item.get("netAmount"))
                            if item.get("netAmount")
                            not in [None, ""]
                            else "",

                        "vendor_comments":
                            item.get("vendorComments", ""),

                        "line_status":
                            item.get("lineStatus", False),
                    }

        except Exception:
            pass


    # ============================================================
    # BUILD LINE ITEMS
    # ============================================================
    line_items = []


    for item in lines:

        material_code = (
            str(item["MATERIAL_CODE"])
            .strip()
            .upper()
        )

        key = (
            int(item["LINENUM"]),
            material_code
        )

        saved = saved_price_map.get(key, {})


        # ========================================================
        # SKIP CONFIRMED LINE
        # ========================================================
        if saved.get("line_status", False):
            continue


        line_items.append({

            "line_num":
                int(item["LINENUM"]),

            "item_name":
                item["MATERIAL_DESCRIPTION"],

            "item_id":
                material_code,

            "quantity":
                item["QUANTITY"],

            "uom":
                item["UOM"],

            "target_price":
                round(
                    float(item["TARGETPRICE"] or 0),
                    2
                ),

            "currency":
                item["CURRENCYCODE"],

            "comments":
                item["COMMENTS"],

            "unit_price":
                saved.get("unit_price", ""),

            "net_amount":
                saved.get("net_amount", ""),

            "vendor_comments":
                saved.get("vendor_comments", ""),

            "rfq_delivery_date":
                format_utc_iso(
                    item.get("LINE_DELIVERY_DATE")
                ),

            "vendor_delivery_date":
                format_utc_iso(
                    item.get("VENDORREPLY_DELIVERY_DATE")
                ),

            "hiq_decision":
                "Expired"
        })


    # ============================================================
    # FINAL RESPONSE
    # ============================================================
    return {

        "success": True,

        "has_draft":
            bool(saved_price_map),

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

            "delivery_date":
                format_utc_iso(
                    header["EXPECTED_DELIVERY_DATE"]
                ),

            "payment_term":
                header["PAYMENT_TERM"] or "-",

            "payment_mode":
                header["METHOD_OF_PAYMENT"] or "-",

            "delivery_term":
                header["DELIVERY_TERM"] or "-",

            "delivery_mode":
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

            "reply_delivery_date":
                saved_header.get(
                    "replyDeliveryDate",
                    ""
                ),

            "reply_delivery_mode":
                saved_header.get(
                    "replyModeOfDelivery",
                    ""
                ),

            "reply_delivery_term":
                saved_header.get(
                    "replyDeliveryTerms",
                    ""
                ),

            "saved_vendor_comments":
                saved_header.get(
                    "vendorComments",
                    ""
                ),

            "line_items":
                line_items
        }
    }


# import json
# from app.db.base import get_connection
# from app.utils.date_utils import format_date,format_utc_iso
# from app.utils.remainingdate import calculate_days_left


# def fetch_rfq_detail(rfq_id: str, vendor_account: str):

#     header_query = """
#         SELECT
#             L.RFQCASEID,
#             T.RFQID,
#             L.NAME              AS DOCUMENT_TITLE,
#             L.EXPIRYDATETIME    AS CLOSING_DATE,
#             L.CREATEDDATETIME   AS ISSUE_DATE,
#             L.DELIVERYDATE      AS EXPECTED_DELIVERY_DATE,
#             PT.DESCRIPTION      AS PAYMENT_TERM,
#             PM.NAME             AS METHOD_OF_PAYMENT,
#             DM.TXT              AS MODE_OF_DELIVERY,
#             DT.TXT              AS DELIVERY_TERM,
#             T.HIQ_TERMSANDCONDITIONS

#         FROM PurchRFQCaseTable L WITH (NOLOCK)

#         INNER JOIN PurchRFQTable T WITH (NOLOCK)
#             ON  T.RFQCASEID   = L.RFQCASEID
#             AND T.VENDACCOUNT = ?

#         LEFT JOIN PAYMTERM PT WITH (NOLOCK)
#             ON L.PAYMENT = PT.PAYMTERMID

#         LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
#             ON L.PAYMMODE = PM.PAYMMODE

#         LEFT JOIN DLVMODE DM WITH (NOLOCK)
#             ON L.DLVMODE = DM.CODE

#         LEFT JOIN DLVTERM DT WITH (NOLOCK)
#             ON L.DLVTERM = DT.CODE

#         WHERE T.RFQID = ?
#     """

#     lines_query = """
#         SELECT
#             RL.LINENUM,
#             RL.ITEMID           AS MATERIAL_CODE,
#             IT.NAMEALIAS        AS MATERIAL_DESCRIPTION,
#             RL.QTYORDERED       AS QUANTITY,
#             RL.PURCHUNIT        AS UOM,
#             RL.HIQ_TARGETPRICE  AS TARGETPRICE,
#             RL.HIQ_COMMENTS     AS COMMENTS,
#             RL.CURRENCYCODE,
#             RL.DELIVERYDATE     AS LINE_DELIVERY_DATE,
#             RPL.DELIVERYDATE    AS VENDORREPLY_DELIVERY_DATE   

#         FROM PurchRFQLine RL WITH (NOLOCK)
#         LEFT JOIN PURCHRFQREPLYLINE RPL WITH (NOLOCK)
#             ON  RPL.RFQLINERECID = RL.RECID
#             AND RPL.DATAAREAID   = 'hi-q'

#         LEFT JOIN INVENTTABLE IT WITH (NOLOCK)
#             ON IT.ITEMID = RL.ITEMID

#         INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#             ON  AVL.ITEMID            = RL.ITEMID
#             AND AVL.PDSAPPROVEDVENDOR = ?
#             --AND AVL.VALIDFROM        <= GETUTCDATE()
#             --AND AVL.VALIDTO          >= GETUTCDATE()

#         WHERE RL.RFQID = ?
#         ORDER BY RL.LINENUM
#     """

#     draft_query = """
#         SELECT TOP 1 PAYLOAD_JSON
#         FROM HIQ_VENDORRFQREPLIES WITH (NOLOCK)
#         WHERE RFQ_ID         = ?
#           AND VENDOR_ACCOUNT = ?
#           --AND SUBMISSION_STATUS = 0
#         ORDER BY ID DESC
#     """

#     with get_connection() as conn:
#         cursor = conn.cursor()

#         cursor.execute(header_query, (vendor_account, rfq_id))
#         row = cursor.fetchone()
#         if not row:
#             return {"success": False, "message": "RFQ not found"}

#         cols   = [c[0] for c in cursor.description]
#         header = dict(zip(cols, row))

#         cursor.execute(lines_query, (vendor_account, rfq_id))
#         line_rows = cursor.fetchall()
#         line_cols = [c[0] for c in cursor.description]
#         lines     = [dict(zip(line_cols, r)) for r in line_rows]

#         cursor.execute(draft_query, (rfq_id, vendor_account))
#         draft_row = cursor.fetchone()

#     saved_price_map = {}
#     saved_header    = {}

#     if draft_row and draft_row[0]:
#         try:
#             payload = json.loads(draft_row[0])

#             saved_header = {
#                 "modeOfDelivery":      payload.get("modeOfDelivery", ""),
#                 "DeliveryTerms":       payload.get("DeliveryTerms", ""),
#                 "methodOfPayment":     payload.get("methodOfPayment", ""),
#                 "termsOfPayment":      payload.get("termsOfPayment", ""),
#                 "replyDeliveryDate":   payload.get("replyDeliveryDate", ""),
#                 "replyDeliveryTerms":  payload.get("replyDeliveryTerms", ""),   
#                 "replyModeOfDelivery": payload.get("replyModeOfDelivery", ""),  
#                 "vendorComments":      payload.get("vendorComments", ""),
#             }
            
#             for item in payload.get("Item", []):
#                 item_number = item.get("itemNumber")
#                 line_number = item.get("lineNumber")

#                 if item_number and line_number:
#                     key = (line_number, item_number)

#                     val = item.get("unitPrice")

#                     saved_price_map[key] = {
#                         "unit_price": float(val) if val not in [None, ""] else "",
#                         "net_amount": float(item.get("netAmount")) if item.get("netAmount") not in [None, ""] else "",
#                         "vendor_comments": item.get("vendorComments", ""),
#                         "line_status": item.get("lineStatus", False),
#                     }
#             # for item in payload.get("Item", []):
#             #     item_number = item.get("itemNumber")
#             #     if item_number:
#             #         val = item.get("unitPrice")
#             #         saved_price_map[item_number] = {
#             #             "unit_price":float(val) if val not in [None, ""] else "",
#             #             "net_amount": float(item.get("netAmount")) if item.get("netAmount") not in [None, ""] else "", 
#             #             "vendor_comments": item.get("vendorComments", ""),
#             #             "line_status": item.get("lineStatus", False),
    
#             #         }
#         except Exception:
#             pass

#     line_items = []
#     for item in lines:
#         material_code = item["MATERIAL_CODE"]
#         key = (int(item["LINENUM"]), item["MATERIAL_CODE"])
#         saved = saved_price_map.get(key, {})
#         # saved         = saved_price_map.get(material_code, {})
#         if saved.get("line_status", False):
#             continue
#         line_items.append({
#             "line_num":                int(item["LINENUM"]),
#             "item_name": item["MATERIAL_DESCRIPTION"],
#             "item_id":        material_code,
#             "quantity":             item["QUANTITY"],
#             "uom":                  item["UOM"],
#             "target_price":     round(float(item['TARGETPRICE'] or 0), 2),
#             # "target_price":    f"{round(float(item['TARGETPRICE'] or 0), 2)} {item['CURRENCYCODE']}",
#             "currency":         item["CURRENCYCODE"],
#             "comments":             item["COMMENTS"],
#             "unit_price": saved.get("unit_price", ""),
#             "net_amount": saved.get("net_amount", ""),
#             # "unit_price":           saved.get("unit_price", None),
#             "vendor_comments":              saved.get("vendor_comments", ""),
#             "rfq_delivery_date": format_utc_iso(item.get("LINE_DELIVERY_DATE")),
#             "vendor_delivery_date": format_utc_iso(item.get("VENDORREPLY_DELIVERY_DATE")),
#             "hiq_decision":"Expired",
#         })

#     return {
#         "success": True,
#         "has_draft": bool(saved_price_map),
#         "data": {
#             "rfq_case_id":            header["RFQCASEID"],
#             "rfq_id":                 header["RFQID"],
#             "document_title":         header["DOCUMENT_TITLE"],
#             "issue_date":             format_utc_iso(header["ISSUE_DATE"]),
#             "closing_date":           format_utc_iso(header["CLOSING_DATE"]),
#             "time_remaining":         calculate_days_left(header["CLOSING_DATE"]),
#             "delivery_date": format_utc_iso(header["EXPECTED_DELIVERY_DATE"]),
#             "payment_term":           header["PAYMENT_TERM"]      or "-",
#             "payment_mode":      header["METHOD_OF_PAYMENT"] or "-",
#             "delivery_term":          header["DELIVERY_TERM"]      or "-",
#             "delivery_mode":       header["MODE_OF_DELIVERY"]   or "-",
#             "termsandconditions":     header["HIQ_TERMSANDCONDITIONS"],

#             # ── Saved draft fields (all 8) ─────────────────────
#             "saved_mode_of_delivery":       saved_header.get("modeOfDelivery", ""),
#             "saved_delivery_terms":         saved_header.get("DeliveryTerms", ""),
#             "saved_method_of_payment":      saved_header.get("methodOfPayment", ""),
#             "saved_terms_of_payment":       saved_header.get("termsOfPayment", ""),
#             "reply_delivery_date":    saved_header.get("replyDeliveryDate", ""),
#             "reply_delivery_mode": saved_header.get("replyModeOfDelivery", ""),   
#             "reply_delivery_term": saved_header.get("replyDeliveryTerms", ""),
#             "saved_vendor_comments":        saved_header.get("vendorComments", ""),

#             "line_items": line_items
#         }
#     }

