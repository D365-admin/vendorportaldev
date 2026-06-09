

from app.db.base import (
    get_connection
)

from app.utils.date_utils import (
    format_utc_iso
)

from app.core.config import settings


SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"
STATUS_DRAFT_ONLY = 3

def fetch_vendor_expired_rfqs(
    vendor_account: str
):

    # ========================================================
    # STEP 1
    # FETCH LATEST REPLIES
    # ========================================================
    reply_query = f"""
        SELECT

            RFQCASEID,
            RFQID,
            VENDORACCOUNT,
            SUBMISSIONSTATUS,
            DRAFTLINECOUNT,
            ID

        FROM (

            SELECT *,

                ROW_NUMBER() OVER (
                    PARTITION BY RFQCASEID, VENDORACCOUNT
                    ORDER BY ID DESC
                ) AS RN

            FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)

            WHERE VENDORACCOUNT = ?

        ) X

        WHERE RN = 1
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
    # REPLY MAP
    # ========================================================
    reply_map = {

        (
            r["RFQCASEID"],
            r["VENDORACCOUNT"]
        ): r

        for r in reply_data
    }

    # ========================================================
    # STEP 2
    # FETCH EXPIRED RFQS
    # ========================================================
    d365_query = f"""
        SELECT

            C.RFQCASEID,

            T.RFQID,

            T.VENDACCOUNT,

            C.NAME AS RFQNAME,

            C.EXPIRYDATETIME,

            C.DELIVERYDATE,

            PT.DESCRIPTION AS PAYMENT_TERM,

            PM.NAME AS PAYMENT_MODE,

            DM.TXT AS DELIVERY_MODE,

            DT.TXT AS DELIVERY_TERM

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

        WHERE

            CAST(
                DATEADD(
                    MINUTE,
                    330,
                    C.EXPIRYDATETIME
                ) AS DATE
            )

            <

            CAST(
                GETDATE()
                AS DATE
            )

        AND EXISTS (

            SELECT 1

            FROM {SCHEMA}.D365_PURCHRFQCASELINE CL WITH (NOLOCK)

            INNER JOIN {SCHEMA}.D365_PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
                ON AVL.ITEMID = CL.ITEMID
                AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT

                AND AVL.VALIDFROM <= GETUTCDATE()

                AND AVL.VALIDTO >= GETUTCDATE()

            WHERE CL.RFQCASEID = C.RFQCASEID
        )

        ORDER BY
            C.EXPIRYDATETIME DESC
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            d365_query,
            vendor_account
        )

        columns = [
            c[0]
            for c in cursor.description
        ]

        rows = cursor.fetchall()

    # ========================================================
    # STEP 3
    # FILTER + STATUS LOGIC
    # ========================================================
    result = []

    for row in rows:

        data = dict(zip(columns, row))

        rfq_caseid = data["RFQCASEID"]

        vend_account = data["VENDACCOUNT"]

        # ====================================================
        # LATEST REPLY
        # ====================================================
        latest_reply = reply_map.get(
            (rfq_caseid, vend_account)
        )

        # ====================================================
        # STATUS
        # ====================================================
        if not latest_reply:

            status = "Not Opened"

            include_record = True

        elif latest_reply["SUBMISSIONSTATUS"] == STATUS_DRAFT_ONLY:

            status = "Drafted"

            include_record = True

        elif (

            latest_reply["SUBMISSIONSTATUS"] == 1

            and

            (
                latest_reply["DRAFTLINECOUNT"] or 0
            ) > 0
        ):

            status = "Drafted"

            include_record = True

        else:

            include_record = False
        # if not latest_reply:

        #     status = "Not Opened"

        #     include_record = True

        # elif (

        #     latest_reply["SUBMISSIONSTATUS"] == 1

        #     and

        #     (
        #         latest_reply["DRAFTLINECOUNT"] or 0
        #     ) > 0
        # ):

        #     status = "Drafted"

        #     include_record = True

        # else:

        #     include_record = False

        # ====================================================
        # SKIP
        # ====================================================
        if not include_record:
            continue

        # ====================================================
        # FINAL RESPONSE
        # ====================================================
        result.append({

            "rfq_caseid":
                data["RFQCASEID"],

            "rfq_id":
                data["RFQID"],

            "expiry_date":
                format_utc_iso(
                    data["EXPIRYDATETIME"]
                ),

            "delivery_date":
                format_utc_iso(
                    data["DELIVERYDATE"]
                ),

            "payment_term":
                data["PAYMENT_TERM"],

            "payment_mode":
                data["PAYMENT_MODE"],

            "delivery_mode":
                data["DELIVERY_MODE"],

            "delivery_term":
                data["DELIVERY_TERM"],

            "status":
                status
        })

    return result


