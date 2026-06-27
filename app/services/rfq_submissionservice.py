from app.db.base import get_connection
from app.utils.date_utils import format_utc_iso
from typing import List, Dict, Any, Optional, Set, Tuple
import json
from app.core.config import settings


SCHEMA = settings.DB_SCHEMA

RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VENDORRFQREPLIES"
BID_HEADER_TABLE = f"{SCHEMA}.HIQ_VENDORBIDSUBMISSIONHEADER"
BID_LINE_TABLE = f"{SCHEMA}.HIQ_VENDORBIDSUBMISSIONLINE"


# ============================================================
# APPROVED ITEMS
# ============================================================
def _get_approved_items(vendor_account: str) -> List[str]:
    try:
        with get_connection() as conn:
            cur = conn.cursor()

            cur.execute(f"""
                SELECT ITEMID
                FROM {SCHEMA}.D365_PDSAPPROVEDVENDORLIST WITH (NOLOCK)
                WHERE PDSAPPROVEDVENDOR = ?
                  AND VALIDFROM <= GETUTCDATE()
                  AND VALIDTO >= GETUTCDATE()
            """, (vendor_account,))

            return [
                str(r[0]).upper()
                for r in cur.fetchall()
                if r[0]
            ]

    except Exception as e:
        print(f"[APPROVED ERROR]: {e}")
        return []


# ============================================================
# PAYLOAD FILTER
# ============================================================
def _get_valid_payload_items(
    rfq_id: str,
    vendor_account: str
) -> Optional[Set[Tuple[int, str]]]:
    try:
        with get_connection() as conn:
            cur = conn.cursor()

            cur.execute(f"""
                SELECT TOP 1 PAYLOADJSON
                FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)
                WHERE UPPER(RFQID) = UPPER(?)
                  AND UPPER(VENDORACCOUNT) = UPPER(?)
                ORDER BY ID DESC
            """, (rfq_id, vendor_account))

            row = cur.fetchone()

        if not row or not row[0]:
            return None

        payload = json.loads(row[0])
        items = payload.get("Item", [])

        has_line_status = any("lineStatus" in i for i in items)
        if not has_line_status:
            return None

        valid = set()

        for i in items:
            if str(i.get("lineStatus")).lower() == "true":
                item_number = i.get("itemNumber")
                line_number = i.get("lineNumber")

                if item_number and line_number is not None:
                    valid.add((
                        int(line_number),
                        str(item_number).upper()
                    ))

        return valid

    except Exception as e:
        print(f"[PAYLOAD ERROR]: {e}")
        return None


# ============================================================
# SUBMITTED RFQ LIST
# Uses staging tables:
#   HIQ_VENDORBIDSUBMISSIONHEADER
#   HIQ_VENDORBIDSUBMISSIONLINE
# ============================================================
def fetch_submitted_rfqs(vendor_account: str) -> List[Dict[str, Any]]:
    approved_items = _get_approved_items(vendor_account)

    if not approved_items:
        return []

    try:
        placeholders = ",".join(["?"] * len(approved_items))

        with get_connection() as conn:
            cur = conn.cursor()

            cur.execute(f"""
                SELECT
                    H.RFQCASEID,
                    H.RFQID,
                    H.VENDORACCOUNT,
                    H.CREATEDDATETIME AS SUBMITTED_ON,
                    C.EXPIRYDATETIME AS CLOSING_DATE,
                    H.REPLYDELIVERYDATE AS DELIVERY_DATE,
                    H.REPLYMODEOFDELIVERY AS DELIVERY_MODE,
                    H.REPLYDELIVERYTERMS AS DELIVERY_TERM,
                    H.METHODOFPAYMENT AS PAYMENT_MODE,
                    H.TERMSOFPAYMENT AS PAYMENT_TERM,
                    H.CURRENCY,
                    ISNULL(SUM(L.NETAMOUNT), 0) AS BID_VALUE
                FROM {BID_HEADER_TABLE} H WITH (NOLOCK)
                INNER JOIN {BID_LINE_TABLE} L WITH (NOLOCK)
                    ON L.HEADERID = H.ID
                   AND L.RFQID = H.RFQID
                   AND L.VENDORACCOUNT = H.VENDORACCOUNT
                LEFT JOIN {SCHEMA}.D365_PURCHRFQCASETABLE C WITH (NOLOCK)
                 ON UPPER(C.RFQCASEID) = UPPER(H.RFQCASEID)
                WHERE UPPER(H.VENDORACCOUNT) = UPPER(?)
                  AND H.STATUS = 2
                  AND L.ITEMNUMBER IN ({placeholders})
                  AND EXISTS
                (
                    SELECT 1
                    FROM
                    (
                        SELECT
                            RFQID,
                            LINENUM,
                            STATUS,
                            ROW_NUMBER() OVER
                            (
                                PARTITION BY RFQID, LINENUM
                                ORDER BY RECID DESC
                            ) RN
                        FROM {SCHEMA}.D365_PURCHRFQLINE
                    ) X
                    WHERE X.RFQID = H.RFQID
                    AND X.LINENUM = L.LINENUMBER
                    AND X.RN = 1
                    AND X.STATUS < 3
                )
                GROUP BY
                    H.RFQCASEID,
                    H.RFQID,
                    H.VENDORACCOUNT,
                    H.CREATEDDATETIME,
                    C.EXPIRYDATETIME,
                    H.REPLYDELIVERYDATE,
                    H.REPLYMODEOFDELIVERY,
                    H.REPLYDELIVERYTERMS,
                    H.METHODOFPAYMENT,
                    H.TERMSOFPAYMENT,
                    H.CURRENCY
                ORDER BY H.CREATEDDATETIME DESC
            """, [vendor_account] + approved_items)

            rows = cur.fetchall()
            if not rows:
                return []

            cols = [c[0] for c in cur.description]
            result = []

            for row in rows:
                data = dict(zip(cols, row))
                rfq_id = data["RFQID"]

                valid_items = _get_valid_payload_items(rfq_id, vendor_account)
                if valid_items:
                    cur.execute(f"""
                        SELECT
                            LINENUMBER,
                            ITEMNUMBER
                        FROM {BID_LINE_TABLE} WITH (NOLOCK)
                        WHERE UPPER(RFQID) = UPPER(?)
                          AND UPPER(VENDORACCOUNT) = UPPER(?)
                          AND ITEMNUMBER IN ({placeholders})
                    """, [rfq_id, vendor_account] + approved_items)

                    line_rows = cur.fetchall()
                    has_valid_line = False

                    for line in line_rows:
                        line_num = int(line[0])
                        item_id = str(line[1]).upper()

                        if (line_num, item_id) in valid_items:
                            has_valid_line = True
                            break

                    if not has_valid_line:
                        continue

                result.append({
                    "rfq_id": rfq_id,
                    "rfq_case_id": data["RFQCASEID"],
                    "submitted_on_date": format_utc_iso(data["SUBMITTED_ON"]),
                    "closing_date": format_utc_iso(data["CLOSING_DATE"]),
                    "bid_value": float(data["BID_VALUE"] or 0),
                    "currency": data["CURRENCY"] or "INR",
                    "payment_mode": data["PAYMENT_MODE"] or "-",
                    "payment_term": data["PAYMENT_TERM"] or "-",
                    "delivery_mode": data["DELIVERY_MODE"] or "-",
                    "delivery_term": data["DELIVERY_TERM"] or "-",
                    "delivery_date": format_utc_iso(data["DELIVERY_DATE"])
                })

            return result

    except Exception as e:
        print(f"[SUBMITTED RFQ LIST ERROR]: {e}")
        return []


