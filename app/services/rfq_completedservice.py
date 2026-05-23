from app.db.base import (
    get_connection
)

from app.utils.date_utils import (
    format_utc_iso
)

from typing import (
    List,
    Dict,
    Any
)

from app.core.config import settings


SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"


# ============================================================
# PL.STATUS MEANING
# 0,1,2 = Under Review
# 3 = Rejected
# 4 = Accepted
# 5 = Canceled
# 6 = Declined
# ============================================================


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

                FROM D365_PDSAPPROVEDVENDORLIST
                WITH (NOLOCK)

                WHERE PDSAPPROVEDVENDOR = ?
            """, (vendor_account,))

            return [

                str(r[0]).strip().upper()

                for r in cur.fetchall()

                if r[0]
            ]

    except Exception as e:

        print(
            f"[APPROVED VENDOR ERROR]: {e}"
        )

        return []


# ============================================================
# COMPLETED RFQ LIST
# ============================================================
def fetch_completed_rfqs(
    vendor_account: str
) -> List[Dict[str, Any]]:

    approved_items = _get_approved_items(
        vendor_account
    )

    if not approved_items:
        return []

    # ========================================================
    # STEP 1
    # FETCH SUBMITTED RFQS
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT

                RFQCASEID,
                RFQID,
                VENDORACCOUNT,

                MAX(SENDTOD365AT)
                    AS SUBMITTED_ON

            FROM {RFQ_REPLIES_TABLE}
            WITH (NOLOCK)

            WHERE VENDORACCOUNT = ?
              AND SUBMISSIONSTATUS = 1

            GROUP BY
                RFQCASEID,
                RFQID,
                VENDORACCOUNT

            ORDER BY
                MAX(SENDTOD365AT) DESC
        """, (vendor_account,))

        rows = cur.fetchall()

        if not rows:
            return []

        cols = [
            c[0]
            for c in cur.description
        ]

        portal_rfqs = [
            dict(zip(cols, r))
            for r in rows
        ]

    rfq_ids = [
        r["RFQID"]
        for r in portal_rfqs
        if r["RFQID"]
    ]

    if not rfq_ids:
        return []

    placeholders = ",".join(
        ["?"] * len(rfq_ids)
    )

    portal_map = {

        (
            r["RFQID"],
            r["VENDORACCOUNT"]
        ): r

        for r in portal_rfqs
    }

    # ========================================================
    # STEP 2
    # FETCH COMPLETED RFQS
    # ========================================================
    d365_query = f"""
        SELECT

            T.RFQID,

            T.VENDACCOUNT,

            T.RFQCASEID,

            C.DELIVERYDATE
                AS EXPECTED_DELIVERY_DATE,

            (
                SELECT TOP 1
                    CURRENCYCODE

                FROM D365_PURCHRFQREPLYTABLE
                WITH (NOLOCK)

                WHERE RFQID = T.RFQID
            ) AS CURRENCY,

            PM.NAME AS PAYMENT_MODE,

            PT.DESCRIPTION
                AS PAYMENT_TERM,

            DM.TXT
                AS DELIVERY_MODE,

            DT.TXT
                AS DELIVERY_TERM

        FROM D365_PURCHRFQTABLE T
        WITH (NOLOCK)

        LEFT JOIN D365_PURCHRFQCASETABLE C
        WITH (NOLOCK)
            ON C.RFQCASEID = T.RFQCASEID

        LEFT JOIN D365_PAYMMODETABLE PM
        WITH (NOLOCK)
            ON C.PAYMMODE = PM.PAYMMODE

        LEFT JOIN D365_PAYMTERM PT
        WITH (NOLOCK)
            ON C.PAYMENT = PT.PAYMTERMID

        LEFT JOIN D365_DLVMODE DM
        WITH (NOLOCK)
            ON C.DLVMODE = DM.CODE

        LEFT JOIN D365_DLVTERM DT
        WITH (NOLOCK)
            ON C.DLVTERM = DT.CODE

        WHERE T.VENDACCOUNT = ?
          AND T.RFQID IN ({placeholders})

          AND EXISTS (

              SELECT 1

              FROM D365_PURCHRFQREPLYLINE RL2
              WITH (NOLOCK)

              INNER JOIN D365_PURCHRFQLINE PL
              WITH (NOLOCK)
                  ON PL.RECID = RL2.RFQLINERECID

              WHERE RL2.RFQID = T.RFQID
                AND PL.STATUS >= 3
          )
    """

    result = []

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(
            d365_query,
            [vendor_account] + rfq_ids
        )

        d365_rows = cur.fetchall()

        if not d365_rows:
            return []

        d365_cols = [
            c[0]
            for c in cur.description
        ]

        d365_data = [
            dict(zip(d365_cols, r))
            for r in d365_rows
        ]

        for data in d365_data:

            rfq_id = data["RFQID"]

            vend_account = data["VENDACCOUNT"]

            portal_row = portal_map.get(
                (rfq_id, vend_account)
            )

            if not portal_row:
                continue

            # =================================================
            # QUOTED AMOUNT
            # =================================================
            cur.execute("""
                SELECT

                    ISNULL(
                        SUM(RL.LINEAMOUNT),
                        0
                    )

                FROM D365_PURCHRFQREPLYLINE RL
                WITH (NOLOCK)

                INNER JOIN D365_PURCHRFQLINE PL
                WITH (NOLOCK)
                    ON PL.RECID = RL.RFQLINERECID

                WHERE RL.RFQID = ?
                  AND PL.STATUS >= 3
            """, (rfq_id,))

            quoted_amount = float(
                cur.fetchone()[0] or 0
            )

            result.append({

                "rfq_id":
                    rfq_id,

                "rfq_case_id":
                    portal_row["RFQCASEID"],

                "submitted_on_date":
                    format_utc_iso(
                        portal_row[
                            "SUBMITTED_ON"
                        ]
                    ),

                "quoted_amount":
                    quoted_amount,

                "currency":
                    data["CURRENCY"] or "INR",

                "payment_mode":
                    data["PAYMENT_MODE"] or "-",

                "payment_term":
                    data["PAYMENT_TERM"] or "-",

                "delivery_mode":
                    data["DELIVERY_MODE"] or "-",

                "delivery_term":
                    data["DELIVERY_TERM"] or "-",

                "delivery_date":
                    format_utc_iso(
                        data[
                            "EXPECTED_DELIVERY_DATE"
                        ]
                    )
            })

    return result