# from app.db.base import (
#     get_connection,
#     get_connection
# )

# from app.utils.date_utils import (
#     format_utc_iso
# )
# from app.core.config import settings

# SCHEMA = settings.DB_SCHEMA

# RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"

# def fetch_vendor_expired_rfqs(
#     vendor_account: str
# ):

#     # ============================================================
#     # STEP 1
#     # FETCH LATEST REPLIES FROM VENDOR DB
#     # ============================================================
#     reply_query = f"""
#         SELECT
#             RFQCASEID,
#             RFQID,
#             VENDORACCOUNT,
#             SUBMISSIONSTATUS,
#             DRAFTLINECOUNT,
#             ID

#         FROM (
#             SELECT *,
#                 ROW_NUMBER() OVER (
#                     PARTITION BY RFQCASEID, VENDORACCOUNT
#                     ORDER BY ID DESC
#                 ) AS RN

#             FROM {RFQ_REPLIES_TABLE}  WITH (NOLOCK)

#             WHERE VENDORACCOUNT = ?
#         ) X

#         WHERE RN = 1
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
#     # REPLY MAP
#     # COMPOSITE KEY
#     # ============================================================
#     reply_map = {
#         (
#             r["RFQCASEID"],
#             r["VENDORACCOUNT"]
#         ): r

#         for r in reply_data
#     }


#     # ============================================================
#     # STEP 2
#     # FETCH EXPIRED RFQS FROM D365 DB
#     # ============================================================
#     d365_query = """
#         SELECT
#             L.RFQCASEID,

#             T.RFQID,

#             T.VENDACCOUNT,

#             L.NAME AS RFQNAME,

#             L.EXPIRYDATETIME,

#             L.DELIVERYDATE,

#             PT.DESCRIPTION AS PAYMENT_TERM,

#             PM.NAME AS PAYMENT_MODE,

#             DM.TXT AS DELIVERY_MODE,

#             DT.TXT AS DELIVERY_TERM

#         FROM PurchRFQCaseTable L WITH (NOLOCK)

#         INNER JOIN PurchRFQTable T WITH (NOLOCK)
#             ON T.RFQCASEID = L.RFQCASEID
#             AND T.VENDACCOUNT = ?

#         LEFT JOIN PAYMTERM PT WITH (NOLOCK)
#             ON L.PAYMENT = PT.PAYMTERMID

#         LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
#             ON L.PAYMMODE = PM.PAYMMODE

#         LEFT JOIN DLVMODE DM WITH (NOLOCK)
#             ON L.DLVMODE = DM.CODE

#         LEFT JOIN DLVTERM DT WITH (NOLOCK)
#             ON L.DLVTERM = DT.CODE

#         WHERE
#             CAST(
#                 DATEADD(MINUTE,330,L.EXPIRYDATETIME)
#                 AS DATE
#             )
#             <
#             CAST(GETDATE() AS DATE)

#         AND EXISTS (
#             SELECT 1

#             FROM PurchRFQCaseLine CL WITH (NOLOCK)

#             INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                 ON AVL.ITEMID = CL.ITEMID
#                 AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                 AND AVL.DATAAREAID = L.DATAAREAID

#             WHERE CL.RFQCASEID = L.RFQCASEID
#         )

#         ORDER BY L.EXPIRYDATETIME DESC
#     """


#     with get_connection() as conn:

#         cursor = conn.cursor()

#         cursor.execute(
#             d365_query,
#             vendor_account
#         )

#         columns = [
#             c[0]
#             for c in cursor.description
#         ]

#         rows = cursor.fetchall()


#     # ============================================================
#     # STEP 3
#     # PYTHON FILTERING + STATUS LOGIC
#     # ============================================================
#     result = []


#     for row in rows:

#         data = dict(zip(columns, row))

#         rfq_caseid = data["RFQCASEID"]

#         vend_account = data["VENDACCOUNT"]


#         # ========================================================
#         # GET LATEST REPLY
#         # ========================================================
#         latest_reply = reply_map.get(
#             (rfq_caseid, vend_account)
#         )


#         # ========================================================
#         # STATUS LOGIC
#         # ========================================================
#         if not latest_reply:

#             status = "Not Opened"

#             include_record = True


#         elif (
#             latest_reply["SUBMISSIONSTATUS"] == 1
#             and
#             (latest_reply["DRAFTLINECOUNT"] or 0) > 0
#         ):

#             status = "Drafted"

#             include_record = True


#         else:

#             include_record = False