# ============================================================
# SUBMITTED RFQ DETAIL
# Uses only staging submission header/line for submitted values.
# Removed unavailable D365 reply fields:
# TOTALSCORE, RANK, VALIDFROM, VALIDTO, VALIDITYDATESTART,
# VALIDITYDATEEND, REPLYPROGRESSSTATUS, MRP, LEADTIME,
# EXTERNALITEMID, LINEDISC, LINEPERCENT.
# ============================================================
def fetch_submitted_rfq_detail(
    rfq_id: str,
    vendor_account: str
) -> Dict[str, Any]:
    approved_items = _get_approved_items(vendor_account)

    if not approved_items:
        return {
            "success": True,
            "data": {
                "rfq_id": rfq_id,
                "rfq_case_id": None,
                "line_items": []
            }
        }

    valid_payload = _get_valid_payload_items(rfq_id, vendor_account)

    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                SELECT TOP 1
                    H.ID AS HEADERID,
                    H.RFQID,
                    H.RFQCASEID,
                    H.DOCUMENTTITLE,
                    H.VENDORACCOUNT,
                    H.EXPIRYDATE AS CLOSING_DATE,

                    L.CREATEDDATETIME AS ISSUE_DATE,

                    H.REPLYDELIVERYDATE AS DELIVERY_DATE,
                    H.REPLYDELIVERYDATE AS REPLY_DELIVERY_DATE,
                    H.REPLYMODEOFDELIVERY AS REPLY_DELIVERY_MODE,
                    H.REPLYDELIVERYTERMS AS REPLY_DELIVERY_TERM,
                    H.MODEOFDELIVERY AS DELIVERY_MODE,
                    H.DELIVERYTERMS AS DELIVERY_TERM,
                    H.METHODOFPAYMENT AS PAYMENT_MODE,
                    H.TERMSOFPAYMENT AS PAYMENT_TERM,
                    H.CURRENCY,
                    H.VENDORCOMMENTS AS REMARKS,
                    H.CONFIRMSAVE,
                    H.STATUS,
                    H.CREATEDDATETIME,
                    H.SUBMITTEDTOD365AT

                FROM {BID_HEADER_TABLE} H WITH (NOLOCK)

                LEFT JOIN {SCHEMA}.d365_PurchRFQCaseTable L WITH (NOLOCK)
                    ON UPPER(L.RFQCASEID)
                    = UPPER(H.RFQCASEID)

                WHERE UPPER(H.RFQID) = UPPER(?)
                AND UPPER(H.VENDORACCOUNT) = UPPER(?)

                ORDER BY H.ID DESC
            """, (rfq_id, vendor_account))
            # cur.execute(f"""SELECT TOP 1
            #         H.ID AS HEADERID,
            #         H.RFQID,
            #         H.RFQCASEID,
            #         H.DOCUMENTTITLE,
            #         H.VENDORACCOUNT,
            #         H.EXPIRYDATE AS CLOSING_DATE,

            #         L.CREATEDDATETIME AS ISSUE_DATE,

            #         H.REPLYDELIVERYDATE AS DELIVERY_DATE,
            #         H.REPLYDELIVERYDATE AS REPLY_DELIVERY_DATE,
            #         H.REPLYMODEOFDELIVERY AS REPLY_DELIVERY_MODE,
            #         H.REPLYDELIVERYTERMS AS REPLY_DELIVERY_TERM,
            #         H.MODEOFDELIVERY AS DELIVERY_MODE,
            #         H.DELIVERYTERMS AS DELIVERY_TERM,
            #         H.METHODOFPAYMENT AS PAYMENT_MODE,
            #         H.TERMSOFPAYMENT AS PAYMENT_TERM,
            #         H.CURRENCY,
            #         H.VENDORCOMMENTS AS REMARKS,
            #         H.CONFIRMSAVE,
            #         H.STATUS,
            #         H.CREATEDDATETIME,
            #         H.SUBMITTEDTOD365AT

            #     FROM {BID_HEADER_TABLE} H WITH (NOLOCK)

            #     LEFT JOIN {SCHEMA}.d365_PurchRFQCaseTable  L WITH (NOLOCK)
            #         ON L.RFQCASEID = H.RFQCASEID 

            #     WHERE UPPER(H.RFQID) = UPPER(?)
            #     AND UPPER(H.VENDORACCOUNT) = UPPER(?)

            #     ORDER BY H.ID DESC
            #     """,(rfq_id, vendor_account))
            # cur.execute(f"""
            #     SELECT TOP 1
            #         H.ID AS HEADERID,
            #         H.RFQID,
            #         H.RFQCASEID,
            #         H.DOCUMENTTITLE,
            #         H.VENDORACCOUNT,
            #         H.EXPIRYDATE AS CLOSING_DATE,
            #         H.RECEIPTDATE AS ISSUE_DATE,
            #         H.REPLYDELIVERYDATE AS DELIVERY_DATE,
            #         H.REPLYDELIVERYDATE AS REPLY_DELIVERY_DATE,
            #         H.REPLYMODEOFDELIVERY AS REPLY_DELIVERY_MODE,
            #         H.REPLYDELIVERYTERMS AS REPLY_DELIVERY_TERM,
            #         H.MODEOFDELIVERY AS DELIVERY_MODE,
            #         H.DELIVERYTERMS AS DELIVERY_TERM,
            #         H.METHODOFPAYMENT AS PAYMENT_MODE,
            #         H.TERMSOFPAYMENT AS PAYMENT_TERM,
            #         H.CURRENCY,
            #         H.VENDORCOMMENTS AS REMARKS,
            #         H.CONFIRMSAVE,
            #         H.STATUS,
            #         H.CREATEDDATETIME,
            #         H.SUBMITTEDTOD365AT
            #     FROM {BID_HEADER_TABLE} H WITH (NOLOCK)
            #     WHERE UPPER(H.RFQID) = UPPER(?)
            #       AND UPPER(H.VENDORACCOUNT) = UPPER(?)
            #     ORDER BY H.ID DESC
            # """, (rfq_id, vendor_account))

            header_row = cur.fetchone()

            if not header_row:
                return {
                    "success": False,
                    "message": "RFQ not found"
                }

            header_cols = [c[0] for c in cur.description]
            header = dict(zip(header_cols, header_row))

            header_id = header["HEADERID"]
            placeholders = ",".join(["?"] * len(approved_items))

            cur.execute(f"""SELECT
    L.LINENUMBER,
    L.ITEMNUMBER,
    IT.NAME AS ITEM_NAME,
    L.QUANTITY,
    L.UNITOFMEASURE,
    L.UNITPRICE,
    L.NETAMOUNT,
    L.VENDORCOMMENTS AS VENDOR_COMMENTS,
    L.REPLYDELIVERYDATETIME AS VENDOR_DELIVERY_DATE,
    L.LINESTATUS,
    L.CREATEDDATETIME,
    L.MODIFIEDDATETIME,
    RL.HIQ_TARGETPRICE AS TARGETPRICE

FROM {BID_LINE_TABLE} L WITH (NOLOCK)

LEFT JOIN {SCHEMA}.D365_INVENTTABLE IT WITH (NOLOCK)
    ON LTRIM(RTRIM(IT.ITEMID))
     = LTRIM(RTRIM(L.ITEMNUMBER))

LEFT JOIN
(
    SELECT
        RFQID,
        LINENUM,
        ITEMID,
        HIQ_TARGETPRICE
    FROM
    (
        SELECT *,
               ROW_NUMBER() OVER
               (
                   PARTITION BY RFQID, LINENUM, ITEMID
                   ORDER BY RECID DESC
               ) AS RN
        FROM {SCHEMA}.D365_PURCHRFQLINE WITH (NOLOCK)
    ) X
    WHERE RN = 1
) RL
    ON RL.RFQID = L.RFQID
   AND RL.LINENUM = L.LINENUMBER
   AND RL.ITEMID = L.ITEMNUMBER

WHERE L.HEADERID = ?
  AND UPPER(L.RFQID) = UPPER(?)
  AND UPPER(L.VENDORACCOUNT) = UPPER(?)
  AND L.ITEMNUMBER IN ({placeholders})

ORDER BY L.LINENUMBER

            """, [header_id, rfq_id, vendor_account] + approved_items)

            rows = cur.fetchall()
            cols = [c[0] for c in cur.description]
            lines = []

            for row in rows:
                data = dict(zip(cols, row))

                line_num = int(data["LINENUMBER"])
                item_id = str(data["ITEMNUMBER"]).upper()

                if valid_payload and (line_num, item_id) not in valid_payload:
                    continue

                lines.append({
                    "line_num": line_num,
                    "item_id": data["ITEMNUMBER"],
                    "item_name": data["ITEM_NAME"] or "-",
                    "quantity": float(data["QUANTITY"] or 0),
                    "uom": data["UNITOFMEASURE"] or "-",
                    "unit_price": (
                        float(data["UNITPRICE"])
                        if data["UNITPRICE"] is not None
                        else None
                    ),
                    "net_amount": (
                        float(data["NETAMOUNT"])
                        if data["NETAMOUNT"] is not None
                        else None
                    ),
                    "vendor_comments": data["VENDOR_COMMENTS"] or " ",
                    "currency": header["CURRENCY"] or "INR",
                    "vendor_delivery_date": format_utc_iso(
                        data["VENDOR_DELIVERY_DATE"]
                    ),
                    "target_price": (
                    float(data["TARGETPRICE"])
                    if data["TARGETPRICE"] is not None
                    else 0),
                    "line_status": data["LINESTATUS"],
                    "hiq_decision": "Under Review"
                })

            return {
                "success": True,
                "data": {
                    "rfq_id": header["RFQID"],
                    "rfq_case_id": header["RFQCASEID"],
                    "delivery_date": format_utc_iso(header["DELIVERY_DATE"]),
                    "payment_term": header["PAYMENT_TERM"] or "-",
                    "delivery_term": header["DELIVERY_TERM"] or "-",
                    "delivery_mode": header["DELIVERY_MODE"] or "-",
                    "payment_mode": header["PAYMENT_MODE"] or "-",
                    "issue_date": format_utc_iso(header["ISSUE_DATE"]),
                    "closing_date": format_utc_iso(header["CLOSING_DATE"]),
                    "document_title": header["DOCUMENTTITLE"] or "-",
                    "currency": header["CURRENCY"] or "INR",
                    "reply_delivery_date": format_utc_iso(
                        header["REPLY_DELIVERY_DATE"]
                    ),
                    "reply_delivery_mode": header["REPLY_DELIVERY_MODE"] or "-",
                    "reply_delivery_term": header["REPLY_DELIVERY_TERM"] or "-",
                    "reply_payment_term": header["PAYMENT_TERM"] or "-",
                    "remarks": header["REMARKS"] or " ",
                    "status": header["STATUS"],
                    "confirm_save": header["CONFIRMSAVE"],
                    "submitted_to_d365_at": format_utc_iso(
                        header["SUBMITTEDTOD365AT"]
                    ),
                    "line_items": lines
                }
            }

    except Exception as e:
        print(f"[SUBMITTED RFQ DETAIL ERROR]: {e}")
        return {
            "success": False,
            "message": "Unable to fetch submitted RFQ detail"
        }


# from app.db.base import (
#     get_connection
# )

# from app.utils.date_utils import (
#     format_utc_iso
# )

# from typing import (
#     List,
#     Dict,
#     Any,
#     Optional,
#     Set,
#     Tuple
# )

# import json

# from app.core.config import settings


# SCHEMA = settings.DB_SCHEMA

# RFQ_REPLIES_TABLE = (
#     f"{SCHEMA}.HIQ_VENDORRFQREPLIES"
# )


# # ============================================================
# # APPROVED ITEMS
# # ============================================================
# def _get_approved_items(
#     vendor_account: str
# ) -> List[str]:

#     try:

#         with get_connection() as conn:

#             cur = conn.cursor()

#             cur.execute(f"""
#                 SELECT

#                     ITEMID

#                 FROM {SCHEMA}.D365_PDSAPPROVEDVENDORLIST
#                 WITH (NOLOCK)

#                 WHERE PDSAPPROVEDVENDOR = ?

#                   AND VALIDFROM <= GETUTCDATE()

#                   AND VALIDTO >= GETUTCDATE()
#             """, (vendor_account,))

#             return [

#                 str(r[0]).strip().upper()

#                 for r in cur.fetchall()

#                 if r[0]
#             ]