# ============================================================
# COMPLETED RFQ DETAIL
# ============================================================
def fetch_completed_rfq_detail(
    rfq_id: str,
    vendor_account: str
) -> Dict[str, Any]:

    approved_items = _get_approved_items(
        vendor_account
    )

    if not approved_items:

        return {
            "success": False,
            "message":
                "No approved items found"
        }

    # ========================================================
    # VALIDATE RFQ
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(f"""
            SELECT TOP 1

                RFQID,
                RFQCASEID,
                VENDORACCOUNT

            FROM {RFQ_REPLIES_TABLE}
            WITH (NOLOCK)

            WHERE UPPER(RFQID)
                    = UPPER(?)

              AND UPPER(VENDORACCOUNT)
                    = UPPER(?)

              AND SUBMISSIONSTATUS = 1
        """, (rfq_id, vendor_account))

        row = cur.fetchone()

        if not row:

            return {
                "success": False,
                "message": "RFQ not found"
            }

        rfq_id = str(row[0]).strip()

        rfq_case_id = row[1]

    # ========================================================
    # HEADER
    # ========================================================
    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute("""
            SELECT TOP 1

                RT.RFQID,

                RT.CURRENCYCODE,

                RT.DELIVERYDATE
                    AS REPLY_DELIVERY_DATE,

                RT.DLVMODE
                    AS REPLY_DELIVERY_MODE,

                RT.DLVTERM
                    AS REPLY_DELIVERY_TERM,

                RT.PAYMENT
                    AS REPLY_PAYMENT_TERM,

                RT.VENDREF,

                RT.TOTALSCORE,

                RT.RANK,

                RT.VALIDFROM,

                RT.VALIDTO,

                RT.VALIDITYDATESTART,

                RT.VALIDITYDATEEND,

                RT.REPLYPROGRESSSTATUS,

                RT.HIQ_COMMENTS
                    AS REMARKS,

                T.RFQCASEID
                    AS RFQ_CASE_ID,

                C.EXPIRYDATETIME
                    AS CLOSING_DATE,

                C.CREATEDDATETIME
                    AS ISSUE_DATE,

                C.DELIVERYDATE
                    AS EXPECTED_DELIVERY_DATE,

                C.NAME
                    AS DOCUMENT_TITLE,

                PM.NAME
                    AS PAYMENT_MODE,

                PT.DESCRIPTION
                    AS PAYMENT_TERM,

                DM.TXT
                    AS DELIVERY_MODE,

                DT.TXT
                    AS DELIVERY_TERM,

                T.HIQ_TERMSANDCONDITIONS

            FROM D365_PURCHRFQREPLYTABLE RT
            WITH (NOLOCK)

            INNER JOIN D365_PURCHRFQTABLE T
            WITH (NOLOCK)
                ON T.RFQID = RT.RFQID
               AND T.VENDACCOUNT = ?

            LEFT JOIN D365_PURCHRFQCASETABLE C
            WITH (NOLOCK)
                ON C.RFQCASEID = T.RFQCASEID

            LEFT JOIN D365_PAYMMODETABLE PM
            WITH (NOLOCK)
                ON C.PAYMMODE = PM.PAYMMODE

            LEFT JOIN D365_PAYMTERM PT
            WITH (NOLOCK)
                ON C.PAYMENT = PT.PAYMTERMID

            LEFT JOIN D365_DLVMODE DM
            WITH (NOLOCK)
                ON C.DLVMODE = DM.CODE

            LEFT JOIN D365_DLVTERM DT
            WITH (NOLOCK)
                ON C.DLVTERM = DT.CODE

            WHERE RT.RFQID = ?
        """, (vendor_account, rfq_id))

        row = cur.fetchone()

        if not row:

            return {
                "success": False,
                "message": "RFQ not found"
            }

        cols = [
            c[0]
            for c in cur.description
        ]

        header = dict(zip(cols, row))

        # ====================================================
        # LINES
        # ====================================================
        cur.execute("""
            SELECT

                RL.LINENUM,

                RL.NAME
                    AS ITEM_NAME,

                RL.PURCHQTY
                    AS QUANTITY,

                RL.PURCHUNIT
                    AS UOM,

                RL.PURCHPRICE
                    AS UNIT_PRICE,

                RL.LINEAMOUNT
                    AS NET_AMOUNT,

                RL.LINEDISC
                    AS LINE_DISC,

                RL.LINEPERCENT
                    AS LINE_PERCENT,

                RL.DELIVERYDATE
                    AS DELIVERY_DATE,

                RL.HIQ_COMMENTS
                    AS VENDOR_COMMENTS,

                RL.VALIDFROM
                    AS LINE_VALID_FROM,

                RL.VALIDTO
                    AS LINE_VALID_TO,

                RL.EXTERNALITEMID,

                PL.HIQ_TARGETPRICE
                    AS TARGETPRICE,

                PL.HIQ_COMMENTS
                    AS COMMENTS,

                PL.ITEMID,

                PL.STATUS,

                PL.CURRENCYCODE,

                PL.PURCHID,

                PL.DELIVERYDATE
                    AS LINE_DELIVERY_DATE,

                RL.DELIVERYDATE
                    AS VENDORREPLY_DELIVERY_DATE,

                CASE PL.STATUS

                    WHEN 3
                        THEN 'Rejected'

                    WHEN 4
                        THEN 'Accepted'

                    WHEN 5
                        THEN 'Canceled'

                    WHEN 6
                        THEN 'Declined'

                    ELSE 'Under Review'

                END AS HIQ_DECISION

            FROM D365_PURCHRFQREPLYLINE RL
            WITH (NOLOCK)

            INNER JOIN D365_PURCHRFQLINE PL
            WITH (NOLOCK)
                ON PL.RECID = RL.RFQLINERECID

            WHERE RL.RFQID = ?
              AND PL.STATUS >= 3

            ORDER BY RL.LINENUM
        """, (rfq_id,))

        line_rows = cur.fetchall()

        line_cols = [
            c[0]
            for c in cur.description
        ]

        lines = [
            dict(zip(line_cols, r))
            for r in line_rows
        ]

    # ========================================================
    # FINAL RESPONSE
    # ========================================================
    return {

        "success": True,

        "data": {

            "rfq_id":
                rfq_id,

            "rfq_case_id":
                rfq_case_id
                or header["RFQ_CASE_ID"],

            "delivery_date":
                format_utc_iso(
                    header[
                        "EXPECTED_DELIVERY_DATE"
                    ]
                ),

            "payment_term":
                header["PAYMENT_TERM"] or "-",

            "delivery_term":
                header["DELIVERY_TERM"] or "-",

            "delivery_mode":
                header["DELIVERY_MODE"] or "-",

            "payment_mode":
                header["PAYMENT_MODE"] or "-",

            "issue_date":
                format_utc_iso(
                    header["ISSUE_DATE"]
                ),

            "closing_date":
                format_utc_iso(
                    header["CLOSING_DATE"]
                ),

            "document_title":
                header["DOCUMENT_TITLE"],

            "currency":
                header["CURRENCYCODE"] or "INR",

            "reply_delivery_date":
                format_utc_iso(
                    header[
                        "REPLY_DELIVERY_DATE"
                    ]
                ),

            "reply_delivery_mode":
                header[
                    "REPLY_DELIVERY_MODE"
                ] or "-",

            "reply_delivery_term":
                header[
                    "REPLY_DELIVERY_TERM"
                ] or "-",

            "reply_payment_term":
                header[
                    "REPLY_PAYMENT_TERM"
                ] or "-",

            "vendor_ref":
                header["VENDREF"] or "-",

            "valid_from":
                format_utc_iso(
                    header["VALIDFROM"]
                ),

            "valid_to":
                format_utc_iso(
                    header["VALIDTO"]
                ),

            "validity_date_start":
                format_utc_iso(
                    header[
                        "VALIDITYDATESTART"
                    ]
                ),

            "validity_date_end":
                format_utc_iso(
                    header[
                        "VALIDITYDATEEND"
                    ]
                ),

            "total_score":
                header["TOTALSCORE"] or 0,

            "rank":
                header["RANK"] or 0,

            "reply_progress_status":
                header[
                    "REPLYPROGRESSSTATUS"
                ] or 0,

            "remarks":
                header["REMARKS"] or "",

            "termsandconditions":
                header[
                    "HIQ_TERMSANDCONDITIONS"
                ],

            "line_items": [

                {

                    "line_num":
                        int(
                            float(
                                line["LINENUM"]
                            )
                        ),

                    "item_id":
                        line["ITEMID"] or "-",

                    "item_name":
                        line["ITEM_NAME"] or "-",

                    "external_item_id":
                        line[
                            "EXTERNALITEMID"
                        ] or "-",

                    "quantity":
                        float(
                            line["QUANTITY"] or 0
                        ),

                    "uom":
                        line["UOM"] or "-",

                    "unit_price":
                        float(
                            line[
                                "UNIT_PRICE"
                            ] or 0
                        ),

                    "net_amount":
                        float(
                            line[
                                "NET_AMOUNT"
                            ] or 0
                        ),

                    "line_disc":
                        float(
                            line[
                                "LINE_DISC"
                            ] or 0
                        ),

                    "line_percent":
                        float(
                            line[
                                "LINE_PERCENT"
                            ] or 0
                        ),

                    "delivery_date":
                        format_utc_iso(
                            line[
                                "DELIVERY_DATE"
                            ]
                        ),

                    "vendor_comments":
                        line[
                            "VENDOR_COMMENTS"
                        ] or " ",

                    "currency":
                        line[
                            "CURRENCYCODE"
                        ] or "INR",

                    "line_valid_from":
                        format_utc_iso(
                            line[
                                "LINE_VALID_FROM"
                            ]
                        ),

                    "line_valid_to":
                        format_utc_iso(
                            line[
                                "LINE_VALID_TO"
                            ]
                        ),

                    "hiq_decision":
                        line[
                            "HIQ_DECISION"
                        ],

                    "target_price":
                        round(
                            float(
                                line[
                                    "TARGETPRICE"
                                ] or 0
                            ),
                            2
                        ),

                    "comments":
                        line["COMMENTS"] or " ",

                    "purchid":
                        line["PURCHID"],

                    "rfq_delivery_date":
                        format_utc_iso(
                            line.get(
                                "LINE_DELIVERY_DATE"
                            )
                        ),

                    "vendor_delivery_date":
                        format_utc_iso(
                            line.get(
                                "VENDORREPLY_DELIVERY_DATE"
                            )
                        )
                }

                for line in lines
            ]
        }
    }