#         # ========================================================
#         # SKIP RECORD
#         # ========================================================
#         if not include_record:
#             continue


#         # ========================================================
#         # FINAL RESPONSE
#         # ========================================================
#         result.append({

#             "rfq_caseid":
#                 data["RFQCASEID"],

#             "rfq_id":
#                 data["RFQID"],

#             "expiry_date":
#                 format_utc_iso(
#                     data["EXPIRYDATETIME"]
#                 ),

#             "delivery_date":
#                 format_utc_iso(
#                     data["DELIVERYDATE"]
#                 ),

#             "payment_term":
#                 data["PAYMENT_TERM"],

#             "payment_mode":
#                 data["PAYMENT_MODE"],

#             "delivery_mode":
#                 data["DELIVERY_MODE"],

#             "delivery_term":
#                 data["DELIVERY_TERM"],

#             "status":
#                 status
#         })


#     return result


# # from app.db.base import get_connection 
# # from app.utils.date_utils import format_utc_iso,format_date
# # from app.utils.remainingdate import calculate_days_left,format_expiry_label

# # def fetch_vendor_expired_rfqs(vendor_account: str):
# #     query="""
# #             SELECT
# #     L.RFQCASEID,
# #     T.RFQID,
# #     L.NAME          AS RFQNAME,
# #     L.EXPIRYDATETIME,
# #     L.DELIVERYDATE,
# #     PT.DESCRIPTION  AS PAYMENT_TERM,
# #     PM.NAME         AS PAYMENT_MODE,
# #     DM.TXT          AS DELIVERY_MODE,
# #     DT.TXT          AS DELIVERY_TERM,

# #     CASE 
# #         WHEN NOT EXISTS (
# #             SELECT 1
# #             FROM HIQ_VendorRFQReplies R
# #             WHERE R.RFQ_CASE_ID = L.RFQCASEID
# #               AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
# #         ) THEN 'Not Opened'

# #         --  CHANGED HERE (STATUS LOGIC)
# #         WHEN EXISTS (
# #             SELECT 1
# #             FROM HIQ_VendorRFQReplies R
# #             WHERE R.ID = (
# #                 SELECT MAX(R2.ID)
# #                 FROM HIQ_VendorRFQReplies R2
# #                 WHERE R2.RFQ_CASE_ID = L.RFQCASEID
# #                   AND R2.VENDOR_ACCOUNT = T.VENDACCOUNT
# #             )
# #             AND R.SUBMISSION_STATUS IN (1)
# #             AND R.DRAFTLINECOUNT > 0
# #         ) THEN 'Drafted'

# #         ELSE 'Not Opened'
# #     END AS STATUS

# # FROM PurchRFQCaseTable L WITH (NOLOCK)

# # INNER JOIN PurchRFQTable T WITH (NOLOCK)
# #     ON  T.RFQCASEID   = L.RFQCASEID
# #     AND T.VENDACCOUNT = ?             

# # LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# #     ON L.PAYMENT = PT.PAYMTERMID

# # LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# #     ON L.PAYMMODE = PM.PAYMMODE

# # LEFT JOIN DLVMODE DM WITH (NOLOCK)
# #     ON L.DLVMODE = DM.CODE

# # LEFT JOIN DLVTERM DT WITH (NOLOCK)
# #     ON L.DLVTERM = DT.CODE

# # WHERE  CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) 
# #     < CAST(GETDATE() AS DATE)
# # --L.EXPIRYDATETIME < GETUTCDATE()

# # AND (
# #     -- Vendor NEVER submitted a reply
# #     NOT EXISTS (
# #         SELECT 1
# #         FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
# #         WHERE R.RFQ_CASE_ID    = L.RFQCASEID
# #           AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
# #     )

# #     OR

# #     -- CHANGED HERE (WHERE LOGIC)
# #     EXISTS (
# #         SELECT 1
# #         FROM HIQ_VendorRFQReplies R
# #         WHERE R.ID = (
# #             SELECT MAX(R2.ID)
# #             FROM HIQ_VendorRFQReplies R2
# #             WHERE R2.RFQ_CASE_ID = L.RFQCASEID
# #               AND R2.VENDOR_ACCOUNT = T.VENDACCOUNT
# #         )
# #         AND R.SUBMISSION_STATUS  = 1
# #         AND R.DRAFTLINECOUNT     > 0   
# #     )
# # )

# # -- Now applies to BOTH branches above
# # AND EXISTS (
# #     SELECT 1
# #     FROM PurchRFQCaseLine CL WITH (NOLOCK)
# #     INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
# #         ON  AVL.ITEMID            = CL.ITEMID
# #         AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
# #         AND AVL.DATAAREAID        = L.DATAAREAID
# #     WHERE CL.RFQCASEID = L.RFQCASEID
# # )