#     except Exception as e:

#         print(
#             f"[APPROVED ERROR]: {e}"
#         )

#         return []


# # ============================================================
# # PAYLOAD FILTER
# # ============================================================
# def _get_valid_payload_items(
#     rfq_id: str,
#     vendor_account: str
# ) -> Optional[Set[Tuple[int, str]]]:

#     try:

#         with get_connection() as conn:

#             cur = conn.cursor()

#             cur.execute(f"""
#                 SELECT TOP 1

#                     PAYLOADJSON

#                 FROM {RFQ_REPLIES_TABLE}
#                 WITH (NOLOCK)

#                 WHERE UPPER(RFQID) = UPPER(?)

#                   AND UPPER(VENDORACCOUNT)
#                         = UPPER(?)

#                 ORDER BY ID DESC
#             """, (rfq_id, vendor_account))

#             row = cur.fetchone()

#         if not row or not row[0]:
#             return None

#         payload = json.loads(
#             row[0]
#         )

#         items = payload.get(
#             "Item",
#             []
#         )

#         has_line_status = any(
#             "lineStatus" in i
#             for i in items
#         )

#         if not has_line_status:
#             return None

#         valid = set()

#         for i in items:

#             if str(
#                 i.get("lineStatus")
#             ).lower() == "true":

#                 item_number = i.get(
#                     "itemNumber"
#                 )

#                 line_number = i.get(
#                     "lineNumber"
#                 )

#                 if (
#                     item_number
#                     and
#                     line_number is not None
#                 ):

#                     valid.add((
#                         int(line_number),
#                         str(item_number)
#                         .strip()
#                         .upper()
#                     ))

#         return valid

#     except Exception as e:

#         print(
#             f"[PAYLOAD ERROR]: {e}"
#         )

#         return None


# # ============================================================
# # SUBMITTED RFQ LIST
# # ============================================================
# def fetch_submitted_rfqs(
#     vendor_account: str
# ) -> List[Dict[str, Any]]:

#     approved_items = _get_approved_items(
#         vendor_account
#     )

#     if not approved_items:
#         return []

#     # ========================================================
#     # STEP 1
#     # ========================================================
#     with get_connection() as conn:

#         cur = conn.cursor()

#         cur.execute(f"""
#             SELECT

#                 RFQCASEID,
#                 RFQID,

#                 MAX(SENDTOD365AT)
#                     AS SUBMITTED_ON

#             FROM {RFQ_REPLIES_TABLE}
#             WITH (NOLOCK)

#             WHERE VENDORACCOUNT = ?
#               AND SUBMISSIONSTATUS = 1

#             GROUP BY
#                 RFQCASEID,
#                 RFQID

#             ORDER BY
#                 MAX(SENDTOD365AT) DESC
#         """, (vendor_account,))

#         portal_rows = cur.fetchall()

#         if not portal_rows:
#             return []

#         portal_cols = [
#             c[0]
#             for c in cur.description
#         ]

#         submitted_rows = [
#             dict(zip(portal_cols, r))
#             for r in portal_rows
#         ]

#     rfq_ids = [
#         r["RFQID"]
#         for r in submitted_rows
#         if r["RFQID"]
#     ]

#     if not rfq_ids:
#         return []

#     placeholders = ",".join(
#         ["?"] * len(rfq_ids)
#     )

#     # ========================================================
#     # STEP 2
#     # ========================================================
#     header_query = f"""
#         SELECT

#             T.RFQID,

#             T.VENDACCOUNT,

#             T.RFQCASEID,

#             L.DELIVERYDATE
#                 AS EXPECTED_DELIVERY_DATE,

#             L.EXPIRYDATETIME
#                 AS CLOSING_DATE,

#             (
#                 SELECT TOP 1
#                     CURRENCYCODE

#                 FROM D365_PURCHRFQREPLYTABLE
#                 WITH (NOLOCK)

#                 WHERE RFQID = T.RFQID

#             ) AS CURRENCY,

#             PM.NAME
#                 AS PAYMENT_MODE,

#             PT.DESCRIPTION
#                 AS PAYMENT_TERM,

#             DM.TXT
#                 AS DELIVERY_MODE,

#             DT.TXT
#                 AS DELIVERY_TERM

#         FROM {SCHEMA}.D365_PURCHRFQTABLE T
#         WITH (NOLOCK)

#         LEFT JOIN {SCHEMA}.D365_PURCHRFQCASETABLE L
#         WITH (NOLOCK)

#             ON L.RFQCASEID = T.RFQCASEID

#         LEFT JOIN {SCHEMA}.D365_PAYMMODETABLE PM
#         WITH (NOLOCK)

#             ON L.PAYMMODE = PM.PAYMMODE

#         LEFT JOIN {SCHEMA}.D365_PAYMTERM PT
#         WITH (NOLOCK)

#             ON L.PAYMENT = PT.PAYMTERMID

#         LEFT JOIN {SCHEMA}.D365_DLVMODE DM
#         WITH (NOLOCK)

#             ON L.DLVMODE = DM.CODE

#         LEFT JOIN {SCHEMA}.D365_DLVTERM DT
#         WITH (NOLOCK)

#             ON L.DLVTERM = DT.CODE

#         WHERE T.VENDACCOUNT = ?

#           AND T.RFQID IN ({placeholders})
#     """

#     with get_connection() as conn:

#         cur = conn.cursor()

#         cur.execute(
#             header_query,
#             [vendor_account] + rfq_ids
#         )

#         header_rows = cur.fetchall()

#         header_cols = [
#             c[0]
#             for c in cur.description
#         ]

#         header_data = [
#             dict(zip(header_cols, r))
#             for r in header_rows
#         ]

#         header_map = {

#             (
#                 h["RFQID"],
#                 h["VENDACCOUNT"]
#             ): h

#             for h in header_data
#         }

#         # ====================================================
#         # STEP 3
#         # ====================================================
#         result = []

#         for portal_row in submitted_rows:

#             rfq_id = portal_row["RFQID"]

#             header = header_map.get(
#                 (rfq_id, vendor_account)
#             )

#             if not header:
#                 continue

#             valid_items = _get_valid_payload_items(
#                 rfq_id,
#                 vendor_account
#             )

#             if not valid_items:
#                 continue

#             cur.execute("""
#                 SELECT

#                     LINENUM,
#                     ITEMID,
#                     STATUS

#                 FROM D365_PURCHRFQLINE
#                 WITH (NOLOCK)

#                 WHERE RFQID = ?
#             """, (rfq_id,))

#             lines = cur.fetchall()

#             is_submitted = False

#             for l in lines:

#                 line_num = int(l[0])

#                 item = str(
#                     l[1]
#                 ).strip().upper()

#                 status = l[2]

#                 if (
#                     line_num,
#                     item
#                 ) in valid_items:

#                     if status < 3:

#                         is_submitted = True

#                         break

#             if not is_submitted:
#                 continue

#             result.append({

#                 "rfq_id":
#                     rfq_id,

#                 "rfq_case_id":
#                     portal_row["RFQCASEID"],

#                 "submitted_on_date":
#                     format_utc_iso(
#                         portal_row[
#                             "SUBMITTED_ON"
#                         ]
#                     ),

#                 "closing_date":
#                     format_utc_iso(
#                         header[
#                             "CLOSING_DATE"
#                         ]
#                     ),

#                 "bid_value":
#                     0.0,

#                 "currency":
#                     header["CURRENCY"]
#                     or "INR",

#                 "payment_mode":
#                     header["PAYMENT_MODE"]
#                     or "-",

#                 "payment_term":
#                     header["PAYMENT_TERM"]
#                     or "-",

#                 "delivery_mode":
#                     header["DELIVERY_MODE"]
#                     or "-",

#                 "delivery_term":
#                     header["DELIVERY_TERM"]
#                     or "-",

#                 "delivery_date":
#                     format_utc_iso(
#                         header[
#                             "EXPECTED_DELIVERY_DATE"
#                         ]
#                     )
#             })

#         # ====================================================
#         # STEP 4
#         # ====================================================
#         for item in result:

#             try:

#                 cur.execute(f"""
#                     SELECT

#                         ISNULL(
#                             SUM(RL.LINEAMOUNT),
#                             0
#                         )

#                     FROM {SCHEMA}.D365_PURCHRFQLINE PL
#                     WITH (NOLOCK)

#                     INNER JOIN {SCHEMA}.D365_PURCHRFQREPLYLINE RL
#                     WITH (NOLOCK)

#                         ON RL.RFQLINERECID = PL.RECID
#                        AND RL.RFQID = PL.RFQID

#                     WHERE PL.RFQID = ?
#                       AND PL.STATUS < 3
#                 """, (item["rfq_id"],))

#                 item["bid_value"] = float(
#                     cur.fetchone()[0] or 0
#                 )

#             except Exception as e:

#                 print(
#                     f"[BID ERROR]: {e}"
#                 )

#                 item["bid_value"] = 0.0

#         return result
# # ============================================================
# # SUBMITTED RFQ DETAIL
# # ============================================================
# def fetch_submitted_rfq_detail(
#     rfq_id: str,
#     vendor_account: str
# ) -> Dict[str, Any]:

#     approved_items = _get_approved_items(
#         vendor_account
#     )

#     # ========================================================
#     # STEP 1
#     # ========================================================
#     with get_connection() as conn:

#         cur = conn.cursor()

#         cur.execute(f"""
#             SELECT TOP 1

#                 RFQID,
#                 RFQCASEID

#             FROM {RFQ_REPLIES_TABLE}
#             WITH (NOLOCK)

#             WHERE UPPER(RFQID) = UPPER(?)

#               AND UPPER(VENDORACCOUNT)
#                     = UPPER(?)
#         """, (rfq_id, vendor_account))

#         row = cur.fetchone()

#         if not row:

#             return {
#                 "success": False,
#                 "message": "RFQ not found"
#             }

#         rfq_id = str(row[0]).strip()

#         rfq_case_id = (

#             str(row[1]).strip()

#             if row[1]

#             else None
#         )