# from app.db.base import get_connection, get_connection
# from app.utils.date_utils import format_utc_iso
# from typing import List, Dict, Any
# from app.core.config import settings

# SCHEMA = settings.DB_SCHEMA

# RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VendorRFQReplies"

# # ============================================================
# # PL.STATUS MEANING:
# # 0,1,2 = Under Review
# # 3 = Rejected
# # 4 = Accepted
# # 5 = Canceled
# # 6 = Declined
# # ============================================================


# def _get_approved_items(vendor_account: str) -> List[str]:
#     try:
#         with get_connection() as conn:
#             cur = conn.cursor()
#             cur.execute("""
#                 SELECT UPPER(LTRIM(RTRIM(ITEMID))) AS ITEMID
#                 FROM PDSAPPROVEDVENDORLIST WITH (NOLOCK)
#                 WHERE PDSAPPROVEDVENDOR = ?
#                   AND DATAAREAID = 'hi-q'
#             """, (vendor_account,))

#             return [str(r[0]).strip().upper() for r in cur.fetchall() if r[0]]

#     except Exception as e:
#         print(f"[APPROVED VENDOR ERROR]: {e}")
#         return []


# # ============================================================
# # COMPLETED LIST
# # ============================================================
# def fetch_completed_rfqs(vendor_account: str) -> List[Dict[str, Any]]:

#     approved_items = _get_approved_items(vendor_account)

#     if not approved_items:
#         return []

#     # STEP 1 — portal DB: get submitted RFQs
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute(f"""
#             SELECT
#                 RFQCASEID,
#                 RFQID,
#                 VENDORACCOUNT,
#                 MAX(SENDTOD365AT) AS SUBMITTED_ON
#             FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)
#             WHERE VENDORACCOUNT = ?
#               AND SUBMISSIONSTATUS = 1
#             GROUP BY RFQCASEID, RFQID, VENDORACCOUNT
#             ORDER BY MAX(SENDTOD365AT) DESC
#         """, (vendor_account,))

#         rows = cur.fetchall()

#         if not rows:
#             return []

#         cols = [c[0] for c in cur.description]
#         portal_rfqs = [dict(zip(cols, r)) for r in rows]

#     rfq_ids = [r["RFQID"] for r in portal_rfqs if r["RFQID"]]

#     if not rfq_ids:
#         return []

