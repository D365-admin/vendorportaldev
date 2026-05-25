from app.utils.lastused_time import (
    format_last_edited
)

from app.utils.date_utils import (
    format_utc_iso
)

from app.utils.remainingdate import (
    calculate_days_left
)

from app.db.base import (
    get_connection
)

from app.core.config import settings


SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"


def fetch_inprogress_rfqs(
    vendor_account: str
):

    # ========================================================
    # STEP 1
    # FETCH LATEST RFQ REPLIES
    # ========================================================
    reply_query = f"""
        SELECT

            RFQID,
            VENDORACCOUNT,
            CREATEDDATETIME,
            SUBMISSIONSTATUS,
            ID,
            CONFIRMSAVE,
            UNCONFIRMEDLINECOUNT,
            TOTALLINES,
            DRAFTLINECOUNT,
            CONFIRMEDLINECOUNT

        FROM (

            SELECT *,

                ROW_NUMBER() OVER (
                    PARTITION BY RFQID, VENDORACCOUNT
                    ORDER BY ID DESC
                ) AS RN

            FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)

            WHERE VENDORACCOUNT = ?

        ) X

        WHERE
            RN = 1
            AND SUBMISSIONSTATUS IN (0, 2)
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            reply_query,
            vendor_account
        )

        reply_rows = cursor.fetchall()

        reply_columns = [
            c[0]
            for c in cursor.description
        ]

        reply_data = [
            dict(zip(reply_columns, r))
            for r in reply_rows
        ]

    # ========================================================
    # NO DATA
    # ========================================================
    if not reply_data:
        return []

    # ========================================================
    # RFQ IDS
    # ========================================================
    rfq_ids = [
        r["RFQID"]
        for r in reply_data
    ]

    # ========================================================
    # COMPOSITE KEY MAP
    # ========================================================
    reply_map = {

        (
            r["RFQID"],
            r["VENDORACCOUNT"]
        ): r

        for r in reply_data
    }

    # ========================================================
    # SQL PLACEHOLDERS
    # ========================================================
    placeholders = ",".join(
        ["?"] * len(rfq_ids)
    )

    # ========================================================
    # STEP 2
    # FETCH RFQ DETAILS
    # ========================================================
    d365_query = f"""
        SELECT

            C.RFQCASEID,

            T.RFQID,

            T.VENDACCOUNT,

            C.NAME AS DOCUMENT_TITLE,

            C.EXPIRYDATETIME AS CLOSING_DATE,

            C.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,

            DM.TXT AS MODE_OF_DELIVERY,

            PT.DESCRIPTION AS PAYMENT_TERM,

            DT.TXT AS DELIVERY_TERM,

            PM.NAME AS PAYMENT_MODE

        FROM {SCHEMA}.D365_PURCHRFQCASETABLE C WITH (NOLOCK)

        INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T WITH (NOLOCK)
            ON T.RFQCASEID = C.RFQCASEID
            AND T.VENDACCOUNT = ?

        LEFT JOIN {SCHEMA}.D365_DLVMODE DM WITH (NOLOCK)
            ON C.DLVMODE = DM.CODE

        LEFT JOIN {SCHEMA}.D365_PAYMTERM PT WITH (NOLOCK)
            ON C.PAYMENT = PT.PAYMTERMID

        LEFT JOIN {SCHEMA}.D365_DLVTERM DT WITH (NOLOCK)
            ON C.DLVTERM = DT.CODE

        LEFT JOIN {SCHEMA}.D365_PAYMMODETABLE PM WITH (NOLOCK)
            ON C.PAYMMODE = PM.PAYMMODE

        WHERE
            T.RFQID IN ({placeholders})

            AND (

                CAST(
                    DATEADD(
                        MINUTE,
                        330,
                        C.EXPIRYDATETIME
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

                OR T.RFQID IN ({placeholders})
            )

        ORDER BY
            C.EXPIRYDATETIME ASC
    """

    # ========================================================
    # QUERY PARAMS
    # ========================================================
    params = (
        [vendor_account]
        + rfq_ids
        + rfq_ids
    )

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            d365_query,
            params
        )

        columns = [
            c[0]
            for c in cursor.description
        ]

        rows = cursor.fetchall()

    # ========================================================
    # STEP 3
    # BUILD RESPONSE
    # ========================================================
    result = []

    for row in rows:

        data = dict(zip(columns, row))

        rfq_id = data["RFQID"]

        vend_account = data["VENDACCOUNT"]

        # ====================================================
        # SAFE LOOKUP
        # ====================================================
        reply = reply_map.get(
            (rfq_id, vend_account)
        )

        if not reply:
            continue

        # ====================================================
        # LAST EDITED
        # ====================================================
        last_edited = reply["CREATEDDATETIME"]

        last_edited_label = (

            format_last_edited(
                last_edited
            )

            if last_edited
            else "N/A"
        )

        # ====================================================
        # STATUS LABEL
        # ====================================================
        confirm_save_raw = reply["CONFIRMSAVE"]

        confirm_save_map = {

            "confirmSave":
                "Confirm Save",

            "save_progress":
                "Inprogress",
        }

        confirm_save_label = (
            confirm_save_map.get(
                confirm_save_raw,
                confirm_save_raw
            )
        )

        # ====================================================
        # FINAL ITEM
        # ====================================================
        result.append({

            "rfq_id":
                rfq_id,

            "rfq_case_id":
                data["RFQCASEID"],

            "expiry_date":
                format_utc_iso(
                    data["CLOSING_DATE"]
                ),

            "last_edited":
                last_edited_label,

            "delivery_date":
                format_utc_iso(
                    data["EXPECTED_DELIVERY_DATE"]
                ),

            "delivery_mode":
                data["MODE_OF_DELIVERY"],

            "payment_mode":
                data["PAYMENT_MODE"],

            "status":
                confirm_save_label,

            "confirm_save":
                reply["CONFIRMSAVE"],

            "reply_id":
                reply["ID"],

            "payment_term":
                data["PAYMENT_TERM"],

            "delivery_term":
                data["DELIVERY_TERM"],

            "dates_left":
                calculate_days_left(
                    data["CLOSING_DATE"]
                ),

            "unfilled_count":
                reply["UNCONFIRMEDLINECOUNT"] or 0,

            "totallines":
                reply["TOTALLINES"],

            "confirmedlinecount":
                reply["CONFIRMEDLINECOUNT"],

            "draftlinecount":
                reply["DRAFTLINECOUNT"]
        })

    # ========================================================
    # FINAL RETURN
    # ========================================================
    return result



# from app.utils.lastused_time import format_last_edited

# from app.utils.date_utils import (
#     format_utc_iso
# )

# from app.utils.remainingdate import (
#     calculate_days_left
# )

# from app.db.base import (
#     get_connection,
#     get_connection
# )

# from app.core.config import settings

# SCHEMA = settings.DB_SCHEMA

# RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"
# def fetch_inprogress_rfqs(
#     vendor_account: str
# ):

#     # ============================================================
#     # STEP 1
#     # FETCH LATEST RFQ REPLIES FROM VENDOR PORTAL DB
#     # ============================================================
#     reply_query = f"""
#         SELECT
#             RFQID,
#             VENDORACCOUNT,
#             CREATEDDATETIME,
#             SUBMISSIONSTATUS,
#             ID,
#             CONFIRMSAVE,
#             UNCONFIRMEDLINECOUNT,
#             TOTALLINES,
#             DRAFTLINECOUNT,
#             CONFIRMEDLINECOUNT

#         FROM (
#             SELECT *,
#                 ROW_NUMBER() OVER (
#                     PARTITION BY RFQID, VENDORACCOUNT
#                     ORDER BY ID DESC
#                 ) AS RN

#             FROM {RFQ_REPLIES_TABLE}  WITH (NOLOCK)

#             WHERE
#                 VENDORACCOUNT = ?
#         ) X

#         WHERE
#             RN = 1
#             AND SUBMISSIONSTATUS IN (0, 2)
#     """


#     with get_connection() as conn:

#         cursor = conn.cursor()

#         cursor.execute(
#             reply_query,
#             vendor_account
#         )

#         reply_rows = cursor.fetchall()

#         reply_columns = [
#             c[0]
#             for c in cursor.description
#         ]

#         reply_data = [
#             dict(zip(reply_columns, r))
#             for r in reply_rows
#         ]


#     # ============================================================
#     # NO DATA
#     # ============================================================
#     if not reply_data:
#         return []


#     # ============================================================
#     # RFQ IDS
#     # ============================================================
#     rfq_ids = [
#         r["RFQID"]
#         for r in reply_data
#     ]


#     # ============================================================
#     # COMPOSITE KEY MAP
#     # VERY IMPORTANT
#     # RFQ_ID + VENDOR_ACCOUNT
#     # ============================================================
#     reply_map = {
#         (
#             r["RFQID"],
#             r["VENDORACCOUNT"]
#         ): r

#         for r in reply_data
#     }


#     # ============================================================
#     # SQL PLACEHOLDERS
#     # ============================================================
#     placeholders = ",".join(
#         ["?"] * len(rfq_ids)
#     )


#     # ============================================================
#     # STEP 2
#     # FETCH RFQ DETAILS FROM D365 DB
#     # ============================================================
#     d365_query = f"""
#         SELECT
#             L.RFQCASEID,

#             T.RFQID,

#             T.VENDACCOUNT,

#             L.NAME AS DOCUMENT_TITLE,

#             L.EXPIRYDATETIME AS CLOSING_DATE,

#             L.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,

#             DM.TXT AS MODE_OF_DELIVERY,

#             PT.DESCRIPTION AS PAYMENT_TERM,

#             DT.TXT AS DELIVERY_TERM,

#             PM.NAME AS PAYMENT_MODE

#         FROM PurchRFQCaseTable L WITH (NOLOCK)

#         INNER JOIN PurchRFQTable T WITH (NOLOCK)
#             ON T.RFQCASEID = L.RFQCASEID
#             AND T.VENDACCOUNT = ?

#         LEFT JOIN DLVMODE DM WITH (NOLOCK)
#             ON L.DLVMODE = DM.CODE

#         LEFT JOIN PAYMTERM PT WITH (NOLOCK)
#             ON L.PAYMENT = PT.PAYMTERMID

#         LEFT JOIN DLVTERM DT WITH (NOLOCK)
#             ON L.DLVTERM = DT.CODE

#         LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
#             ON L.PAYMMODE = PM.PAYMMODE

#         WHERE
#             T.RFQID IN ({placeholders})

#             AND (
#                 CAST(
#                     DATEADD(MINUTE,330,L.EXPIRYDATETIME)
#                     AS DATE
#                 )

#                 >=

#                 CAST(
#                     DATEADD(MINUTE,330,GETUTCDATE())
#                     AS DATE
#                 )

#                 OR T.RFQID IN ({placeholders})
#             )

#         ORDER BY
#             L.EXPIRYDATETIME ASC
#     """


#     # ============================================================
#     # QUERY PARAMS
#     # ============================================================
#     params = (
#         [vendor_account]
#         + rfq_ids
#         + rfq_ids
#     )


#     with get_connection() as conn:

#         cursor = conn.cursor()

#         cursor.execute(
#             d365_query,
#             params
#         )

#         columns = [
#             c[0]
#             for c in cursor.description
#         ]

#         rows = cursor.fetchall()


#     # ============================================================
#     # STEP 3
#     # BUILD FINAL RESPONSE
#     # ============================================================
#     result = []


#     for row in rows:

#         data = dict(zip(columns, row))

#         rfq_id = data["RFQID"]

#         vend_account = data["VENDACCOUNT"]


#         # ========================================================
#         # SAFE LOOKUP USING COMPOSITE KEY
#         # ========================================================
#         reply = reply_map.get(
#             (rfq_id, vend_account)
#         )


#         if not reply:
#             continue


#         # ========================================================
#         # LAST EDITED
#         # ========================================================
#         last_edited = reply["CREATEDDATETIME"]

#         last_edited_label = (
#             format_last_edited(last_edited)
#             if last_edited else "N/A"
#         )


#         # ========================================================
#         # STATUS LABEL
#         # ========================================================
#         confirm_save_raw = reply["CONFIRMSAVE"]


#         confirm_save_map = {
#             "confirmSave": "Confirm Save",
#             "save_progress": "Inprogress",
#         }


#         confirm_save_label = (
#             confirm_save_map.get(
#                 confirm_save_raw,
#                 confirm_save_raw
#             )
#         )


#         # ========================================================
#         # FINAL RESPONSE ITEM
#         # ========================================================
#         result.append({

#             "rfq_id":
#                 rfq_id,

#             "rfq_case_id":
#                 data["RFQCASEID"],

#             "expiry_date":
#                 format_utc_iso(
#                     data["CLOSING_DATE"]
#                 ),

#             "last_edited":
#                 last_edited_label,

#             "delivery_date":
#                 format_utc_iso(
#                     data["EXPECTED_DELIVERY_DATE"]
#                 ),

#             "delivery_mode":
#                 data["MODE_OF_DELIVERY"],

#             "payment_mode":
#                 data["PAYMENT_MODE"],

#             "status":
#                 confirm_save_label,

#             "confirm_save":
#                 reply["CONFIRMSAVE"],

#             "reply_id":
#                 reply["ID"],

#             "payment_term":
#                 data["PAYMENT_TERM"],

#             "delivery_term":
#                 data["DELIVERY_TERM"],

#             "dates_left":
#                 calculate_days_left(
#                     data["CLOSING_DATE"]
#                 ),

#             "unfilled_count":
#                 reply["UNCONFIRMEDLINECOUNT"] or 0,

#             "totallines":
#                 reply["TOTALLINES"],

#             "confirmedlinecount":
#                 reply["CONFIRMEDLINECOUNT"],

#             "draftlinecount":
#                 reply["DRAFTLINECOUNT"]
#         })


#     # ============================================================
#     # FINAL RETURN
#     # ============================================================
#     return result


# # from app.utils.lastused_time import format_last_edited
# # from app.utils.date_utils import format_date,format_utc_iso
# # from app.utils.remainingdate import calculate_days_left, format_expiry_label  # ← add this
# # from app.db.base import get_connection
 
 
# # def fetch_inprogress_rfqs(vendor_account: str):
# #     query="""SELECT
# #     L.RFQCASEID,
# #     T.RFQID,
# #     L.NAME              AS DOCUMENT_TITLE,
# #     L.EXPIRYDATETIME    AS CLOSING_DATE,
# #     L.DELIVERYDATE      AS EXPECTED_DELIVERY_DATE,
# #     DM.TXT              AS MODE_OF_DELIVERY,
# #     R.CREATED_AT        AS LAST_EDITED,
# #     R.SUBMISSION_STATUS AS SUBMISSION_STATUS,
# #     R.ID                AS REPLY_ID,
# #     R.CONFIRM_SAVE      AS CONFIRM_SAVE,
# #     PT.DESCRIPTION      AS PAYMENT_TERM,
# #     DT.TXT              AS DELIVERY_TERM,
# #     PM.NAME             AS PAYMENT_MODE,
# #     R.UNCONFIRMEDLINECOUNT  AS UNFILLED_COUNT,
# #     R.TOTALLINES,
# #     R.DRAFTLINECOUNT,
# #     R.CONFIRMEDLINECOUNT

# # FROM PurchRFQCaseTable L WITH (NOLOCK)

# # INNER JOIN PurchRFQTable T WITH (NOLOCK)
# #     ON  T.RFQCASEID   = L.RFQCASEID
# #     AND T.VENDACCOUNT = ?

# # -- ✅ FIXED: removed status filter here
# # INNER JOIN (
# #     SELECT *,
# #         ROW_NUMBER() OVER (
# #             PARTITION BY RFQ_ID, VENDOR_ACCOUNT
# #             ORDER BY ID DESC   -- always latest
# #         ) AS RN
# #     FROM HIQ_VendorRFQReplies WITH (NOLOCK)
# # ) R
# #     ON  R.RFQ_ID         = T.RFQID
# #     AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
# #     AND R.RN             = 1

# # LEFT JOIN DLVMODE DM WITH (NOLOCK)
# #     ON L.DLVMODE = DM.CODE

# # LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# #     ON L.PAYMENT = PT.PAYMTERMID

# # LEFT JOIN DLVTERM DT WITH (NOLOCK)
# #     ON L.DLVTERM = DT.CODE

# # LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# #     ON L.PAYMMODE = PM.PAYMMODE

# # -- ✅ FIXED: apply filter AFTER picking latest
# # WHERE 
# #     R.SUBMISSION_STATUS IN (0, 2)
# #     AND (
# #         --L.EXPIRYDATETIME >= GETUTCDATE()
# #         CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) >= CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
# #         OR R.SUBMISSION_STATUS = 2
# #     )

# # ORDER BY 
# #     L.EXPIRYDATETIME ASC;
# # """
# # #     query = """
# # #     SELECT
# # #         L.RFQCASEID,
# # #         T.RFQID,
# # #         L.NAME              AS DOCUMENT_TITLE,
# # #         L.EXPIRYDATETIME    AS CLOSING_DATE,
# # #         L.DELIVERYDATE      AS EXPECTED_DELIVERY_DATE,
# # #         DM.TXT              AS MODE_OF_DELIVERY,
# # #         R.CREATED_AT        AS LAST_EDITED,
# # #         R.SUBMISSION_STATUS AS SUBMISSION_STATUS,
# # #         R.ID                AS REPLY_ID,
# # #         R.CONFIRM_SAVE      AS CONFIRM_SAVE,
# # #         PT.DESCRIPTION      AS PAYMENT_TERM,
# # #         DT.TXT              AS DELIVERY_TERM,
# # #         PM.NAME             AS PAYMENT_MODE,
# # #         R.UNCONFIRMEDLINECOUNT  AS UNFILLED_COUNT,
# # #         R.TOTALLINES,
# # #         R.DRAFTLINECOUNT,
# # #         R.CONFIRMEDLINECOUNT

# # #     FROM PurchRFQCaseTable L WITH (NOLOCK)

# # #     INNER JOIN PurchRFQTable T WITH (NOLOCK)
# # #         ON  T.RFQCASEID   = L.RFQCASEID
# # #         AND T.VENDACCOUNT = ?

# # #     INNER JOIN (
# # #         SELECT *,
# # #             ROW_NUMBER() OVER (
# # #                 PARTITION BY RFQ_ID, VENDOR_ACCOUNT
# # #                 ORDER BY ID DESC
# # #             ) AS RN
# # #         FROM HIQ_VendorRFQReplies WITH (NOLOCK)
# # #         WHERE SUBMISSION_STATUS IN (0, 2)
# # #     ) R
# # #         ON  R.RFQ_ID         = T.RFQID
# # #         AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
# # #         AND R.RN             = 1

# # #     LEFT JOIN DLVMODE DM WITH (NOLOCK)
# # #         ON L.DLVMODE = DM.CODE

# # #     LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# # #         ON L.PAYMENT = PT.PAYMTERMID

# # #     LEFT JOIN DLVTERM DT WITH (NOLOCK)
# # #         ON L.DLVTERM = DT.CODE

# # #     LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# # #         ON L.PAYMMODE = PM.PAYMMODE

# # #     WHERE (
# # #         L.EXPIRYDATETIME >= GETDATE()    -- active RFQs
# # #         OR R.SUBMISSION_STATUS = 2       -- OR failed submission, keep even if expired
# # #     )

# # #     ORDER BY 
# # #         --R.SUBMISSION_STATUS DESC,        -- status=2 (failed) floats to top
# # #         L.EXPIRYDATETIME ASC
# # # """

    
# #     with get_connection() as conn:
# #         cursor = conn.cursor()
# #         cursor.execute(query, vendor_account)
 
# #         columns = [c[0] for c in cursor.description]
# #         rows    = cursor.fetchall()
# #         result  = []
 
# #         for row in rows:
# #             data             = dict(zip(columns, row))
# #             last_edited      = data["LAST_EDITED"]
# #             last_edited_label = format_last_edited(last_edited) if last_edited else "N/A"
# #             confirm_save_raw = data["CONFIRM_SAVE"]
 
# #             confirm_save_map = {
# #                 "confirmSave": "Confirm Save",
# #                 "save_progress":  "Inprogress",
# #             }
# #             confirm_save_label = confirm_save_map.get(confirm_save_raw, confirm_save_raw)
# #             result.append({
# #                 "rfq_id":        data["RFQID"],
# #                 "rfq_case_id":   data["RFQCASEID"],
# #                 "expiry_date":  format_utc_iso(data["CLOSING_DATE"]),
# #                 "last_edited":   last_edited_label,
# #                 "delivery_date": format_utc_iso(data["EXPECTED_DELIVERY_DATE"]),
# #                 "delivery_mode": data["MODE_OF_DELIVERY"],
# #                 "payment_mode":data["PAYMENT_MODE"],
# #                 "status"       :confirm_save_label  ,
# #                 "confirm_save":  data["CONFIRM_SAVE"],  
# #                 "reply_id":      data["REPLY_ID"],
# #                 "payment_term":data["PAYMENT_TERM"],
# #                 "delivery_term":data["DELIVERY_TERM"],
# #                 "dates_left":calculate_days_left(data["CLOSING_DATE"]),
# #                 "unfilled_count": data["UNFILLED_COUNT"] or 0,
# #                 "totallines":data["TOTALLINES"],
# #                 "confirmedlinecount":data["CONFIRMEDLINECOUNT"],
# #                 "draftlinecount":data["DRAFTLINECOUNT"]

# #             })
 
# #         return result
 