#     valid_payload = _get_valid_payload_items(
#         rfq_id,
#         vendor_account
#     )

#     # ========================================================
#     # STEP 2
#     # ========================================================
#     with get_connection() as conn:

#         cur = conn.cursor()

#         cur.execute(f"""
#             SELECT TOP 1

#                 RT.RFQID,

#                 RT.CURRENCYCODE,

#                 RT.DELIVERYDATE
#                     AS REPLY_DELIVERY_DATE,

#                 RT.DLVMODE
#                     AS REPLY_DELIVERY_MODE,

#                 RT.DLVTERM
#                     AS REPLY_DELIVERY_TERM,

#                 RT.PAYMENT
#                     AS REPLY_PAYMENT_TERM,

#                 RT.VENDREF,

#                 RT.TOTALSCORE,

#                 RT.RANK,

#                 RT.VALIDFROM,

#                 RT.VALIDTO,

#                 RT.VALIDITYDATESTART,

#                 RT.VALIDITYDATEEND,

#                 RT.REPLYPROGRESSSTATUS,

#                 RT.HIQ_COMMENTS
#                     AS REMARKS,

#                 T.RFQCASEID
#                     AS RFQCASEID,

#                 L.EXPIRYDATETIME
#                     AS CLOSING_DATE,

#                 L.CREATEDDATETIME
#                     AS ISSUE_DATE,

#                 L.DELIVERYDATE
#                     AS EXPECTED_DELIVERY_DATE,

#                 L.NAME
#                     AS DOCUMENT_TITLE,

#                 PM.NAME
#                     AS PAYMENT_MODE,

#                 PT.DESCRIPTION
#                     AS PAYMENT_TERM,

#                 DM.TXT
#                     AS DELIVERY_MODE,

#                 DT.TXT
#                     AS DELIVERY_TERM,

#                 T.HIQ_TERMSANDCONDITIONS

#             FROM {SCHEMA}.D365_PURCHRFQREPLYTABLE RT
#             WITH (NOLOCK)

#             INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T
#             WITH (NOLOCK)

#                 ON T.RFQID = RT.RFQID
#                AND T.VENDACCOUNT = ?

#             LEFT JOIN {SCHEMA}.D365_PURCHRFQCASETABLE L
#             WITH (NOLOCK)

#                 ON L.RFQCASEID = T.RFQCASEID

#             LEFT JOIN {SCHEMA}.D365_PAYMMODETABLE PM
#             WITH (NOLOCK)

#                 ON L.PAYMMODE = PM.PAYMMODE

#             LEFT JOIN {SCHEMA}.D365_PAYMTERM PT
#             WITH (NOLOCK)

#                 ON L.PAYMENT = PT.PAYMTERMID

#             LEFT JOIN {SCHEMA}.D365_DLVMODE DM
#             WITH (NOLOCK)

#                 ON L.DLVMODE = DM.CODE

#             LEFT JOIN {SCHEMA}.D365_DLVTERM DT
#             WITH (NOLOCK)

#                 ON L.DLVTERM = DT.CODE

#             WHERE RT.RFQID = ?
#         """, (vendor_account, rfq_id))

#         header_row = cur.fetchone()

#         if not header_row:

#             return {
#                 "success": False,
#                 "message": "RFQ not found"
#             }

#         cols = [
#             c[0]
#             for c in cur.description
#         ]

#         header = dict(zip(cols, header_row))

#         # ====================================================
#         # STEP 3
#         # ====================================================
#         lines = []

#         if approved_items:

#             placeholders = ",".join(
#                 ["?"] * len(approved_items)
#             )

#             cur.execute(f"""
#                 SELECT

#                     PL.LINENUM,

#                     PL.ITEMID,

#                     IT.NAME
#                         AS ITEM_NAME,

#                     PL.QTYORDERED,

#                     PL.PURCHUNIT,

#                     RL.PURCHPRICE,

#                     RL.LINEAMOUNT,

#                     RL.LINEDISC,

#                     RL.LINEPERCENT,

#                     RL.DELIVERYDATE
#                         AS VENDOR_DELIVERY_DATE,

#                     RL.LEADTIME,

#                     RL.HIQ_COMMENTS
#                         AS VENDOR_COMMENTS,

#                     RL.VALIDFROM,

#                     RL.VALIDTO,

#                     RL.EXTERNALITEMID,

#                     RL.MAXIMUMRETAILPRICE_IN
#                         AS MRP,

#                     PL.HIQ_TARGETPRICE,

#                     PL.HIQ_COMMENTS
#                         AS COMMENTS,

#                     PL.CURRENCYCODE,

#                     PL.STATUS,

#                     PL.DELIVERYDATE
#                         AS RFQ_DELIVERY_DATE

#                 FROM {SCHEMA}.D365_PURCHRFQLINE PL
#                 WITH (NOLOCK)

#                 LEFT {SCHEMA}.JOIN D365_PURCHRFQREPLYLINE RL
#                 WITH (NOLOCK)

#                     ON RL.RFQLINERECID = PL.RECID
#                    AND RL.RFQID = PL.RFQID

#                 LEFT JOIN {SCHEMA}.D365_INVENTTABLE IT
#                 WITH (NOLOCK)

#                     ON IT.ITEMID = PL.ITEMID

#                 WHERE PL.RFQID = ?

#                   AND PL.STATUS < 3

#                   AND PL.ITEMID IN ({placeholders})

#                 ORDER BY PL.LINENUM
#             """, [rfq_id] + approved_items)

#             rows = cur.fetchall()

#             cols = [
#                 c[0]
#                 for c in cur.description
#             ]

#             for r in rows:

#                 data = dict(zip(cols, r))

#                 line_num = int(
#                     data["LINENUM"]
#                 )

#                 item_id = str(
#                     data["ITEMID"]
#                 ).strip().upper()

#                 if valid_payload and (
#                     line_num,
#                     item_id
#                 ) not in valid_payload:
#                     continue

#                 lines.append({

#                     "line_num":
#                         line_num,

#                     "item_id":
#                         data["ITEMID"],

#                     "item_name":
#                         data["ITEM_NAME"]
#                         or "-",

#                     "external_item_id":
#                         data[
#                             "EXTERNALITEMID"
#                         ] or "-",

#                     "quantity":
#                         float(
#                             data[
#                                 "QTYORDERED"
#                             ] or 0
#                         ),

#                     "uom":
#                         data["PURCHUNIT"]
#                         or "-",

#                     "unit_price":

#                         float(
#                             data[
#                                 "PURCHPRICE"
#                             ]
#                         )

#                         if data[
#                             "PURCHPRICE"
#                         ] is not None

#                         else None,

#                     "net_amount":

#                         float(
#                             data[
#                                 "LINEAMOUNT"
#                             ]
#                         )

#                         if data[
#                             "LINEAMOUNT"
#                         ] is not None

#                         else None,

#                     "line_disc":
#                         float(
#                             data[
#                                 "LINEDISC"
#                             ] or 0
#                         ),

#                     "line_percent":
#                         float(
#                             data[
#                                 "LINEPERCENT"
#                             ] or 0
#                         ),

#                     "mrp":
#                         float(
#                             data["MRP"] or 0
#                         ),

#                     "target_price":
#                         float(
#                             data[
#                                 "HIQ_TARGETPRICE"
#                             ] or 0
#                         ),

#                     "comments":
#                         data["COMMENTS"]
#                         or " ",

#                     "lead_time":
#                         data["LEADTIME"]
#                         or 0,

#                     "vendor_comments":
#                         data[
#                             "VENDOR_COMMENTS"
#                         ] or " ",

#                     "currency":
#                         data[
#                             "CURRENCYCODE"
#                         ] or "INR",

#                     "line_valid_from":
#                         format_utc_iso(
#                             data[
#                                 "VALIDFROM"
#                             ]
#                         ),

#                     "line_valid_to":
#                         format_utc_iso(
#                             data[
#                                 "VALIDTO"
#                             ]
#                         ),

#                     "rfq_delivery_date":
#                         format_utc_iso(
#                             data[
#                                 "RFQ_DELIVERY_DATE"
#                             ]
#                         ),

#                     "vendor_delivery_date":
#                         format_utc_iso(
#                             data[
#                                 "VENDOR_DELIVERY_DATE"
#                             ]
#                         ),

#                     "hiq_decision":
#                         "Under Review"
#                 })

#     return {

#         "success": True,

#         "data": {

#             "rfq_id":
#                 rfq_id,

#             "rfq_case_id":
#                 rfq_case_id
#                 or header["RFQCASEID"],

#             "delivery_date":
#                 format_utc_iso(
#                     header[
#                         "EXPECTED_DELIVERY_DATE"
#                     ]
#                 ),

#             "payment_term":
#                 header[
#                     "PAYMENT_TERM"
#                 ] or "-",

#             "delivery_term":
#                 header[
#                     "DELIVERY_TERM"
#                 ] or "-",

#             "delivery_mode":
#                 header[
#                     "DELIVERY_MODE"
#                 ] or "-",

#             "payment_mode":
#                 header[
#                     "PAYMENT_MODE"
#                 ] or "-",

#             "issue_date":
#                 format_utc_iso(
#                     header["ISSUE_DATE"]
#                 ),

#             "closing_date":
#                 format_utc_iso(
#                     header[
#                         "CLOSING_DATE"
#                     ]
#                 ),

#             "document_title":
#                 header[
#                     "DOCUMENT_TITLE"
#                 ],

#             "termsandconditions":
#                 header[
#                     "HIQ_TERMSANDCONDITIONS"
#                 ],

#             "currency":
#                 header[
#                     "CURRENCYCODE"
#                 ] or "INR",

#             "reply_delivery_date":
#                 format_utc_iso(
#                     header[
#                         "REPLY_DELIVERY_DATE"
#                     ]
#                 ),

#             "reply_delivery_mode":
#                 header[
#                     "REPLY_DELIVERY_MODE"
#                 ] or "-",

#             "reply_delivery_term":
#                 header[
#                     "REPLY_DELIVERY_TERM"
#                 ] or "-",