#     placeholders = ",".join(["?"] * len(rfq_ids))
#     item_placeholders = ",".join(["?"] * len(approved_items))

#     portal_map = {
#         (r["RFQID"], r["VENDORACCOUNT"]): r
#         for r in portal_rfqs
#     }

#     # STEP 2 — D365 DB: get completed RFQ metadata
#     d365_query = f"""
#         SELECT
#             T.RFQID,
#             T.VENDACCOUNT,
#             T.RFQCASEID,
#             L.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,

#             (
#                 SELECT TOP 1 CURRENCYCODE
#                 FROM PURCHRFQREPLYTABLE WITH (NOLOCK)
#                 WHERE RFQID = T.RFQID
#                   AND DATAAREAID = 'hi-q'
#             ) AS CURRENCY,

#             PM.NAME AS PAYMENT_MODE,
#             PT.DESCRIPTION AS PAYMENT_TERM,
#             DM.TXT AS DELIVERY_MODE,
#             DT.TXT AS DELIVERY_TERM

#         FROM PurchRFQTable T WITH (NOLOCK)

#         LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
#             ON L.RFQCASEID = T.RFQCASEID
#             AND L.DATAAREAID = 'hi-q'

#         LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
#             ON L.PAYMMODE = PM.PAYMMODE

#         LEFT JOIN PAYMTERM PT WITH (NOLOCK)
#             ON L.PAYMENT = PT.PAYMTERMID

#         LEFT JOIN DLVMODE DM WITH (NOLOCK)
#             ON L.DLVMODE = DM.CODE

#         LEFT JOIN DLVTERM DT WITH (NOLOCK)
#             ON L.DLVTERM = DT.CODE

#         WHERE T.VENDACCOUNT = ?
#           AND T.RFQID IN ({placeholders})
#           AND EXISTS (
#               SELECT 1
#               FROM PURCHRFQREPLYLINE RL2 WITH (NOLOCK)
#               INNER JOIN PURCHRFQLINE PL WITH (NOLOCK)
#                   ON PL.RECID = RL2.RFQLINERECID
#                  AND PL.DATAAREAID = 'hi-q'
#               WHERE RL2.RFQID = T.RFQID
#                 AND RL2.DATAAREAID = 'hi-q'
#                 AND PL.STATUS >= 3
#           )
#     """

#     result = []

#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute(d365_query, [vendor_account] + rfq_ids)

#         d365_rows = cur.fetchall()

#         if not d365_rows:
#             return []

#         d365_cols = [c[0] for c in cur.description]
#         d365_data = [dict(zip(d365_cols, r)) for r in d365_rows]

#         for data in d365_data:
#             rfq_id = data["RFQID"]
#             vend_account = data["VENDACCOUNT"]

#             portal_row = portal_map.get((rfq_id, vend_account))

#             if not portal_row:
#                 continue

#             quoted_amount = 0.0

#             cur.execute(f"""
#                 SELECT ISNULL(SUM(RL.LINEAMOUNT), 0)
#                 FROM PURCHRFQREPLYLINE RL WITH (NOLOCK)

#                 INNER JOIN PURCHRFQLINE PL2 WITH (NOLOCK)
#                     ON PL2.RECID = RL.RFQLINERECID
#                    AND PL2.DATAAREAID = 'hi-q'

#                 WHERE RL.RFQID = ?
#                   AND RL.DATAAREAID = 'hi-q'
#                   AND PL2.STATUS >= 3
#                   AND UPPER(LTRIM(RTRIM(PL2.ITEMID))) IN ({item_placeholders})
#             """, [rfq_id] + approved_items)

#             quoted_amount = float(cur.fetchone()[0] or 0)

#             result.append({
#                 "rfq_id": rfq_id,
#                 "rfq_case_id": portal_row["RFQ_CASE_ID"],
#                 "submitted_on_date": format_utc_iso(portal_row["SUBMITTED_ON"]),
#                 "quoted_amount": quoted_amount,
#                 "currency": data["CURRENCY"] or "INR",
#                 "payment_mode": data["PAYMENT_MODE"] or "-",
#                 "payment_term": data["PAYMENT_TERM"] or "-",
#                 "delivery_mode": data["DELIVERY_MODE"] or "-",
#                 "delivery_term": data["DELIVERY_TERM"] or "-",
#                 "delivery_date": format_utc_iso(data["EXPECTED_DELIVERY_DATE"])
#             })

#     return result


# # ============================================================
# # COMPLETED DETAIL
# # ============================================================
# def fetch_completed_rfq_detail(rfq_id: str, vendor_account: str) -> Dict[str, Any]:

#     approved_items = _get_approved_items(vendor_account)

#     if not approved_items:
#         return {
#             "success": False,
#             "message": "No approved items found"
#         }

#     # STEP 1 — portal DB: validate RFQ belongs to vendor
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute(f"""
#             SELECT TOP 1
#                 RFQID,
#                 RFQCASEID,
#                 VENDORACCOUNT
#             FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)
#             WHERE UPPER(RFQID) = UPPER(?)
#               AND UPPER(VENDORACCOUNT) = UPPER(?)
#               AND SUBMISSIONSTATUS = 1
#         """, (rfq_id, vendor_account))

#         row = cur.fetchone()

#         if not row:
#             return {
#                 "success": False,
#                 "message": "RFQ not found"
#             }

#         rfq_id = str(row[0]).strip()
#         rfq_case_id = row[1]

#     item_placeholders = ",".join(["?"] * len(approved_items))

#     # STEP 2 — D365 DB: header
#     with get_connection() as conn:
#         cur = conn.cursor()

#         cur.execute("""
#             SELECT TOP 1
#                 RT.RFQID,
#                 RT.CURRENCYCODE,
#                 RT.DELIVERYDATE AS REPLY_DELIVERY_DATE,
#                 RT.DLVMODE AS REPLY_DELIVERY_MODE,
#                 RT.DLVTERM AS REPLY_DELIVERY_TERM,
#                 RT.PAYMENT AS REPLY_PAYMENT_TERM,
#                 RT.VENDREF,
#                 RT.TOTALSCORE,
#                 RT.RANK,
#                 RT.VALIDFROM,
#                 RT.VALIDTO,
#                 RT.VALIDITYDATESTART,
#                 RT.VALIDITYDATEEND,
#                 RT.REPLYPROGRESSSTATUS,
#                 RT.HIQ_COMMENTS AS REMARKS,