# # ORDER BY L.EXPIRYDATETIME DESC
# # """
# # #     query = """
# # #         SELECT
# # #             L.RFQCASEID,
# # #             T.RFQID,
# # #             L.NAME          AS RFQNAME,
# # #             L.EXPIRYDATETIME,
# # #             L.DELIVERYDATE,
# # #             PT.DESCRIPTION  AS PAYMENT_TERM,
# # #             PM.NAME         AS PAYMENT_MODE,
# # #             DM.TXT          AS DELIVERY_MODE,
# # #             DT.TXT          AS DELIVERY_TERM,
# # #             CASE 
# # #         WHEN NOT EXISTS (
# # #             SELECT 1
# # #             FROM HIQ_VendorRFQReplies R
# # #             WHERE R.RFQ_CASE_ID = L.RFQCASEID
# # #               AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
# # #         ) THEN 'Not Opened'

# # #         WHEN EXISTS (
# # #             SELECT 1
# # #             FROM HIQ_VendorRFQReplies R
# # #             WHERE R.RFQ_CASE_ID = L.RFQCASEID
# # #               AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
# # #               AND R.SUBMISSION_STATUS IN (1)
# # #               AND R.DRAFTLINECOUNT > 0
# # #         ) THEN 'Drafted'
# # #            ELSE 'Not Opened'
# # #         END AS STATUS

# # #         FROM PurchRFQCaseTable L WITH (NOLOCK)

# # #         INNER JOIN PurchRFQTable T WITH (NOLOCK)
# # #             ON  T.RFQCASEID   = L.RFQCASEID
# # #             AND T.VENDACCOUNT = ?             

# # #         LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# # #             ON L.PAYMENT = PT.PAYMTERMID

# # #         LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# # #             ON L.PAYMMODE = PM.PAYMMODE

# # #         LEFT JOIN DLVMODE DM WITH (NOLOCK)
# # #             ON L.DLVMODE = DM.CODE

# # #         LEFT JOIN DLVTERM DT WITH (NOLOCK)
# # #             ON L.DLVTERM = DT.CODE
# # #         WHERE L.EXPIRYDATETIME < GETUTCDATE()

# # #     AND (
# # #         -- Vendor NEVER submitted a reply
# # #         NOT EXISTS (
# # #             SELECT 1
# # #             FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
# # #             WHERE R.RFQ_CASE_ID    = L.RFQCASEID
# # #               AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
# # #         )
# # #         OR
# # #         -- PARTIAL SUBMISSION (IMPORTANT)
# # #         EXISTS (
# # #             SELECT 1
# # #             FROM HIQ_VendorRFQReplies R
# # #             WHERE R.RFQ_CASE_ID        = L.RFQCASEID
# # #               AND R.VENDOR_ACCOUNT     = T.VENDACCOUNT
# # #               AND R.SUBMISSION_STATUS  = 1
# # #               AND R.DRAFTLINECOUNT     > 0   
# # #         )
# # #     )

# # #     -- ✅ Now applies to BOTH branches above
# # #     AND EXISTS (
# # #         SELECT 1
# # #         FROM PurchRFQCaseLine CL WITH (NOLOCK)
# # #         INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
# # #             ON  AVL.ITEMID            = CL.ITEMID
# # #             AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
# # #             AND AVL.DATAAREAID        = L.DATAAREAID
# # #         WHERE CL.RFQCASEID = L.RFQCASEID
# # #     )

# # # ORDER BY L.EXPIRYDATETIME DESC

# # #     """
# #     with get_connection() as conn:
# #         cursor = conn.cursor()
# #         cursor.execute(query, vendor_account)

# #         columns = [c[0] for c in cursor.description]
# #         rows    = cursor.fetchall()
# #         result  = []

# #         for row in rows:
# #             data = dict(zip(columns, row))
# #             result.append({
# #                 "rfq_caseid":    data["RFQCASEID"],
# #                 "rfq_id":        data["RFQID"],
# #                 "expiry_date":   format_utc_iso(data["EXPIRYDATETIME"]),
# #                 "delivery_date": format_utc_iso(data["DELIVERYDATE"]),
# #                 "payment_term":  data["PAYMENT_TERM"],
# #                 "payment_mode":  data["PAYMENT_MODE"],
# #                 "delivery_mode": data["DELIVERY_MODE"],
# #                 "delivery_term": data["DELIVERY_TERM"],
# #                 "status":data["STATUS"]
# #             })

# #         return result 