#             "reply_payment_term":
#                 header[
#                     "REPLY_PAYMENT_TERM"
#                 ] or "-",

#             "vendor_ref":
#                 header["VENDREF"]
#                 or "-",

#             "valid_from":
#                 format_utc_iso(
#                     header["VALIDFROM"]
#                 ),

#             "valid_to":
#                 format_utc_iso(
#                     header["VALIDTO"]
#                 ),

#             "validity_date_start":
#                 format_utc_iso(
#                     header[
#                         "VALIDITYDATESTART"
#                     ]
#                 ),

#             "validity_date_end":
#                 format_utc_iso(
#                     header[
#                         "VALIDITYDATEEND"
#                     ]
#                 ),

#             "total_score":
#                 header[
#                     "TOTALSCORE"
#                 ] or 0,

#             "rank":
#                 header["RANK"] or 0,

#             "reply_progress_status":
#                 header[
#                     "REPLYPROGRESSSTATUS"
#                 ] or 0,

#             "remarks":
#                 header["REMARKS"],

#             "line_items":
#                 lines
#         }
#     }
# # from app.db.base import get_connection, get_connection
# # from app.utils.date_utils import format_utc_iso
# # from typing import List, Dict, Any, Optional, Set, Tuple
# # import json
# # from app.core.config import settings

# # SCHEMA = settings.DB_SCHEMA

# # RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VENDORRFQREPLIES"

# # # ============================================================
# # # APPROVED ITEMS — D365 DB
# # # ============================================================
# # def _get_approved_items(vendor_account: str) -> List[str]:
# #     try:
# #         with get_connection() as conn:
# #             cur = conn.cursor()
# #             cur.execute("""
# #                 SELECT LTRIM(RTRIM(ITEMID)) AS ITEMID
# #                 FROM PDSAPPROVEDVENDORLIST WITH (NOLOCK)
# #                 WHERE PDSAPPROVEDVENDOR = ?
# #                   AND DATAAREAID = 'hi-q'
# #                   AND VALIDFROM <= GETUTCDATE()
# #                   AND VALIDTO >= GETUTCDATE()
# #             """, (vendor_account,))

# #             return [
# #                 str(r[0]).strip().upper()
# #                 for r in cur.fetchall()
# #                 if r[0]
# #             ]

# #     except Exception as e:
# #         print(f"[APPROVED ERROR]: {e}")
# #         return []


# # # ============================================================
# # # PAYLOAD FILTER — PORTAL DB
# # # ============================================================
# # def _get_valid_payload_items(
# #     rfq_id: str,
# #     vendor_account: str
# # ) -> Optional[Set[Tuple[int, str]]]:

# #     try:
# #         with get_connection() as conn:
# #             cur = conn.cursor()

# #             cur.execute(f"""
# #                 SELECT TOP 1 PAYLOADJSON
# #                 FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)
# #                 WHERE UPPER(RFQID) = UPPER(?)
# #                   AND UPPER(VENDORACCOUNT) = UPPER(?)
# #                 ORDER BY ID DESC
# #             """, (rfq_id, vendor_account))

# #             row = cur.fetchone()

# #         if not row or not row[0]:
# #             return None

# #         payload = json.loads(row[0])
# #         items = payload.get("Item", [])

# #         has_line_status = any("lineStatus" in i for i in items)

# #         if not has_line_status:
# #             return None

# #         valid = set()

# #         for i in items:
# #             if str(i.get("lineStatus")).lower() == "true":
# #                 item_number = i.get("itemNumber")
# #                 line_number = i.get("lineNumber")

# #                 if item_number and line_number is not None:
# #                     valid.add((
# #                         int(line_number),
# #                         str(item_number).strip().upper()
# #                     ))

# #         return valid

# #     except Exception as e:
# #         print(f"[PAYLOAD ERROR]: {e}")
# #         return None


# # # ============================================================
# # # SUBMITTED RFQ LIST
# # # ============================================================
# # def fetch_submitted_rfqs(vendor_account: str) -> List[Dict[str, Any]]:

# #     approved_items = _get_approved_items(vendor_account)

# #     if not approved_items:
# #         return []

# #     # ========================================================
# #     # STEP 1 — GET SUBMITTED RFQS FROM PORTAL DB
# #     # ========================================================
# #     with get_connection() as conn:
# #         cur = conn.cursor()

# #         cur.execute(f"""
# #             SELECT
# #                 RFQCASEID,
# #                 RFQID,
# #                 MAX(SENDTOD365AT) AS SUBMITTED_ON
# #             FROM {RFQ_REPLIES_TABLE} WITH (NOLOCK)
# #             WHERE VENDORACCOUNT = ?
# #               AND SUBMISSIONSTATUS = 1
# #             GROUP BY
# #                 RFQCASEID,
# #                 RFQID
# #             ORDER BY MAX(SENDTOD365AT) DESC
# #         """, (vendor_account,))

# #         portal_rows = cur.fetchall()

# #         if not portal_rows:
# #             return []

# #         portal_cols = [c[0] for c in cur.description]

# #         submitted_rows = [
# #             dict(zip(portal_cols, r))
# #             for r in portal_rows
# #         ]

# #     rfq_ids = [
# #         r["RFQID"]
# #         for r in submitted_rows
# #         if r["RFQID"]
# #     ]

# #     if not rfq_ids:
# #         return []

# #     submitted_map = {
# #         (r["RFQID"], vendor_account): r
# #         for r in submitted_rows
# #     }

# #     placeholders = ",".join(["?"] * len(rfq_ids))


# #     # ========================================================
# #     # STEP 2 — GET HEADER/METADATA FROM D365 DB
# #     # ========================================================
# #     d365_header_query = f"""
# #         SELECT
# #             T.RFQID,
# #             T.VENDACCOUNT,
# #             T.RFQCASEID,

# #             L.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,
# #             L.EXPIRYDATETIME AS CLOSING_DATE,

# #             (
# #                 SELECT TOP 1 CURRENCYCODE
# #                 FROM PURCHRFQREPLYTABLE WITH (NOLOCK)
# #                 WHERE RFQID = T.RFQID
# #                   AND DATAAREAID = 'hi-q'
# #             ) AS CURRENCY,

# #             PM.NAME AS PAYMENT_MODE,
# #             PT.DESCRIPTION AS PAYMENT_TERM,
# #             DM.TXT AS DELIVERY_MODE,
# #             DT.TXT AS DELIVERY_TERM

# #         FROM PurchRFQTable T WITH (NOLOCK)

# #         LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
# #             ON L.RFQCASEID = T.RFQCASEID

# #         LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# #             ON L.PAYMMODE = PM.PAYMMODE

# #         LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# #             ON L.PAYMENT = PT.PAYMTERMID

# #         LEFT JOIN DLVMODE DM WITH (NOLOCK)
# #             ON L.DLVMODE = DM.CODE

# #         LEFT JOIN DLVTERM DT WITH (NOLOCK)
# #             ON L.DLVTERM = DT.CODE

# #         WHERE T.VENDACCOUNT = ?
# #           AND T.RFQID IN ({placeholders})
# #     """

# #     with get_connection() as conn:
# #         cur = conn.cursor()

# #         cur.execute(
# #             d365_header_query,
# #             [vendor_account] + rfq_ids
# #         )

# #         header_rows = cur.fetchall()
# #         header_cols = [c[0] for c in cur.description]

# #         header_data = [
# #             dict(zip(header_cols, r))
# #             for r in header_rows
# #         ]

# #         header_map = {
# #             (h["RFQID"], h["VENDACCOUNT"]): h
# #             for h in header_data
# #         }


# #         # ====================================================
# #         # STEP 3 — FILTER VALID SUBMITTED RFQS
# #         # ====================================================
# #         result = []

# #         for portal_row in submitted_rows:
# #             rfq_id = portal_row["RFQID"]

# #             header = header_map.get((rfq_id, vendor_account))

# #             if not header:
# #                 continue

# #             valid_items = _get_valid_payload_items(
# #                 rfq_id,
# #                 vendor_account
# #             )

# #             if not valid_items:
# #                 continue

# #             cur.execute("""
# #                 SELECT
# #                     LINENUM,
# #                     LTRIM(RTRIM(ITEMID)) AS ITEMID,
# #                     STATUS
# #                 FROM PURCHRFQLINE WITH (NOLOCK)
# #                 WHERE RFQID = ?
# #                   AND DATAAREAID = 'hi-q'
# #             """, (rfq_id,))

# #             lines = cur.fetchall()

# #             is_submitted = False

# #             for l in lines:
# #                 line_num = int(l[0])
# #                 item = str(l[1]).strip().upper()
# #                 status = l[2]

# #                 if (line_num, item) in valid_items:
# #                     if status < 3:
# #                         is_submitted = True
# #                         break

# #             if not is_submitted:
# #                 continue

# #             result.append({
# #                 "rfq_id": rfq_id,
# #                 "rfq_case_id": portal_row["RFQCASEID"],
# #                 "submitted_on_date": format_utc_iso(portal_row["SUBMITTED_ON"]),
# #                 "closing_date": format_utc_iso(header["CLOSING_DATE"]),
# #                 "bid_value": 0.0,
# #                 "currency": header["CURRENCY"] or "INR",
# #                 "payment_mode": header["PAYMENT_MODE"] or "-",
# #                 "payment_term": header["PAYMENT_TERM"] or "-",
# #                 "delivery_mode": header["DELIVERY_MODE"] or "-",
# #                 "delivery_term": header["DELIVERY_TERM"] or "-",
# #                 "delivery_date": format_utc_iso(header["EXPECTED_DELIVERY_DATE"])
# #             })


# #         # ====================================================
# #         # STEP 4 — CALCULATE BID VALUE FROM D365 DB
# #         # ====================================================
# #         for item in result:
# #             try:
# #                 cur.execute("""
# #                     SELECT ISNULL(SUM(RL.LINEAMOUNT), 0)
# #                     FROM PURCHRFQLINE PL WITH (NOLOCK)