#                 T.RFQCASEID AS RFQ_CASE_ID,
#                 L.EXPIRYDATETIME AS CLOSING_DATE,
#                 L.CREATEDDATETIME AS ISSUE_DATE,
#                 L.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,
#                 L.NAME AS DOCUMENT_TITLE,

#                 PM.NAME AS PAYMENT_MODE,
#                 PT.DESCRIPTION AS PAYMENT_TERM,
#                 DM.TXT AS DELIVERY_MODE,
#                 DT.TXT AS DELIVERY_TERM,

#                 T.HIQ_TERMSANDCONDITIONS

#             FROM PURCHRFQREPLYTABLE RT WITH (NOLOCK)

#             INNER JOIN PurchRFQTable T WITH (NOLOCK)
#                 ON T.RFQID = RT.RFQID
#                AND T.VENDACCOUNT = ?
#                AND T.DATAAREAID = 'hi-q'

#             LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
#                 ON L.RFQCASEID = T.RFQCASEID
#                AND L.DATAAREAID = 'hi-q'

#             LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
#                 ON L.PAYMMODE = PM.PAYMMODE

#             LEFT JOIN PAYMTERM PT WITH (NOLOCK)
#                 ON L.PAYMENT = PT.PAYMTERMID

#             LEFT JOIN DLVMODE DM WITH (NOLOCK)
#                 ON L.DLVMODE = DM.CODE

#             LEFT JOIN DLVTERM DT WITH (NOLOCK)
#                 ON L.DLVTERM = DT.CODE

#             WHERE RT.RFQID = ?
#               AND RT.DATAAREAID = 'hi-q'
#         """, (vendor_account, rfq_id))

#         row = cur.fetchone()

#         if not row:
#             return {
#                 "success": False,
#                 "message": "RFQ not found"
#             }

#         cols = [c[0] for c in cur.description]
#         header = dict(zip(cols, row))

#         # STEP 3 — D365 DB: lines
#         cur.execute(f"""
#             SELECT
#                 RL.LINENUM,
#                 RL.NAME AS ITEM_NAME,
#                 RL.PURCHQTY AS QUANTITY,
#                 RL.PURCHUNIT AS UOM,
#                 RL.PURCHPRICE AS UNIT_PRICE,
#                 RL.LINEAMOUNT AS NET_AMOUNT,
#                 RL.LINEDISC AS LINE_DISC,
#                 RL.LINEPERCENT AS LINE_PERCENT,
#                 RL.DELIVERYDATE AS DELIVERY_DATE,
#                 RL.LEADTIME,
#                 RL.HIQ_COMMENTS AS VENDOR_COMMENTS,
#                 RL.VALIDFROM AS LINE_VALID_FROM,
#                 RL.VALIDTO AS LINE_VALID_TO,
#                 RL.EXTERNALITEMID,
#                 RL.MAXIMUMRETAILPRICE_IN AS MRP,

#                 PL.HIQ_TARGETPRICE AS TARGETPRICE,
#                 PL.HIQ_COMMENTS AS COMMENTS,
#                 PL.ITEMID,
#                 PL.STATUS,
#                 PL.CURRENCYCODE,
#                 PL.PURCHID,
#                 PL.DELIVERYDATE AS LINE_DELIVERY_DATE,
#                 RL.DELIVERYDATE AS VENDORREPLY_DELIVERY_DATE,

#                 CASE PL.STATUS
#                     WHEN 3 THEN 'Rejected'
#                     WHEN 4 THEN 'Accepted'
#                     WHEN 5 THEN 'Canceled'
#                     WHEN 6 THEN 'Declined'
#                     ELSE 'Under Review'
#                 END AS HIQ_DECISION

#             FROM PURCHRFQREPLYLINE RL WITH (NOLOCK)

#             INNER JOIN PURCHRFQLINE PL WITH (NOLOCK)
#                 ON PL.RECID = RL.RFQLINERECID
#                AND PL.DATAAREAID = 'hi-q'

#             WHERE RL.RFQID = ?
#               AND RL.DATAAREAID = 'hi-q'
#               AND PL.STATUS >= 3
#               AND UPPER(LTRIM(RTRIM(PL.ITEMID))) IN ({item_placeholders})

#             ORDER BY RL.LINENUM
#         """, [rfq_id] + approved_items)

#         line_rows = cur.fetchall()
#         line_cols = [c[0] for c in cur.description]
#         lines = [dict(zip(line_cols, r)) for r in line_rows]

#     return {
#         "success": True,
#         "data": {
#             "rfq_id": rfq_id,
#             "rfq_case_id": rfq_case_id or header["RFQ_CASE_ID"],
#             "delivery_date": format_utc_iso(header["EXPECTED_DELIVERY_DATE"]),
#             "payment_term": header["PAYMENT_TERM"] or "-",
#             "delivery_term": header["DELIVERY_TERM"] or "-",
#             "delivery_mode": header["DELIVERY_MODE"] or "-",
#             "payment_mode": header["PAYMENT_MODE"] or "-",
#             "issue_date": format_utc_iso(header["ISSUE_DATE"]),
#             "closing_date": format_utc_iso(header["CLOSING_DATE"]),
#             "document_title": header["DOCUMENT_TITLE"],
#             "currency": header["CURRENCYCODE"] or "INR",
#             "reply_delivery_date": format_utc_iso(header["REPLY_DELIVERY_DATE"]),
#             "reply_delivery_mode": header["REPLY_DELIVERY_MODE"] or "-",
#             "reply_delivery_term": header["REPLY_DELIVERY_TERM"] or "-",
#             "reply_payment_term": header["REPLY_PAYMENT_TERM"] or "-",
#             "vendor_ref": header["VENDREF"] or "-",
#             "valid_from": format_utc_iso(header["VALIDFROM"]),
#             "valid_to": format_utc_iso(header["VALIDTO"]),
#             "validity_date_start": format_utc_iso(header["VALIDITYDATESTART"]),
#             "validity_date_end": format_utc_iso(header["VALIDITYDATEEND"]),
#             "total_score": header["TOTALSCORE"] or 0,
#             "rank": header["RANK"] or 0,
#             "reply_progress_status": header["REPLYPROGRESSSTATUS"] or 0,
#             "remarks": header["REMARKS"] or "",
#             "termsandconditions": header["HIQ_TERMSANDCONDITIONS"],
#             "line_items": [
#                 {
#                     "line_num": int(float(line["LINENUM"])),
#                     "item_id": line["ITEMID"] or "-",
#                     "item_name": line["ITEM_NAME"] or "-",
#                     "external_item_id": line["EXTERNALITEMID"] or "-",
#                     "quantity": float(line["QUANTITY"] or 0),
#                     "uom": line["UOM"] or "-",
#                     "unit_price": float(line["UNIT_PRICE"] or 0),
#                     "net_amount": float(line["NET_AMOUNT"] or 0),
#                     "line_disc": float(line["LINE_DISC"] or 0),
#                     "line_percent": float(line["LINE_PERCENT"] or 0),
#                     "mrp": float(line["MRP"] or 0),
#                     "delivery_date": format_utc_iso(line["DELIVERY_DATE"]),
#                     "lead_time": line["LEADTIME"] or 0,
#                     "vendor_comments": line["VENDOR_COMMENTS"] or " ",
#                     "currency": line["CURRENCYCODE"] or "INR",
#                     "line_valid_from": format_utc_iso(line["LINE_VALID_FROM"]),
#                     "line_valid_to": format_utc_iso(line["LINE_VALID_TO"]),
#                     "hiq_decision": line["HIQ_DECISION"],
#                     "target_price": round(float(line["TARGETPRICE"] or 0), 2),
#                     "comments": line["COMMENTS"] or " ",
#                     "purchid": line["PURCHID"],
#                     "rfq_delivery_date": format_utc_iso(line.get("LINE_DELIVERY_DATE")),
#                     "vendor_delivery_date": format_utc_iso(line.get("VENDORREPLY_DELIVERY_DATE"))
#                 }
#                 for line in lines
#             ]
#         }
#     }



