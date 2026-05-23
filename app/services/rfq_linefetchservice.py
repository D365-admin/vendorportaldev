import json

from app.db.base import (
    get_connection
)

from app.utils.date_utils import (
    format_utc_iso
)

from app.utils.remainingdate import (
    calculate_days_left
)

from app.core.config import settings


SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = (
    f"{SCHEMA}.HIQ_VendorRFQReplies"
)


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
    header_query = """
        SELECT

            C.RFQCASEID,

            T.RFQID,

            C.NAME
                AS DOCUMENT_TITLE,

            C.EXPIRYDATETIME
                AS CLOSING_DATE,

            C.CREATEDDATETIME
                AS ISSUE_DATE,

            C.DELIVERYDATE
                AS EXPECTED_DELIVERY_DATE,

            PT.DESCRIPTION
                AS PAYMENT_TERM,

            PM.NAME
                AS METHOD_OF_PAYMENT,

            DM.TXT
                AS MODE_OF_DELIVERY,

            DT.TXT
                AS DELIVERY_TERM,

            T.HIQ_TERMSANDCONDITIONS

        FROM D365_PURCHRFQCASETABLE C
        WITH (NOLOCK)

        INNER JOIN D365_PURCHRFQTABLE T
        WITH (NOLOCK)

            ON T.RFQCASEID = C.RFQCASEID
           AND T.VENDACCOUNT = ?

        LEFT JOIN D365_PAYMTERM PT
        WITH (NOLOCK)

            ON C.PAYMENT = PT.PAYMTERMID

        LEFT JOIN D365_PAYMMODETABLE PM
        WITH (NOLOCK)

            ON C.PAYMMODE = PM.PAYMMODE

        LEFT JOIN D365_DLVMODE DM
        WITH (NOLOCK)

            ON C.DLVMODE = DM.CODE

        LEFT JOIN D365_DLVTERM DT
        WITH (NOLOCK)

            ON C.DLVTERM = DT.CODE

        WHERE T.RFQID = ?
    """


    # ========================================================
    # LINE QUERY
    # ========================================================
    lines_query = """
        SELECT

            RL.LINENUM,

            RL.ITEMID
                AS MATERIAL_CODE,

            IT.NAME
                AS MATERIAL_DESCRIPTION,

            RL.QTYORDERED
                AS QUANTITY,

            RL.PURCHUNIT
                AS UOM,

            RL.HIQ_TARGETPRICE
                AS TARGETPRICE,

            RL.HIQ_COMMENTS
                AS COMMENTS,

            RL.CURRENCYCODE,

            RL.DELIVERYDATE
                AS LINE_DELIVERY_DATE

        FROM D365_PURCHRFQLINE RL
        WITH (NOLOCK)

        LEFT JOIN D365_INVENTTABLE IT
        WITH (NOLOCK)

            ON IT.ITEMID = RL.ITEMID

        INNER JOIN D365_PDSAPPROVEDVENDORLIST AVL
        WITH (NOLOCK)

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

            PAYLOADJSON

        FROM {RFQ_REPLIES_TABLE}
        WITH (NOLOCK)

        WHERE RFQID = ?
          AND VENDORACCOUNT = ?
          AND SUBMISSIONSTATUS = 0

        ORDER BY ID DESC
    """


    # ========================================================
    # FETCH HEADER + LINES + DRAFT
    # ========================================================
    with get_connection() as conn:

        cursor = conn.cursor()

        # ====================================================
        # HEADER
        # ====================================================
        cursor.execute(
            header_query,
            (
                vendor_account,
                rfq_id
            )
        )

        row = cursor.fetchone()

        if not row:

            return {
                "success": False,
                "message": "RFQ not found"
            }

        cols = [
            c[0]
            for c in cursor.description
        ]

        header = dict(zip(cols, row))


        # ====================================================
        # LINES
        # ====================================================
        cursor.execute(
            lines_query,
            (
                vendor_account,
                rfq_id
            )
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


        # ====================================================
        # DRAFT
        # ====================================================
        cursor.execute(
            draft_query,
            (
                rfq_id,
                vendor_account
            )
        )

        draft_row = cursor.fetchone()


    # ========================================================
    # PARSE SAVED DRAFT
    # ========================================================
    saved_price_map = {}

    saved_header = {}

    if draft_row and draft_row[0]:

        try:

            payload = json.loads(
                draft_row[0]
            )

            saved_header = {

                "modeOfDelivery":
                    payload.get(
                        "modeOfDelivery",
                        ""
                    ),

                "DeliveryTerms":
                    payload.get(
                        "DeliveryTerms",
                        ""
                    ),

                "methodOfPayment":
                    payload.get(
                        "methodOfPayment",
                        ""
                    ),

                "termsOfPayment":
                    payload.get(
                        "termsOfPayment",
                        ""
                    ),

                "replyDeliveryDate":
                    payload.get(
                        "replyDeliveryDate",
                        ""
                    ),

                "replyDeliveryTerms":
                    payload.get(
                        "replyDeliveryTerms",
                        ""
                    ),

                "replyModeOfDelivery":
                    payload.get(
                        "replyModeOfDelivery",
                        ""
                    ),

                "vendorComments":
                    payload.get(
                        "vendorComments",
                        ""
                    ),
            }

            # =================================================
            # LINE VALUES
            # =================================================
            for item in payload.get(
                "Item",
                []
            ):

                line_number = item.get(
                    "lineNumber"
                )

                if line_number is not None:

                    saved_price_map[
                        int(line_number)
                    ] = {

                        "unit_price":
                            item.get(
                                "unitPrice",
                                0
                            ),

                        "vendor_comments":
                            item.get(
                                "vendorComments",
                                ""
                            ),

                        "lineStatus":
                            item.get(
                                "lineStatus"
                            ),

                        "vendor_delivery_date":
                            item.get(
                                "deliveryDate"
                            )
                    }

        except Exception as e:

            print(
                "Draft parse error:",
                e
            )


    # ========================================================
    # BUILD ITEMS
    # ========================================================
    items = []

    for item in lines:

        line_number = int(
            item["LINENUM"]
        )

        saved = saved_price_map.get(
            line_number,
            {}
        )

        unit_price = saved.get(
            "unit_price",
            0
        )

        # ====================================================
        # LINE STATUS
        # ====================================================
        if "lineStatus" in saved:

            line_status = saved.get(
                "lineStatus"
            )

        else:

            line_status = (

                True

                if unit_price > 0

                else False
            )

        vendor_date = saved.get(
            "vendor_delivery_date"
        )

        items.append({

            "sl_no":
                line_number,

            "material_description":
                item[
                    "MATERIAL_DESCRIPTION"
                ],

            "material_code":
                item[
                    "MATERIAL_CODE"
                ],

            "quantity":
                item["QUANTITY"],

            "uom":
                item["UOM"],

            "target_price":

                round(
                    float(
                        item[
                            "TARGETPRICE"
                        ] or 0
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

                format_utc_iso(
                    vendor_date
                )

                if vendor_date

                else None
        })


    # ========================================================
    # FINAL RESPONSE
    # ========================================================
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
                header[
                    "DOCUMENT_TITLE"
                ],

            "issue_date":
                format_utc_iso(
                    header[
                        "ISSUE_DATE"
                    ]
                ),

            "closing_date":
                format_utc_iso(
                    header[
                        "CLOSING_DATE"
                    ]
                ),

            "time_remaining":
                calculate_days_left(
                    header[
                        "CLOSING_DATE"
                    ]
                ),

            "expected_delivery_date":
                format_utc_iso(
                    header[
                        "EXPECTED_DELIVERY_DATE"
                    ]
                ),

            "payment_term":
                header[
                    "PAYMENT_TERM"
                ] or "-",

            "method_of_payment":
                header[
                    "METHOD_OF_PAYMENT"
                ] or "-",

            "delivery_term":
                header[
                    "DELIVERY_TERM"
                ] or "-",

            "mode_of_delivery":
                header[
                    "MODE_OF_DELIVERY"
                ] or "-",

            "termsandconditions":
                header[
                    "HIQ_TERMSANDCONDITIONS"
                ],

            # ================================================
            # SAVED VALUES
            # ================================================
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
                saved_header.get(
                    "replyDeliveryDate",
                    ""
                ),

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

# from app.db.base import (
#     get_connection,
#     get_connection
# )

# from app.utils.date_utils import (
#     format_utc_iso
# )

# from app.utils.remainingdate import (
#     calculate_days_left
# )
# from app.core.config import settings

# SCHEMA = settings.DB_SCHEMA

# RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"

# def fetch_rfq_detail(
#     rfq_id: str,
#     vendor_account: str
# ):

#     # ─────────────────────────────────────────────
#     # D365 HEADER QUERY
#     # ─────────────────────────────────────────────
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


#     # ─────────────────────────────────────────────
#     # D365 LINES QUERY
#     # ─────────────────────────────────────────────
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

#             RL.DELIVERYDATE     AS LINE_DELIVERY_DATE

#         FROM PurchRFQLine RL WITH (NOLOCK)

#         LEFT JOIN INVENTTABLE IT WITH (NOLOCK)
#             ON IT.ITEMID = RL.ITEMID

#         INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#             ON UPPER(LTRIM(RTRIM(AVL.ITEMID)))
#              = UPPER(LTRIM(RTRIM(RL.ITEMID)))

#             AND AVL.PDSAPPROVEDVENDOR = ?

#             AND AVL.VALIDFROM <= GETUTCDATE()

#             AND AVL.VALIDTO >= GETUTCDATE()

#         WHERE RL.RFQID = ?

#         ORDER BY RL.LINENUM
#     """


#     # ─────────────────────────────────────────────
#     # PORTAL DB DRAFT QUERY
#     # ─────────────────────────────────────────────
#     draft_query = f"""
#         SELECT TOP 1 PAYLOADJSON

#         FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)

#         WHERE RFQID = ?

#           AND VENDORACCOUNT = ?

#           AND SUBMISSIONSTATUS = 0

#         ORDER BY ID DESC
#     """


#     # ============================================================
#     # STEP 1 → FETCH HEADER + LINES FROM D365 DB
#     # ============================================================
#     with get_connection() as conn:

#         cursor = conn.cursor()

#         # HEADER
#         cursor.execute(
#             header_query,
#             (vendor_account, rfq_id)
#         )

#         row = cursor.fetchone()

#         if not row:
#             return {
#                 "success": False,
#                 "message": "RFQ not found"
#             }

#         cols = [c[0] for c in cursor.description]

#         header = dict(zip(cols, row))


#         # LINES
#         cursor.execute(
#             lines_query,
#             (vendor_account, rfq_id)
#         )

#         line_rows = cursor.fetchall()

#         line_cols = [c[0] for c in cursor.description]

#         lines = [
#             dict(zip(line_cols, r))
#             for r in line_rows
#         ]


#     # ============================================================
#     # STEP 2 → FETCH DRAFT FROM PORTAL DB
#     # ============================================================
#     with get_connection() as conn:

#         cursor = conn.cursor()

#         cursor.execute(
#             draft_query,
#             (rfq_id, vendor_account)
#         )

#         draft_row = cursor.fetchone()


#     # ============================================================
#     # STEP 3 → PARSE SAVED DRAFT
#     # ============================================================
#     saved_price_map = {}

#     saved_header = {}


#     if draft_row and draft_row[0]:

#         try:

#             payload = json.loads(draft_row[0])

#             # HEADER VALUES
#             saved_header = {
#                 "modeOfDelivery":
#                     payload.get("modeOfDelivery", ""),

#                 "DeliveryTerms":
#                     payload.get("DeliveryTerms", ""),

#                 "methodOfPayment":
#                     payload.get("methodOfPayment", ""),

#                 "termsOfPayment":
#                     payload.get("termsOfPayment", ""),

#                 "replyDeliveryDate":
#                     payload.get("replyDeliveryDate", ""),

#                 "replyDeliveryTerms":
#                     payload.get("replyDeliveryTerms", ""),

#                 "replyModeOfDelivery":
#                     payload.get("replyModeOfDelivery", ""),

#                 "vendorComments":
#                     payload.get("vendorComments", ""),
#             }

#             # LINE VALUES
#             for item in payload.get("Item", []):

#                 line_number = item.get("lineNumber")

#                 if line_number is not None:

#                     saved_price_map[int(line_number)] = {
#                         "unit_price":
#                             item.get("unitPrice", 0),

#                         "vendor_comments":
#                             item.get("vendorComments", ""),

#                         "lineStatus":
#                             item.get("lineStatus"),

#                         "vendor_delivery_date":
#                             item.get("deliveryDate")
#                     }

#         except Exception as e:

#             print("Draft parse error:", e)


#     # ============================================================
#     # STEP 4 → BUILD ITEMS
#     # ============================================================
#     items = []

#     for item in lines:

#         line_number = int(item["LINENUM"])

#         saved = saved_price_map.get(line_number, {})

#         unit_price = saved.get("unit_price", 0)


#         # LINE STATUS
#         if "lineStatus" in saved:

#             line_status = saved.get("lineStatus")

#         else:

#             line_status = True if unit_price > 0 else False


#         vendor_date = saved.get("vendor_delivery_date")


#         items.append({

#             "sl_no":
#                 line_number,

#             "material_description":
#                 item["MATERIAL_DESCRIPTION"],

#             "material_code":
#                 item["MATERIAL_CODE"],

#             "quantity":
#                 item["QUANTITY"],

#             "uom":
#                 item["UOM"],

#             "target_price":
#                 round(float(item["TARGETPRICE"] or 0), 2),

#             "comments":
#                 item["COMMENTS"],

#             "unit_price":
#                 unit_price,

#             "remarks":
#                 saved.get("vendor_comments", ""),

#             "lineStatus":
#                 line_status,

#             "currency":
#                 item.get("CURRENCYCODE"),

#             "rfq_delivery_date":
#                 format_utc_iso(
#                     item.get("LINE_DELIVERY_DATE")
#                 ),

#             "vendor_delivery_date":
#                 format_utc_iso(vendor_date)
#                 if vendor_date else None
#         })


#     # ============================================================
#     # FINAL RESPONSE
#     # ============================================================
#     return {

#         "success": True,

#         "has_draft": bool(saved_price_map),

#         "data": {

#             "rfq_case_id":
#                 header["RFQCASEID"],

#             "rfq_id":
#                 header["RFQID"],

#             "document_title":
#                 header["DOCUMENT_TITLE"],

#             "issue_date":
#                 format_utc_iso(header["ISSUE_DATE"]),

#             "closing_date":
#                 format_utc_iso(header["CLOSING_DATE"]),

#             "time_remaining":
#                 calculate_days_left(
#                     header["CLOSING_DATE"]
#                 ),

#             "expected_delivery_date":
#                 format_utc_iso(
#                     header["EXPECTED_DELIVERY_DATE"]
#                 ),

#             "payment_term":
#                 header["PAYMENT_TERM"] or "-",

#             "method_of_payment":
#                 header["METHOD_OF_PAYMENT"] or "-",

#             "delivery_term":
#                 header["DELIVERY_TERM"] or "-",

#             "mode_of_delivery":
#                 header["MODE_OF_DELIVERY"] or "-",

#             "termsandconditions":
#                 header["HIQ_TERMSANDCONDITIONS"],


#             # SAVED HEADER VALUES
#             "saved_mode_of_delivery":
#                 saved_header.get("modeOfDelivery", ""),

#             "saved_delivery_terms":
#                 saved_header.get("DeliveryTerms", ""),

#             "saved_method_of_payment":
#                 saved_header.get("methodOfPayment", ""),

#             "saved_terms_of_payment":
#                 saved_header.get("termsOfPayment", ""),

#             "saved_reply_delivery_date":
#                 saved_header.get("replyDeliveryDate", ""),

#             "saved_reply_delivery_terms":
#                 saved_header.get("replyDeliveryTerms", ""),

#             "saved_reply_mode_of_delivery":
#                 saved_header.get("replyModeOfDelivery", ""),

#             "saved_vendor_comments":
#                 saved_header.get("vendorComments", ""),


#             "items":
#                 items
#         }
#     }


# # import json
# # from app.db.base import get_connection
# # from app.utils.date_utils import format_date,format_utc_iso
# # from app.utils.remainingdate import calculate_days_left


# # def fetch_rfq_detail(rfq_id: str, vendor_account: str):

# #     header_query = """
# #         SELECT
# #             L.RFQCASEID,
# #             T.RFQID,
# #             L.NAME              AS DOCUMENT_TITLE,
# #             L.EXPIRYDATETIME    AS CLOSING_DATE,
# #             L.CREATEDDATETIME   AS ISSUE_DATE,
# #             L.DELIVERYDATE      AS EXPECTED_DELIVERY_DATE,
# #             PT.DESCRIPTION      AS PAYMENT_TERM,
# #             PM.NAME             AS METHOD_OF_PAYMENT,
# #             DM.TXT              AS MODE_OF_DELIVERY,
# #             DT.TXT              AS DELIVERY_TERM,
# #             T.HIQ_TERMSANDCONDITIONS
# #         FROM PurchRFQCaseTable L WITH (NOLOCK)
# #         INNER JOIN PurchRFQTable T WITH (NOLOCK)
# #             ON  T.RFQCASEID   = L.RFQCASEID
# #             AND T.VENDACCOUNT = ?
# #         LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# #             ON L.PAYMENT = PT.PAYMTERMID
# #         LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# #             ON L.PAYMMODE = PM.PAYMMODE
# #         LEFT JOIN DLVMODE DM WITH (NOLOCK)
# #             ON L.DLVMODE = DM.CODE
# #         LEFT JOIN DLVTERM DT WITH (NOLOCK)
# #             ON L.DLVTERM = DT.CODE
# #         WHERE T.RFQID = ?
# #     """

# #     lines_query = """
# #         SELECT
# #             RL.LINENUM,
# #             RL.ITEMID           AS MATERIAL_CODE,
# #             IT.NAMEALIAS        AS MATERIAL_DESCRIPTION,
# #             RL.QTYORDERED       AS QUANTITY,
# #             RL.PURCHUNIT        AS UOM,
# #             RL.HIQ_TARGETPRICE  AS TARGETPRICE,
# #             RL.HIQ_COMMENTS     AS COMMENTS,
# #             RL.CURRENCYCODE,
# #             RL.DELIVERYDATE     AS LINE_DELIVERY_DATE   

# #         FROM PurchRFQLine RL WITH (NOLOCK)
# #         LEFT JOIN INVENTTABLE IT WITH (NOLOCK)
# #             ON IT.ITEMID = RL.ITEMID
# #         INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
# #            ON UPPER(LTRIM(RTRIM(AVL.ITEMID))) = UPPER(LTRIM(RTRIM(RL.ITEMID)))
# #             --ON  AVL.ITEMID            = RL.ITEMID
# #             AND AVL.PDSAPPROVEDVENDOR = ?
# #             AND AVL.VALIDFROM        <= GETUTCDATE()
# #             AND AVL.VALIDTO          >= GETUTCDATE()
# #         WHERE RL.RFQID = ?
# #         ORDER BY RL.LINENUM
# #     """

# #     draft_query = """
# #         SELECT TOP 1 PAYLOAD_JSON
# #         FROM HIQ_VENDORRFQREPLIES WITH (NOLOCK)
# #         WHERE RFQ_ID         = ?
# #           AND VENDOR_ACCOUNT = ?
# #           AND SUBMISSION_STATUS = 0
# #         ORDER BY ID DESC
# #     """

# #     with get_connection() as conn:
# #         cursor = conn.cursor()

# #         # HEADER
# #         cursor.execute(header_query, (vendor_account, rfq_id))
# #         row = cursor.fetchone()

# #         if not row:
# #             return {"success": False, "message": "RFQ not found"}

# #         cols = [c[0] for c in cursor.description]
# #         header = dict(zip(cols, row))

# #         # LINES
# #         cursor.execute(lines_query, (vendor_account, rfq_id))
# #         line_rows = cursor.fetchall()
# #         line_cols = [c[0] for c in cursor.description]
# #         lines = [dict(zip(line_cols, r)) for r in line_rows]

# #         # DRAFT
# #         cursor.execute(draft_query, (rfq_id, vendor_account))
# #         draft_row = cursor.fetchone()

# #     # ===============================
# #     # ✅ FIXED MAPPING (LINE NUMBER)
# #     # ===============================
# #     saved_price_map = {}
# #     saved_header = {}

# #     if draft_row and draft_row[0]:
# #         try:
# #             payload = json.loads(draft_row[0])

# #             # HEADER VALUES
# #             saved_header = {
# #                 "modeOfDelivery": payload.get("modeOfDelivery", ""),
# #                 "DeliveryTerms": payload.get("DeliveryTerms", ""),
# #                 "methodOfPayment": payload.get("methodOfPayment", ""),
# #                 "termsOfPayment": payload.get("termsOfPayment", ""),
# #                 "replyDeliveryDate": payload.get("replyDeliveryDate", ""),
# #                 "replyDeliveryTerms": payload.get("replyDeliveryTerms", ""),
# #                 "replyModeOfDelivery": payload.get("replyModeOfDelivery", ""),
# #                 "vendorComments": payload.get("vendorComments", ""),
# #             }

# #             # KEY CHANGE HERE (lineNumber)
# #             for item in payload.get("Item", []):
# #                 line_number = item.get("lineNumber")

# #                 if line_number is not None:
# #                     saved_price_map[int(line_number)] = {
# #                         "unit_price": item.get("unitPrice", 0),
# #                         "vendor_comments": item.get("vendorComments", ""),
# #                         "lineStatus": item.get("lineStatus"),
# #                         "vendor_delivery_date": item.get("deliveryDate")
# #                     }

# #         except Exception as e:
# #             print("Draft parse error:", e)

# #     # ===============================
# #     # BUILD RESPONSE
# #     # ===============================
# #     items = []

# #     for item in lines:
# #         line_number = int(item["LINENUM"])
# #         saved = saved_price_map.get(line_number, {})

# #         unit_price = saved.get("unit_price", 0)

# #         # LINE STATUS LOGIC
# #         if "lineStatus" in saved:
# #             line_status = saved.get("lineStatus")
# #         else:
# #             line_status = True if unit_price > 0 else False
        
# #         vendor_date = saved.get("vendor_delivery_date")
# #         items.append({
# #             "sl_no": line_number,
# #             "material_description": item["MATERIAL_DESCRIPTION"],
# #             "material_code": item["MATERIAL_CODE"],
# #             "quantity": item["QUANTITY"],
# #             "uom": item["UOM"],
# #             "target_price": round(float(item["TARGETPRICE"] or 0), 2),
# #             "comments": item["COMMENTS"],
# #             "unit_price": unit_price,
# #             "remarks": saved.get("vendor_comments", ""),
# #             "lineStatus": line_status,
# #             "currency": item.get("CURRENCYCODE"),
# #             "rfq_delivery_date": format_utc_iso(item.get("LINE_DELIVERY_DATE")),
# #              "vendor_delivery_date": format_utc_iso(vendor_date) if vendor_date else None
# #         })

# #     return {
# #         "success": True,
# #         "has_draft": bool(saved_price_map),
# #         "data": {
# #             "rfq_case_id": header["RFQCASEID"],
# #             "rfq_id": header["RFQID"],
# #             "document_title": header["DOCUMENT_TITLE"],
# #             "issue_date": format_utc_iso(header["ISSUE_DATE"]),
# #             "closing_date": format_utc_iso(header["CLOSING_DATE"]),
# #             "time_remaining": calculate_days_left(header["CLOSING_DATE"]),
# #             "expected_delivery_date": format_utc_iso(header["EXPECTED_DELIVERY_DATE"]),
# #             "payment_term": header["PAYMENT_TERM"] or "-",
# #             "method_of_payment": header["METHOD_OF_PAYMENT"] or "-",
# #             "delivery_term": header["DELIVERY_TERM"] or "-",
# #             "mode_of_delivery": header["MODE_OF_DELIVERY"] or "-",
# #             "termsandconditions": header["HIQ_TERMSANDCONDITIONS"],

# #             # SAVED VALUES
# #             "saved_mode_of_delivery": saved_header.get("modeOfDelivery", ""),
# #             "saved_delivery_terms": saved_header.get("DeliveryTerms", ""),
# #             "saved_method_of_payment": saved_header.get("methodOfPayment", ""),
# #             "saved_terms_of_payment": saved_header.get("termsOfPayment", ""),
# #             "saved_reply_delivery_date": saved_header.get("replyDeliveryDate", ""),
# #             "saved_reply_delivery_terms": saved_header.get("replyDeliveryTerms", ""),
# #             "saved_reply_mode_of_delivery": saved_header.get("replyModeOfDelivery", ""),
# #             "saved_vendor_comments": saved_header.get("vendorComments", ""),

# #             "items": items
# #         }
# #     }