# #                     INNER JOIN PURCHRFQREPLYLINE RL WITH (NOLOCK)
# #                         ON RL.RFQLINERECID = PL.RECID
# #                         AND RL.RFQID = PL.RFQID
# #                         AND RL.DATAAREAID = 'hi-q'

# #                     WHERE PL.RFQID = ?
# #                       AND PL.DATAAREAID = 'hi-q'
# #                       AND PL.STATUS < 3
# #                 """, (item["rfq_id"],))

# #                 item["bid_value"] = float(cur.fetchone()[0] or 0)

# #             except Exception as e:
# #                 print(f"[BID ERROR]: {e}")
# #                 item["bid_value"] = 0.0

# #         return result


# # # ============================================================
# # # SUBMITTED RFQ DETAIL
# # # ============================================================
# # def fetch_submitted_rfq_detail(
# #     rfq_id: str,
# #     vendor_account: str
# # ) -> Dict[str, Any]:

# #     approved_items = _get_approved_items(vendor_account)

# #     # ========================================================
# #     # STEP 1 — VALIDATE RFQ FROM PORTAL DB
# #     # ========================================================
# #     with get_connection() as conn:
# #         cur = conn.cursor()

# #         cur.execute(f"""
# #             SELECT TOP 1
# #                 RFQID,
# #                 RFQCASEID
# #             FROM {RFQ_REPLIES_TABLE}  WITH (NOLOCK)
# #             WHERE UPPER(RFQID) = UPPER(?)
# #               AND UPPER(VENDORACCOUNT) = UPPER(?)
# #         """, (rfq_id, vendor_account))

# #         row = cur.fetchone()

# #         if not row:
# #             return {
# #                 "success": False,
# #                 "message": "RFQ not found"
# #             }

# #         rfq_id = str(row[0]).strip()
# #         rfq_case_id = str(row[1]).strip() if row[1] else None


# #     valid_payload = _get_valid_payload_items(
# #         rfq_id,
# #         vendor_account
# #     )


# #     # ========================================================
# #     # STEP 2 — HEADER FROM D365 DB
# #     # ========================================================
# #     with get_connection() as conn:
# #         cur = conn.cursor()

# #         cur.execute("""
# #             SELECT TOP 1
# #                 RT.RFQID,
# #                 RT.CURRENCYCODE,
# #                 RT.DELIVERYDATE AS REPLY_DELIVERY_DATE,
# #                 RT.DLVMODE AS REPLY_DELIVERY_MODE,
# #                 RT.DLVTERM AS REPLY_DELIVERY_TERM,
# #                 RT.PAYMENT AS REPLY_PAYMENT_TERM,
# #                 RT.VENDREF,
# #                 RT.TOTALSCORE,
# #                 RT.RANK,
# #                 RT.VALIDFROM,
# #                 RT.VALIDTO,
# #                 RT.VALIDITYDATESTART,
# #                 RT.VALIDITYDATEEND,
# #                 RT.REPLYPROGRESSSTATUS,
# #                 RT.HIQ_COMMENTS AS REMARKS,

# #                 T.RFQCASEID AS RFQCASEID,

# #                 L.EXPIRYDATETIME AS CLOSING_DATE,
# #                 L.CREATEDDATETIME AS ISSUE_DATE,
# #                 L.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,
# #                 L.NAME AS DOCUMENT_TITLE,

# #                 PM.NAME AS PAYMENT_MODE,
# #                 PT.DESCRIPTION AS PAYMENT_TERM,
# #                 DM.TXT AS DELIVERY_MODE,
# #                 DT.TXT AS DELIVERY_TERM,

# #                 T.HIQ_TERMSANDCONDITIONS

# #             FROM PURCHRFQREPLYTABLE RT WITH (NOLOCK)

# #             INNER JOIN PurchRFQTable T WITH (NOLOCK)
# #                 ON T.RFQID = RT.RFQID
# #                 AND T.VENDACCOUNT = ?

# #             LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
# #                 ON L.RFQCASEID = T.RFQCASEID

# #             LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# #                 ON L.PAYMMODE = PM.PAYMMODE

# #             LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# #                 ON L.PAYMENT = PT.PAYMTERMID

# #             LEFT JOIN DLVMODE DM WITH (NOLOCK)
# #                 ON L.DLVMODE = DM.CODE

# #             LEFT JOIN DLVTERM DT WITH (NOLOCK)
# #                 ON L.DLVTERM = DT.CODE

# #             WHERE RT.RFQID = ?
# #               AND RT.DATAAREAID = 'hi-q'
# #         """, (vendor_account, rfq_id))

# #         header_row = cur.fetchone()

# #         if not header_row:
# #             return {
# #                 "success": False,
# #                 "message": "RFQ not found"
# #             }

# #         cols = [c[0] for c in cur.description]
# #         header = dict(zip(cols, header_row))


# #         # ====================================================
# #         # STEP 3 — LINE ITEMS FROM D365 DB
# #         # ====================================================
# #         lines = []

# #         if approved_items:
# #             placeholders = ",".join(["?"] * len(approved_items))

# #             cur.execute(f"""
# #                 SELECT
# #                     PL.LINENUM,
# #                     LTRIM(RTRIM(PL.ITEMID)) AS ITEMID,
# #                     IT.NAMEALIAS AS ITEM_NAME,
# #                     PL.QTYORDERED,
# #                     PL.PURCHUNIT,

# #                     RL.PURCHPRICE,
# #                     RL.LINEAMOUNT,
# #                     RL.LINEDISC,
# #                     RL.LINEPERCENT,
# #                     RL.DELIVERYDATE AS VENDOR_DELIVERY_DATE,
# #                     RL.LEADTIME,
# #                     RL.HIQ_COMMENTS AS VENDOR_COMMENTS,
# #                     RL.VALIDFROM,
# #                     RL.VALIDTO,
# #                     RL.EXTERNALITEMID,
# #                     RL.MAXIMUMRETAILPRICE_IN AS MRP,

# #                     PL.HIQ_TARGETPRICE,
# #                     PL.HIQ_COMMENTS AS COMMENTS,
# #                     PL.CURRENCYCODE,
# #                     PL.STATUS,
# #                     PL.DELIVERYDATE AS RFQ_DELIVERY_DATE

# #                 FROM PURCHRFQLINE PL WITH (NOLOCK)

# #                 LEFT JOIN PURCHRFQREPLYLINE RL WITH (NOLOCK)
# #                     ON RL.RFQLINERECID = PL.RECID
# #                     AND RL.RFQID = PL.RFQID
# #                     AND RL.DATAAREAID = 'hi-q'

# #                 LEFT JOIN INVENTTABLE IT WITH (NOLOCK)
# #                     ON LTRIM(RTRIM(IT.ITEMID)) = LTRIM(RTRIM(PL.ITEMID))

# #                 WHERE PL.RFQID = ?
# #                   AND PL.DATAAREAID = 'hi-q'
# #                   AND PL.STATUS < 3
# #                   AND LTRIM(RTRIM(PL.ITEMID)) IN ({placeholders})

# #                 ORDER BY PL.LINENUM
# #             """, [rfq_id] + approved_items)

# #             rows = cur.fetchall()
# #             cols = [c[0] for c in cur.description]

# #             for r in rows:
# #                 data = dict(zip(cols, r))

# #                 line_num = int(data["LINENUM"])
# #                 item_id = str(data["ITEMID"]).strip().upper()

# #                 if valid_payload and (line_num, item_id) not in valid_payload:
# #                     continue

# #                 lines.append({
# #                     "line_num": line_num,
# #                     "item_id": data["ITEMID"],
# #                     "item_name": data["ITEM_NAME"] or "-",
# #                     "external_item_id": data["EXTERNALITEMID"] or "-",
# #                     "quantity": float(data["QTYORDERED"] or 0),
# #                     "uom": data["PURCHUNIT"] or "-",

# #                     "unit_price": float(data["PURCHPRICE"])
# #                     if data["PURCHPRICE"] is not None else None,

# #                     "net_amount": float(data["LINEAMOUNT"])
# #                     if data["LINEAMOUNT"] is not None else None,

# #                     "line_disc": float(data["LINEDISC"] or 0),
# #                     "line_percent": float(data["LINEPERCENT"] or 0),
# #                     "mrp": float(data["MRP"] or 0),

# #                     "target_price": float(data["HIQ_TARGETPRICE"] or 0),
# #                     "comments": data["COMMENTS"] or " ",

# #                     "lead_time": data["LEADTIME"] or 0,
# #                     "vendor_comments": data["VENDOR_COMMENTS"] or " ",

# #                     "currency": data["CURRENCYCODE"] or "INR",

# #                     "line_valida_from": format_utc_iso(data["VALIDFROM"]),
# #                     "line_valid_to": format_utc_iso(data["VALIDTO"]),
# #                     "rfq_delivery_date": format_utc_iso(data["RFQ_DELIVERY_DATE"]),
# #                     "vendor_delivery_date": format_utc_iso(data["VENDOR_DELIVERY_DATE"]),
# #                     "hiq_decision": "Under Review"
# #                 })


