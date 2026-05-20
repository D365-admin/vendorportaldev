from app.db.base import get_connection, get_d365_connection
from app.utils.date_utils import format_utc_iso
from app.utils.remainingdate import calculate_days_left
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"

def fetch_vendor_rfqs(vendor_account: str):

    # ─────────────────────────────────────────────
    # STEP 1 → Fetch replied RFQ IDs from Portal DB
    # ─────────────────────────────────────────────
    replied_rfqs = set()

    reply_query = f"""
        SELECT RFQID
        FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)
        WHERE VENDORACCOUNT = ?
    """

    with get_connection() as conn:

        cursor = conn.cursor()
        cursor.execute(reply_query, vendor_account)

        rows = cursor.fetchall()

        replied_rfqs = {row[0] for row in rows}


    # ─────────────────────────────────────────────
    # STEP 2 → Fetch RFQs from D365 DB
    # ─────────────────────────────────────────────
    d365_query = """
        SELECT
            L.RFQCASEID,
            T.RFQID,
            L.NAME AS RFQNAME,
            L.EXPIRYDATETIME,
            L.DELIVERYDATE,

            PT.DESCRIPTION AS PAYMENT_TERM,
            PM.NAME AS PAYMENT_MODE,
            DM.TXT AS DELIVERY_MODE,
            DT.TXT AS DELIVERY_TERM

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

        WHERE
            CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE)
            >=
            CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)

            AND EXISTS (
                SELECT 1
                FROM PurchRFQCaseLine CL WITH (NOLOCK)

                INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
                    ON TRIM(AVL.ITEMID) = TRIM(CL.ITEMID)
                    AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
                    AND AVL.VALIDFROM <= GETUTCDATE()
                    AND AVL.VALIDTO >= GETUTCDATE()

                WHERE CL.RFQCASEID = L.RFQCASEID
            )

        ORDER BY L.EXPIRYDATETIME
    """


    with get_d365_connection() as conn:

        cursor = conn.cursor()
        cursor.execute(d365_query, vendor_account)

        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchall()

        result = []

        for row in rows:

            data = dict(zip(columns, row))

            # ─────────────────────────────────────
            # STEP 3 → Python-side filtering
            # ─────────────────────────────────────
            if data["RFQID"] in replied_rfqs:
                continue

            result.append({
                "rfq_caseid": data["RFQCASEID"],
                "rfq_id": data["RFQID"],

                "expiry_date":
                    format_utc_iso(data["EXPIRYDATETIME"]),

                "delivery_date":
                    format_utc_iso(data["DELIVERYDATE"]),

                "payment_term":
                    data["PAYMENT_TERM"] or "-",

                "payment_mode":
                    data["PAYMENT_MODE"] or "-",

                "delivery_mode":
                    data["DELIVERY_MODE"] or "-",

                "delivery_term":
                    data["DELIVERY_TERM"] or "-",

                "dates_left":
                    calculate_days_left(data["EXPIRYDATETIME"])
            })

        return result

# from app.db.base import get_connection
# from app.utils.date_utils import format_date,format_utc_iso
# from app.utils.remainingdate import calculate_days_left, format_expiry_label


# def fetch_vendor_rfqs(vendor_account: str):

#     query = """
#         SELECT
#             L.RFQCASEID,
#             T.RFQID,
#             L.NAME              AS RFQNAME,
#             L.EXPIRYDATETIME,
        
 
#             L.DELIVERYDATE,
#             PT.DESCRIPTION      AS PAYMENT_TERM,
#             PM.NAME             AS PAYMENT_MODE,
#             DM.TXT              AS DELIVERY_MODE,
#             DT.TXT              AS DELIVERY_TERM

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

#         --WHERE L.EXPIRYDATETIME >= GETUTCDATE()
#         WHERE CAST(DATEADD(MINUTE,330,L.EXPIRYDATETIME) AS DATE) >= CAST(DATEADD(MINUTE,330,GETUTCDATE()) AS DATE)
#         --WHERE CAST(L.EXPIRYDATETIME AS DATE) >= CAST(GETDATE() AS DATE)   
#             -- ONLY show RFQs where vendor is approved for at least one item
#             AND EXISTS (
#                 SELECT 1
#                 FROM PurchRFQCaseLine CL WITH (NOLOCK)
#                 INNER JOIN PDSAPPROVEDVENDORLIST AVL WITH (NOLOCK)
#                     ON  TRIM(AVL.ITEMID)      = TRIM(CL.ITEMID) 
#                    -- ON  AVL.ITEMID            = CL.ITEMID
#                     AND AVL.PDSAPPROVEDVENDOR = T.VENDACCOUNT
#                     AND AVL.VALIDFROM        <= GETUTCDATE()
#                     AND AVL.VALIDTO          >= GETUTCDATE()
#                 WHERE CL.RFQCASEID = L.RFQCASEID
#             )

#             -- EXCLUDE RFQs already replied
#             AND NOT EXISTS (
#                 SELECT 1
#                 FROM HIQ_VendorRFQReplies R WITH (NOLOCK)
#                 WHERE R.RFQ_ID        = T.RFQID
#                   AND R.VENDOR_ACCOUNT = T.VENDACCOUNT
#             )

#         ORDER BY L.EXPIRYDATETIME
#     """

#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute(query, vendor_account)

#         columns = [c[0] for c in cursor.description]
#         rows    = cursor.fetchall()
#         result  = []

#         for row in rows:
#             data = dict(zip(columns, row))
#             result.append({
#                 "rfq_caseid":    data["RFQCASEID"],
#                 "rfq_id":        data["RFQID"],
#                 "expiry_date":   format_utc_iso(data["EXPIRYDATETIME"]),
#                 "delivery_date": format_utc_iso(data["DELIVERYDATE"]),
#                 "payment_term":  data["PAYMENT_TERM"]  or "-",
#                 "payment_mode":  data["PAYMENT_MODE"]  or "-",
#                 "delivery_mode": data["DELIVERY_MODE"] or "-",
#                 "delivery_term": data["DELIVERY_TERM"] or "-",
#                 "dates_left":    calculate_days_left(data["EXPIRYDATETIME"])
#             })

#         return result