# # from app.db.base import get_connection, get_connection
# # from app.utils.date_utils import format_utc_iso,format_date
# # from typing import List, Dict, Any

# # # ============================================================
# # # PL.STATUS MEANING:
# # #   0 = Created       → Under Review  (stays in Submitted tab)
# # #   1 = Sent          → Under Review  (stays in Submitted tab)
# # #   2 = Received      → Under Review  (stays in Submitted tab)
# # #   ─────────────────────────────────────────────────────────
# # #   3 = Rejected      → Not Selected  (moves to Completed tab)
# # #   4 = Accepted      → Won           (moves to Completed tab)
# # #   5 = Canceled      → Canceled      (moves to Completed tab)
# # #   6 = Declined      → Not Selected  (moves to Completed tab)
# # # ============================================================


# # def _get_approved_items(vendor_account: str) -> List[str]:
# #     """
# #     Fetch approved item IDs for a vendor from D365.
# #     PDSAPPROVEDVENDORLIST lives in AxDb — must use get_connection().
# #     """
# #     try:
        
# #         with get_connection() as conn:
# #             cur = conn.cursor()
# #             cur.execute("""
# #                 SELECT ITEMID
# #                 FROM PDSAPPROVEDVENDORLIST WITH (NOLOCK)
# #                 WHERE PDSAPPROVEDVENDOR = ?
# #                   AND DATAAREAID        = 'hi-q'
# #                   --AND VALIDFROM        <= GETUTCDATE()
# #                   --AND VALIDTO          >= GETUTCDATE()
# #             """, (vendor_account,))
# #             return [str(r[0]).strip() for r in cur.fetchall()]
# #     except Exception as e:
# #         print(f"[APPROVED VENDOR] D365 fetch error for {vendor_account}: {e}")
# #         return []


# # # ============================================================
# # # API 1 — COMPLETED LIST
# # # /rfq/completed?vendor_account=V0011
# # # ============================================================
# # def fetch_completed_rfqs(vendor_account: str) -> List[Dict[str, Any]]:

# #     # Step 1 — get approved items from D365
# #     approved_items = _get_approved_items(vendor_account)

# #     with get_connection() as conn:
# #         cur = conn.cursor()

# #         # Step 2 — fetch completed RFQ list (no item filter needed here,
# #         #           just list-level data; quoted_amount filtered below)
# #         cur.execute("""
# #             SELECT DISTINCT
# #                 R.RFQ_CASE_ID,
# #                 R.RFQ_ID,
# #                 R.VENDOR_ACCOUNT,
# #                 L.DELIVERYDATE              AS EXPECTED_DELIVERY_DATE,
# #                 MAX(R.SEND_TO_D365_AT)      AS SUBMITTED_ON,

# #                 (
# #                     SELECT TOP 1 CURRENCYCODE
# #                     FROM PURCHRFQREPLYTABLE WITH (NOLOCK)
# #                     WHERE RFQID      = R.RFQ_ID
# #                       AND DATAAREAID = 'hi-q'
# #                 )                           AS CURRENCY,

# #                 PM.NAME                     AS PAYMENT_MODE,
# #                 PT.DESCRIPTION              AS PAYMENT_TERM,
# #                 DM.TXT                      AS DELIVERY_MODE,
# #                 DT.TXT                      AS DELIVERY_TERM

# #             FROM HIQ_VENDORRFQREPLIES R WITH (NOLOCK)

# #             LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
# #                 ON L.RFQCASEID = R.RFQ_CASE_ID

# #             LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# #                 ON L.PAYMMODE = PM.PAYMMODE

# #             LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# #                 ON L.PAYMENT = PT.PAYMTERMID

# #             LEFT JOIN DLVMODE DM WITH (NOLOCK)
# #                 ON L.DLVMODE = DM.CODE

# #             LEFT JOIN DLVTERM DT WITH (NOLOCK)
# #                 ON L.DLVTERM = DT.CODE

# #             WHERE R.VENDOR_ACCOUNT    = ?
# #               AND R.SUBMISSION_STATUS = 1

# #               AND EXISTS (
# #                   SELECT 1
# #                   FROM PURCHRFQREPLYLINE RL2 WITH (NOLOCK)
# #                   INNER JOIN PURCHRFQLINE PL WITH (NOLOCK)
# #                       ON  PL.RECID      = RL2.RFQLINERECID
# #                       AND PL.DATAAREAID = 'hi-q'
# #                   WHERE RL2.RFQID      = R.RFQ_ID
# #                     AND RL2.DATAAREAID = 'hi-q'
# #                     AND PL.STATUS      >= 3
# #               )

# #             GROUP BY
# #                 R.RFQ_CASE_ID,
# #                 R.RFQ_ID,
# #                 R.VENDOR_ACCOUNT,
# #                 PM.NAME,
# #                 PT.DESCRIPTION,
# #                 L.DELIVERYDATE,
# #                 DM.TXT,
# #                 DT.TXT