# #     return {
# #         "success": True,
# #         "data": {
# #             "rfq_id": rfq_id,
# #             "rfq_case_id": rfq_case_id or header["RFQCASEID"],
# #             "delivery_date": format_utc_iso(header["EXPECTED_DELIVERY_DATE"]),
# #             "payment_term": header["PAYMENT_TERM"] or "-",
# #             "delivery_term": header["DELIVERY_TERM"] or "-",
# #             "delivery_mode": header["DELIVERY_MODE"] or "-",
# #             "payment_mode": header["PAYMENT_MODE"] or "-",
# #             "issue_date": format_utc_iso(header["ISSUE_DATE"]),
# #             "closing_date": format_utc_iso(header["CLOSING_DATE"]),
# #             "document_title": header["DOCUMENT_TITLE"],
# #             "termsandconditions": header["HIQ_TERMSANDCONDITIONS"],
# #             "currency": header["CURRENCYCODE"] or "INR",
# #             "reply_delivery_date": format_utc_iso(header["REPLY_DELIVERY_DATE"]),
# #             "reply_delivery_mode": header["REPLY_DELIVERY_MODE"] or "-",
# #             "reply_delivery_term": header["REPLY_DELIVERY_TERM"] or "-",
# #             "reply_payment_term": header["REPLY_PAYMENT_TERM"] or "-",
# #             "vendor_ref": header["VENDREF"] or "-",
# #             "valid_from": format_utc_iso(header["VALIDFROM"]),
# #             "valid_to": format_utc_iso(header["VALIDTO"]),
# #             "validity_date_start": format_utc_iso(header["VALIDITYDATESTART"]),
# #             "validity_date_end": format_utc_iso(header["VALIDITYDATEEND"]),
# #             "total_score": header["TOTALSCORE"] or 0,
# #             "rank": header["RANK"] or 0,
# #             "reply_progress_status": header["REPLYPROGRESSSTATUS"] or 0,
# #             "remarks": header["REMARKS"],
# #             "line_items": lines
# #         }
# #     }


# # # from app.db.base import get_connection, get_connection
# # # from app.utils.date_utils import format_date,format_utc_iso
# # # from typing import List, Dict, Any, Optional, Set
# # # import json


# # # # ============================================================
# # # # APPROVED ITEMS
# # # # ============================================================
# # # def _get_approved_items(vendor_account: str) -> List[str]:
# # #     try:
# # #         with get_connection() as conn:
# # #             cur = conn.cursor()
# # #             cur.execute("""
# # #                 SELECT LTRIM(RTRIM(ITEMID)) AS ITEMID
# # #                 FROM PDSAPPROVEDVENDORLIST WITH (NOLOCK)
# # #                 WHERE PDSAPPROVEDVENDOR = ?
# # #                   AND DATAAREAID = 'hi-q'
# # #                   AND VALIDFROM <= GETUTCDATE()
# # #                   AND VALIDTO >= GETUTCDATE()
# # #             """, (vendor_account,))
# # #             return [str(r[0]).strip().upper() for r in cur.fetchall() if r[0]]
# # #     except Exception as e:
# # #         print(f"[APPROVED ERROR]: {e}")
# # #         return []


# # # # ============================================================
# # # # PAYLOAD FILTER
# # # # ============================================================
# # # def _get_valid_payload_items(rfq_id: str, vendor_account: str, cur) -> Optional[Set[tuple]]:
# # #     try:
# # #         cur.execute("""
# # #             SELECT TOP 1 PAYLOAD_JSON
# # #             FROM RFQ_REPLIES_TABLE  WITH (NOLOCK)
# # #             WHERE UPPER(RFQ_ID)=UPPER(?) AND UPPER(VENDOR_ACCOUNT)=UPPER(?)
# # #             ORDER BY ID DESC
# # #         """, (rfq_id, vendor_account))

# # #         row = cur.fetchone()
# # #         if not row or not row[0]:
# # #             return None

# # #         payload = json.loads(row[0])
# # #         items = payload.get("Item", [])

# # #         has_line_status = any("lineStatus" in i for i in items)

# # #         if not has_line_status:
# # #             return None  # OLD RFQ

# # #         valid = set()
# # #         for i in items:
# # #             if str(i.get("lineStatus")).lower() == "true":
# # #                 item_number = i.get("itemNumber")
# # #                 line_number = i.get("lineNumber")

# # #                 if item_number and line_number is not None:
# # #                     valid.add((int(line_number), str(item_number).strip().upper()))

# # #         return valid

# # #     except:
# # #         return None


# # # def fetch_submitted_rfqs(vendor_account: str) -> List[Dict[str, Any]]:

# # #     approved_items = _get_approved_items(vendor_account)

# # #     if not approved_items:
# # #         return []

# # #     with get_connection() as conn:
# # #         cur = conn.cursor()

# # #         cur.execute("""
# # #             SELECT DISTINCT
# # #                 R.RFQ_CASE_ID,
# # #                 R.RFQ_ID,
# # #                 L.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,
# # #                 L.EXPIRYDATETIME AS CLOSING_DATE,
# # #                 MAX(R.SEND_TO_D365_AT) AS SUBMITTED_ON,

# # #                 (
# # #                     SELECT TOP 1 CURRENCYCODE
# # #                     FROM PURCHRFQREPLYTABLE WITH (NOLOCK)
# # #                     WHERE RFQID = R.RFQ_ID
# # #                       AND DATAAREAID = 'hi-q'
# # #                 ) AS CURRENCY,

# # #                 PM.NAME AS PAYMENT_MODE,
# # #                 PT.DESCRIPTION AS PAYMENT_TERM,
# # #                 DM.TXT AS DELIVERY_MODE,
# # #                 DT.TXT AS DELIVERY_TERM

# # #             FROM RFQ_REPLIES_TABLE  R WITH (NOLOCK)

# # #             LEFT JOIN PurchRFQCaseTable L WITH (NOLOCK)
# # #                 ON L.RFQCASEID = R.RFQ_CASE_ID

# # #             LEFT JOIN VENDPAYMMODETABLE PM WITH (NOLOCK)
# # #                 ON L.PAYMMODE = PM.PAYMMODE

# # #             LEFT JOIN PAYMTERM PT WITH (NOLOCK)
# # #                 ON L.PAYMENT = PT.PAYMTERMID

# # #             LEFT JOIN DLVMODE DM WITH (NOLOCK)
# # #                 ON L.DLVMODE = DM.CODE

# # #             LEFT JOIN DLVTERM DT WITH (NOLOCK)
# # #                 ON L.DLVTERM = DT.CODE

# # #             WHERE R.VENDOR_ACCOUNT = ?
# # #               AND R.SUBMISSION_STATUS = 1

# # #             GROUP BY
# # #                 R.RFQ_CASE_ID,
# # #                 R.RFQ_ID,
# # #                 PM.NAME,
# # #                 PT.DESCRIPTION,
# # #                 L.DELIVERYDATE,
# # #                 L.EXPIRYDATETIME,
# # #                 DM.TXT,
# # #                 DT.TXT

# # #             ORDER BY MAX(R.SEND_TO_D365_AT) DESC
# # #         """, (vendor_account,))

# # #         rows = cur.fetchall()
# # #         if not rows:
# # #             return []

# # #         cols = [c[0] for c in cur.description]
# # #         result = []

# # #         for row in rows:
# # #             data = dict(zip(cols, row))
# # #             rfq_id = data["RFQ_ID"]

# # #             # STEP 1: Get active payload items
# # #             valid_items = _get_valid_payload_items(rfq_id, vendor_account, cur)

# # #             if not valid_items:
# # #                 continue

# # #             # STEP 2: Get D365 line statuses
# # #             cur.execute("""
# # #                 SELECT LINENUM, LTRIM(RTRIM(ITEMID)) AS ITEMID, STATUS
# # #                 FROM PURCHRFQLINE WITH (NOLOCK)
# # #                 WHERE RFQID = ?
# # #                   AND DATAAREAID = 'hi-q'
# # #             """, (rfq_id,))

# # #             lines = cur.fetchall()

# # #             is_submitted = False

# # #             for l in lines:
# # #                 line_num = int(l[0])
# # #                 item = str(l[1]).strip().upper()
# # #                 status = l[2]

# # #                 # Only check ACTIVE payload items (match by lineNumber + itemNumber)
# # #                 if (line_num, item) in valid_items:
# # #                     if status < 3:
# # #                         is_submitted = True
# # #                         break

# # #             # REMOVE COMPLETED RFQs
# # #             if not is_submitted:
# # #                 continue

# # #             result.append({
# # #                 "rfq_id": data["RFQ_ID"],
# # #                 "rfq_case_id": data["RFQ_CASE_ID"],
# # #                 "submitted_on_date": format_utc_iso(data["SUBMITTED_ON"]),
# # #                 "closing_date": format_utc_iso(data["CLOSING_DATE"]),
# # #                 "bid_value": 0.0,
# # #                 "currency": data["CURRENCY"] or "INR",
# # #                 "payment_mode": data["PAYMENT_MODE"] or "-",
# # #                 "payment_term": data["PAYMENT_TERM"] or "-",
# # #                 "delivery_mode": data["DELIVERY_MODE"] or "-",
# # #                 "delivery_term": data["DELIVERY_TERM"] or "-",
# # #                 "delivery_date": format_utc_iso(data["EXPECTED_DELIVERY_DATE"])
# # #             })

# # #         # STEP 3: Calculate bid_value (only for filtered RFQs)
# # #         for item in result:
# # #             try:
# # #                 cur.execute("""
# # #                     SELECT ISNULL(SUM(RL.LINEAMOUNT), 0)
# # #                     FROM PURCHRFQLINE PL WITH (NOLOCK)

# # #                     INNER JOIN PURCHRFQREPLYLINE RL WITH (NOLOCK)
# # #                         ON RL.RFQLINERECID = PL.RECID
# # #                         AND RL.RFQID = PL.RFQID
# # #                         AND RL.DATAAREAID = 'hi-q'

# # #                     WHERE PL.RFQID = ?
# # #                     AND PL.DATAAREAID = 'hi-q'
# # #                     AND PL.STATUS < 3
# # #                 """, (item["rfq_id"],))

# # #                 item["bid_value"] = float(cur.fetchone()[0] or 0)

# # #             except Exception as e:
# # #                 print(f"[BID ERROR]: {e}")
# # #                 item["bid_value"] = 0.0

# # #         return result


# # # # ============================================================
# # # # RFQ DETAIL
# # # # ============================================================
# # # def fetch_submitted_rfq_detail(rfq_id: str, vendor_account: str) -> Dict[str, Any]:

# # #     approved_items = _get_approved_items(vendor_account)

# # #     with get_connection() as conn:
# # #         cur = conn.cursor()