# #             ORDER BY MAX(R.SEND_TO_D365_AT) DESC
# #         """, (vendor_account,))

# #         rows = cur.fetchall()
# #         if not rows:
# #             return []

# #         cols   = [c[0] for c in cur.description]
# #         result = []

# #         for row in rows:
# #             data   = dict(zip(cols, row))
# #             rfq_id = data["RFQ_ID"]

# #             # Step 3 — calculate quoted_amount only for approved items
# #             quoted_amount = 0.0
# #             if approved_items:
# #                 placeholders = ",".join(["?" for _ in approved_items])
# #                 cur.execute(f"""
# #                     SELECT ISNULL(SUM(RL.LINEAMOUNT), 0)
# #                     FROM PURCHRFQREPLYLINE RL WITH (NOLOCK)
# #                     INNER JOIN PURCHRFQLINE PL2 WITH (NOLOCK)
# #                         ON  PL2.RECID      = RL.RFQLINERECID
# #                         AND PL2.DATAAREAID = 'hi-q'
# #                     WHERE RL.RFQID      = ?
# #                       AND RL.DATAAREAID = 'hi-q'
# #                       AND PL2.STATUS    >= 3
# #                       AND UPPER(LTRIM(RTRIM(PL2.ITEMID))) IN ({placeholders})
# #                      -- AND PL2.ITEMID    IN ({placeholders})
# #                 """, [rfq_id] + approved_items)
# #                 quoted_amount = float(cur.fetchone()[0] or 0)

# #             result.append({
# #                 "rfq_id":           rfq_id,
# #                 "rfq_case_id":      data["RFQ_CASE_ID"],
# #                 "submitted_on_date": format_utc_iso(data["SUBMITTED_ON"]),
# #                 "quoted_amount":    quoted_amount,
# #                 "currency":         data["CURRENCY"]      or "INR",
# #                 "payment_mode":     data["PAYMENT_MODE"]  or "-",
# #                 "payment_term":     data["PAYMENT_TERM"]  or "-",
# #                 "delivery_mode":    data["DELIVERY_MODE"] or "-",
# #                 "delivery_term":    data["DELIVERY_TERM"] or "-",
# #                 "delivery_date":    format_utc_iso(data["EXPECTED_DELIVERY_DATE"])
# #             })

# #         return result


# # # ============================================================
# # # API 2 — COMPLETED DETAIL
# # # /rfq/completed-detail?rfq_id=Hi-Q-000133&vendor_account=V0011
# # # ============================================================
# # def fetch_completed_rfq_detail(rfq_id: str, vendor_account: str) -> Dict[str, Any]:

# #     # Step 1 — get approved items from D365
# #     approved_items = _get_approved_items(vendor_account)

# #     with get_connection() as conn:
# #         cur = conn.cursor()

# #         # Step 2 — Header
# #         cur.execute("""
# #             SELECT TOP 1
# #                 RT.RFQID,
# #                 RT.CURRENCYCODE,
# #                 RT.DELIVERYDATE         AS REPLY_DELIVERY_DATE,
# #                 RT.DLVMODE              AS REPLY_DELIVERY_MODE,
# #                 RT.DLVTERM              AS REPLY_DELIVERY_TERM,
# #                 RT.PAYMENT              AS REPLY_PAYMENT_TERM,
# #                 RT.VENDREF,
# #                 RT.TOTALSCORE,
# #                 RT.RANK,
# #                 RT.VALIDFROM,
# #                 RT.VALIDTO,
# #                 RT.VALIDITYDATESTART,
# #                 RT.VALIDITYDATEEND,
# #                 RT.REPLYPROGRESSSTATUS,
# #                 RT.HIQ_COMMENTS         AS REMARKS,
# #                 R.RFQ_CASE_ID,
# #                 L.EXPIRYDATETIME        AS CLOSING_DATE,
# #                 L.CREATEDDATETIME       AS ISSUE_DATE,
# #                 L.DELIVERYDATE          AS EXPECTED_DELIVERY_DATE,
# #                 L.NAME                  AS DOCUMENT_TITLE,
# #                 PM.NAME                 AS PAYMENT_MODE,
# #                 PT.DESCRIPTION          AS PAYMENT_TERM,
# #                 DM.TXT                  AS DELIVERY_MODE,
# #                 DT.TXT                  AS DELIVERY_TERM,
# #                 T.HIQ_TERMSANDCONDITIONS
                
# #             FROM PURCHRFQREPLYTABLE RT WITH (NOLOCK)

# #             INNER JOIN HIQ_VENDORRFQREPLIES R WITH (NOLOCK)
# #                 ON  R.RFQ_ID         = RT.RFQID
# #                 AND R.VENDOR_ACCOUNT = ?

# #             LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
# #                 ON  L.RFQCASEID  = R.RFQ_CASE_ID
# #                 AND L.DATAAREAID = 'hi-q'
# #             LEFT JOIN PurchRFQTable T WITH (NOLOCK)   -- ✅ ADD THIS JOIN
# #                 ON  T.RFQCASEID   = L.RFQCASEID
# #                 AND T.VENDACCOUNT = R.VENDOR_ACCOUNT
# #                 AND T.DATAAREAID  = 'hi-q'

# #             LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# #                 ON L.PAYMMODE = PM.PAYMMODE

# #             LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# #                 ON L.PAYMENT = PT.PAYMTERMID

# #             LEFT JOIN DLVMODE DM WITH (NOLOCK)
# #                 ON L.DLVMODE = DM.CODE

# #             LEFT JOIN DLVTERM DT WITH (NOLOCK)
# #                 ON L.DLVTERM = DT.CODE

# #             WHERE RT.RFQID      = ?
# #               AND RT.DATAAREAID = 'hi-q'
# #         """, (vendor_account, rfq_id))

# #         row = cur.fetchone()
# #         if not row:
# #             return {"success": False, "message": "RFQ not found"}

# #         cols   = [c[0] for c in cur.description]
# #         header = dict(zip(cols, row))