# # #         # Validate RFQ
# # #         cur.execute("""
# # #             SELECT TOP 1 RFQ_ID
# # #             FROM RFQ_REPLIES_TABLE  WITH (NOLOCK)
# # #             WHERE UPPER(RFQ_ID)=UPPER(?) AND UPPER(VENDOR_ACCOUNT)=UPPER(?)
# # #         """, (rfq_id, vendor_account))

# # #         row = cur.fetchone()
# # #         if not row:
# # #             return {"success": False, "message": "RFQ not found"}

# # #         rfq_id = str(row[0]).strip()

# # #         # HEADER
# # #         cur.execute("""
# # #             SELECT TOP 1
# # #                 RT.RFQID,
# # #                 RT.CURRENCYCODE,
# # #                 RT.DELIVERYDATE AS REPLY_DELIVERY_DATE,
# # #                 RT.DLVMODE AS REPLY_DELIVERY_MODE,
# # #                 RT.DLVTERM AS REPLY_DELIVERY_TERM,
# # #                 RT.PAYMENT AS REPLY_PAYMENT_TERM,
# # #                 RT.VENDREF,
# # #                 RT.TOTALSCORE,
# # #                 RT.RANK,
# # #                 RT.VALIDFROM,
# # #                 RT.VALIDTO,
# # #                 RT.VALIDITYDATESTART,
# # #                 RT.VALIDITYDATEEND,
# # #                 RT.REPLYPROGRESSSTATUS,
# # #                 RT.HIQ_COMMENTS AS REMARKS,

# # #                 R.RFQ_CASE_ID,
# # #                 L.EXPIRYDATETIME AS CLOSING_DATE,
# # #                 L.CREATEDDATETIME AS ISSUE_DATE,
# # #                 L.DELIVERYDATE AS EXPECTED_DELIVERY_DATE,
# # #                 L.NAME AS DOCUMENT_TITLE,

# # #                 PM.NAME AS PAYMENT_MODE,
# # #                 PT.DESCRIPTION AS PAYMENT_TERM,
# # #                 DM.TXT AS DELIVERY_MODE,
# # #                 DT.TXT AS DELIVERY_TERM,
# # #                 T.HIQ_TERMSANDCONDITIONS

# # #             FROM PURCHRFQREPLYTABLE RT

# # #             INNER JOIN RFQ_REPLIES_TABLE  R
# # #                 ON R.RFQ_ID = RT.RFQID AND R.VENDOR_ACCOUNT = ?

# # #             LEFT JOIN PurchRFQCaseTable L
# # #                 ON L.RFQCASEID = R.RFQ_CASE_ID

# # #             LEFT JOIN PurchRFQTable T
# # #                 ON T.RFQCASEID = L.RFQCASEID AND T.VENDACCOUNT = R.VENDOR_ACCOUNT

# # #             LEFT JOIN VENDPAYMMODETABLE PM ON L.PAYMMODE = PM.PAYMMODE
# # #             LEFT JOIN PAYMTERM PT ON L.PAYMENT = PT.PAYMTERMID
# # #             LEFT JOIN DLVMODE DM ON L.DLVMODE = DM.CODE
# # #             LEFT JOIN DLVTERM DT ON L.DLVTERM = DT.CODE

# # #             WHERE RT.RFQID = ? AND RT.DATAAREAID = 'hi-q'
# # #         """, (vendor_account, rfq_id))

# # #         header_row = cur.fetchone()
# # #         if not header_row:
# # #             return {"success": False, "message": "RFQ not found"}

# # #         cols = [c[0] for c in cur.description]
# # #         header = dict(zip(cols, header_row))

# # #         # =========================
# # #         # LINE ITEMS
# # #         # =========================
# # #         lines = []

# # #         if approved_items:
# # #             valid_payload = _get_valid_payload_items(rfq_id, vendor_account, cur)
# # #             placeholders = ",".join(["?" for _ in approved_items])

# # #             cur.execute(f"""
# # #                 SELECT
# # #                     PL.LINENUM,
# # #                     LTRIM(RTRIM(PL.ITEMID)) AS ITEMID,
# # #                     IT.NAMEALIAS AS ITEM_NAME,
# # #                     PL.QTYORDERED,
# # #                     PL.PURCHUNIT,

# # #                     RL.PURCHPRICE,
# # #                     RL.LINEAMOUNT,
# # #                     RL.LINEDISC,
# # #                     RL.LINEPERCENT,
# # #                     RL.DELIVERYDATE AS VENDOR_DELIVERY_DATE,
# # #                     RL.LEADTIME,
# # #                     RL.HIQ_COMMENTS AS VENDOR_COMMENTS,
# # #                     RL.VALIDFROM,
# # #                     RL.VALIDTO,
# # #                     RL.EXTERNALITEMID,
# # #                     RL.MAXIMUMRETAILPRICE_IN AS MRP,

# # #                     PL.HIQ_TARGETPRICE,
# # #                     PL.HIQ_COMMENTS AS COMMENTS,
# # #                     PL.CURRENCYCODE,
# # #                     PL.STATUS,
# # #                     PL.DELIVERYDATE AS RFQ_DELIVERY_DATE

# # #                 FROM PURCHRFQLINE PL

# # #                 LEFT JOIN PURCHRFQREPLYLINE RL
# # #                     ON RL.RFQLINERECID = PL.RECID
# # #                     AND RL.RFQID = PL.RFQID
# # #                     AND RL.DATAAREAID = 'hi-q'

# # #                 LEFT JOIN INVENTTABLE IT
# # #                     ON LTRIM(RTRIM(IT.ITEMID)) = LTRIM(RTRIM(PL.ITEMID))

# # #                 WHERE PL.RFQID = ?
# # #                   AND PL.DATAAREAID = 'hi-q'
# # #                   AND PL.STATUS < 3
# # #                   AND LTRIM(RTRIM(PL.ITEMID)) IN ({placeholders})

# # #                 ORDER BY PL.LINENUM
# # #             """, [rfq_id] + approved_items)

# # #             rows = cur.fetchall()
# # #             cols = [c[0] for c in cur.description]

# # #             for r in rows:
# # #                 data = dict(zip(cols, r))
# # #                 line_num = int(data["LINENUM"])
# # #                 item_id = str(data["ITEMID"]).strip().upper()

# # #                 # Filter by both lineNumber + itemNumber tuple (lineStatus=true only)
# # #                 if valid_payload and (line_num, item_id) not in valid_payload:
# # #                     continue

# # #                 lines.append({
# # #                     "line_num": line_num,
# # #                     "item_id": data["ITEMID"],
# # #                     "item_name": data["ITEM_NAME"] or "-",
# # #                     "external_item_id": data["EXTERNALITEMID"] or "-",
# # #                     "quantity": float(data["QTYORDERED"] or 0),
# # #                     "uom": data["PURCHUNIT"] or "-",

# # #                     "unit_price": float(data["PURCHPRICE"]) if data["PURCHPRICE"] is not None else None,
# # #                     "net_amount": float(data["LINEAMOUNT"]) if data["LINEAMOUNT"] is not None else None,

# # #                     "line_disc": float(data["LINEDISC"] or 0),
# # #                     "line_percent": float(data["LINEPERCENT"] or 0),
# # #                     "mrp": float(data["MRP"] or 0),

# # #                     "target_price": float(data["HIQ_TARGETPRICE"] or 0),
# # #                     "comments": data["COMMENTS"] or " ",

# # #                     "lead_time": data["LEADTIME"] or 0,
# # #                     "vendor_comments": data["VENDOR_COMMENTS"] or " ",

# # #                     "currency": data["CURRENCYCODE"] or "INR",

# # #                     "line_valida_from": format_utc_iso(data["VALIDFROM"]),
# # #                     "line_valid_to": format_utc_iso(data["VALIDTO"]),
# # #                     "rfq_delivery_date": format_utc_iso(data["RFQ_DELIVERY_DATE"]),
# # #                     "vendor_delivery_date": format_utc_iso(data["VENDOR_DELIVERY_DATE"]),
# # #                     "hiq_decision": "Under Review"
# # #                 })

# # #         return {
# # #             "success": True,
# # #             "data": {
# # #                 "rfq_id": rfq_id,
# # #                 "rfq_case_id": header["RFQ_CASE_ID"],
# # #                 "delivery_date": format_utc_iso(header["EXPECTED_DELIVERY_DATE"]),
# # #                 "payment_term": header["PAYMENT_TERM"] or "-",
# # #                 "delivery_term": header["DELIVERY_TERM"] or "-",
# # #                 "delivery_mode": header["DELIVERY_MODE"] or "-",
# # #                 "payment_mode": header["PAYMENT_MODE"] or "-",
# # #                 "issue_date": format_utc_iso(header["ISSUE_DATE"]),
# # #                 "closing_date": format_utc_iso(header["CLOSING_DATE"]),
# # #                 "document_title": header["DOCUMENT_TITLE"],
# # #                 "termsandconditions": header["HIQ_TERMSANDCONDITIONS"],
# # #                 "currency": header["CURRENCYCODE"] or "INR",
# # #                 "reply_delivery_date": format_utc_iso(header["REPLY_DELIVERY_DATE"]),
# # #                 "reply_delivery_mode": header["REPLY_DELIVERY_MODE"] or "-",
# # #                 "reply_delivery_term": header["REPLY_DELIVERY_TERM"] or "-",
# # #                 "reply_payment_term": header["REPLY_PAYMENT_TERM"] or "-",
# # #                 "vendor_ref": header["VENDREF"] or "-",
# # #                 "valid_from": format_utc_iso(header["VALIDFROM"]),
# # #                 "valid_to": format_utc_iso(header["VALIDTO"]),
# # #                 "validity_date_start": format_utc_iso(header["VALIDITYDATESTART"]),
# # #                 "validity_date_end": format_utc_iso(header["VALIDITYDATEEND"]),
# # #                 "total_score": header["TOTALSCORE"] or 0,
# # #                 "rank": header["RANK"] or 0,
# # #                 "reply_progress_status": header["REPLYPROGRESSSTATUS"] or 0,
# # #                 "remarks": header["REMARKS"],
# # #                 "line_items": lines
# # #             }
# # #         }