# #         # Step 3 — Lines filtered by approved items
# #         lines = []
# #         if approved_items:
# #             placeholders = ",".join(["?" for _ in approved_items])
# #             cur.execute(f"""
# #                 SELECT
# #                     RL.LINENUM,
# #                     RL.NAME                     AS ITEM_NAME,
# #                     RL.PURCHQTY                 AS QUANTITY,
# #                     RL.PURCHUNIT                AS UOM,
# #                     RL.PURCHPRICE               AS UNIT_PRICE,
# #                     RL.LINEAMOUNT               AS NET_AMOUNT,
# #                     RL.LINEDISC                 AS LINE_DISC,
# #                     RL.LINEPERCENT              AS LINE_PERCENT,
# #                     RL.DELIVERYDATE             AS DELIVERY_DATE,
# #                     RL.LEADTIME,
# #                     RL.HIQ_COMMENTS             AS VENDOR_COMMENTS,
# #                     RL.VALIDFROM                AS LINE_VALID_FROM,
# #                     RL.VALIDTO                  AS LINE_VALID_TO,
# #                     RL.EXTERNALITEMID,
# #                     RL.MAXIMUMRETAILPRICE_IN    AS MRP,
# #                     PL.HIQ_TARGETPRICE          AS TARGETPRICE,
# #                     PL.HIQ_COMMENTS             AS COMMENTS,
# #                     PL.ITEMID,
# #                     PL.STATUS,
# #                     PL.CURRENCYCODE,
# #                     PL.PURCHID,
# #                     PL.DELIVERYDATE     AS LINE_DELIVERY_DATE,
# #                     RL.DELIVERYDATE AS VENDORREPLY_DELIVERY_DATE,
# #                     CASE PL.STATUS
# #                         WHEN 3 THEN 'Rejected'
# #                         WHEN 4 THEN 'Accepted'
# #                         WHEN 5 THEN 'Caceled'
# #                         WHEN 6 THEN 'Declined'
# #                         ELSE        'Under Review'
# #                     END                         AS HIQ_DECISION

# #                 FROM PURCHRFQREPLYLINE RL WITH (NOLOCK)

# #                 INNER JOIN PURCHRFQLINE PL WITH (NOLOCK)
# #                     ON  PL.RECID      = RL.RFQLINERECID
# #                     AND PL.DATAAREAID = 'hi-q'

# #                 WHERE RL.RFQID      = ?
# #                   AND RL.DATAAREAID = 'hi-q'
# #                   AND PL.STATUS     >= 3
# #                   AND UPPER(LTRIM(RTRIM(PL.ITEMID))) IN ({placeholders})
# #                   --AND PL.ITEMID     IN ({placeholders})

# #                 ORDER BY RL.LINENUM
# #             """, [rfq_id] + approved_items)

# #             line_rows = cur.fetchall()
# #             line_cols = [c[0] for c in cur.description]
# #             lines     = [dict(zip(line_cols, r)) for r in line_rows]

# #     return {
# #         "success": True,
# #         "data": {
# #             "rfq_id":                   rfq_id,
# #             "rfq_case_id":              header["RFQ_CASE_ID"],
# #             "delivery_date":            format_utc_iso(header["EXPECTED_DELIVERY_DATE"]),
# #             "payment_term":             header["PAYMENT_TERM"]          or "-",
# #             "delivery_term":            header["DELIVERY_TERM"]         or "-",
# #             "delivery_mode":            header["DELIVERY_MODE"]         or "-",
# #             "payment_mode":             header["PAYMENT_MODE"]          or "-",
# #             "issue_date":               format_utc_iso(header["ISSUE_DATE"]),
# #             "closing_date":             format_utc_iso(header["CLOSING_DATE"]),
# #             "document_title":           header["DOCUMENT_TITLE"],
# #             "currency":                 header["CURRENCYCODE"]          or "INR",
# #             "reply_delivery_date":      format_utc_iso(header["REPLY_DELIVERY_DATE"]),
# #             "reply_delivery_mode":      header["REPLY_DELIVERY_MODE"]   or "-",
# #             "reply_delivery_term":      header["REPLY_DELIVERY_TERM"]   or "-",
# #             "reply_payment_term":       header["REPLY_PAYMENT_TERM"]    or "-",
# #             "vendor_ref":               header["VENDREF"]               or "-",
# #             "valid_from":               format_utc_iso(header["VALIDFROM"]),
# #             "valid_to":                 format_utc_iso(header["VALIDTO"]),
# #             "validity_date_start":      format_utc_iso(header["VALIDITYDATESTART"]),
# #             "validity_date_end":        format_utc_iso(header["VALIDITYDATEEND"]),
# #             "total_score":              header["TOTALSCORE"]            or 0,
# #             "rank":                     header["RANK"]                  or 0,
# #             "reply_progress_status":    header["REPLYPROGRESSSTATUS"]   or 0,
# #             "remarks":                  header["REMARKS"]               or "",
# #             "termsandconditions":     header["HIQ_TERMSANDCONDITIONS"],
# #             "line_items": [
# #                 {
# #                     "line_num":         int(float(line["LINENUM"])),
# #                     "item_id":          line["ITEMID"]               or "-",
# #                     "item_name":        line["ITEM_NAME"]            or "-",
# #                     "external_item_id": line["EXTERNALITEMID"]       or "-",
# #                     "quantity":         float(line["QUANTITY"]       or 0),
# #                     "uom":              line["UOM"]                  or "-",
# #                     "unit_price":       float(line["UNIT_PRICE"]     or 0),
# #                     "net_amount":       float(line["NET_AMOUNT"]     or 0),
# #                     "line_disc":        float(line["LINE_DISC"]      or 0),
# #                     "line_percent":     float(line["LINE_PERCENT"]   or 0),
# #                     "mrp":              float(line["MRP"]            or 0),
# #                     "delivery_date":    format_utc_iso(line["DELIVERY_DATE"]),
# #                     "lead_time":        line["LEADTIME"]             or 0,
# #                     "vendor_comments":  line["VENDOR_COMMENTS"]      or " ",
# #                     "currency":         line["CURRENCYCODE"]       or "INR",
# #                     "line_valid_from":  format_utc_iso(line["LINE_VALID_FROM"]),
# #                     "line_valid_to":    format_utc_iso(line["LINE_VALID_TO"]),
# #                     "hiq_decision":     line["HIQ_DECISION"],
# #                     "target_price":     round(float(line['TARGETPRICE'] or 0), 2),
# #                     # "target_price":     f"{round(float(line['TARGETPRICE'] or 0), 2)} {line['CURRENCYCODE']}",
# #                     "comments":         line["COMMENTS"] or " ",
# #                     "purchid":line["PURCHID"],
# #                     "rfq_delivery_date": format_utc_iso(line.get("LINE_DELIVERY_DATE")),
# #                     "vendor_delivery_date": format_utc_iso(line.get("VENDORREPLY_DELIVERY_DATE"))
# #                 }
# #                 for line in lines
# #             ]
# #         }
# #     }
