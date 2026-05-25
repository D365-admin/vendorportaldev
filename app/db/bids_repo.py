import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.db.base import get_connection, get_connection
from app.core.config import settings

SCHEMA=settings.DB_SCHEMA
VENDOR_USER_TABLE = f"{SCHEMA}.HIQ_VENDORPORTALUSER"

OTP_TABLE = f"{SCHEMA}.HIQ_VENDOROTP"

LOGIN_LOG_TABLE = f"{SCHEMA}.HIQ_VENDORLOGINLOG"

REFRESH_TOKEN_TABLE = f"{SCHEMA}.HIQ_VENDORREFRESHTOKEN"
VEN_NOT=f"{SCHEMA}.HIQ_VENDORNOTIFICATION"
RFQ_REPLIES_TABLE = f"{SCHEMA}.HIQ_VENDORRFQREPLIES"
RFQ_BID_SUB=f"{SCHEMA}.HIQ_VENDORBIDSUBMISSIONHEADER"
RFQ_LINEBID=f"{SCHEMA}.HIQ_VENDORBIDSUBMISSIONLINE"
# ── Status constants ──────────────────────────────────────
STATUS_PENDING = 0   # inserted by vendor, waiting for scheduler
STATUS_SENT    = 1   # moved to header+line by scheduler
STATUS_FAILED  = 2   # failed, will retry next run


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

def parse_date_for_db(val):
    if not val:
        return None
    val = str(val).strip()
    if "/" in val:
        try:
            return datetime.strptime(val, "%d/%m/%Y").strftime("%Y-%m-%d 23:59:59")
        except:
            pass
    return val or None


def fmt_datetime_ms(val=None):
    if not val:
        dt = datetime.now()
    elif isinstance(val, datetime):
        dt = val
    else:
        val = str(val).replace("T", " ").strip()
        if "/" in val:
            try:
                dt = datetime.strptime(val[:10], "%d/%m/%Y")
            except:
                dt = datetime.now()
        else:
            try:
                dt = datetime.strptime(val[:19], "%Y-%m-%d %H:%M:%S")
            except:
                try:
                    dt = datetime.strptime(val[:10], "%Y-%m-%d")
                except:
                    return None
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _calculate_line_counts(payload: dict):
    items     = payload.get("Item", []) or payload.get("rfqItems", [])
    total     = len(items)
    confirmed = 0
    drafted   = 0
    unfilled  = 0
    for item in items:
        status = item.get("lineStatus", False)
        if isinstance(status, str):
            status = status.lower() == "true"
        confirmed += 1 if status else 0
        drafted   += 0 if status else 1
        if float(item.get("unitPrice") or 0) <= 0:
            unfilled += 1
    return total, drafted, confirmed, unfilled


# ══════════════════════════════════════════════════════════
# INSERT INTO HIQ_VENDORRFQREPLIES
# Called when vendor submits from portal
# ══════════════════════════════════════════════════════════
def insert_reply(payload: Dict[str, Any]) -> int:
    """
    INSERT into HIQ_VENDORRFQREPLIES.
    If already exists for same RFQ+vendor, UPDATE instead.
    Returns ID.
    """

    try:
        rfq_case_id    = payload.get("rfqCaseId")
        rfq_id         = payload.get("rfqId")
        vendor_account = payload.get("vendorAccount")

        expiry_date    = parse_date_for_db(payload.get("expiryDate"))
        receipt_date   = payload.get("receiptDate") or None

        payload_json   = json.dumps(
            payload,
            ensure_ascii=False,
            default=str
        )

        confirm_save = (
            payload.get("confirmSave")
            or "save_progress"
        )

        total, drafted, confirmed, unfilled = (
            _calculate_line_counts(payload)
        )

        with get_connection() as conn:

            cur = conn.cursor()

            # =========================================
            # CHECK EXISTING RFQ
            # =========================================

            cur.execute(
                f"""
                SELECT ID
                FROM {RFQ_REPLIES_TABLE}
                WHERE RFQID = ?
                  AND VENDORACCOUNT = ?
                """,
                rfq_id,
                vendor_account
            )

            existing = cur.fetchone()

            # =========================================
            # UPDATE EXISTING
            # =========================================

            if existing:

                cur.execute(
                    f"""
                    UPDATE {RFQ_REPLIES_TABLE}

                    SET
                        PAYLOADJSON          = ?,
                        CONFIRMSAVE          = ?,
                        TOTALLINES           = ?,
                        CONFIRMEDLINECOUNT   = ?,
                        DRAFTLINECOUNT       = ?,
                        UNCONFIRMEDLINECOUNT = ?,
                        SUBMISSIONSTATUS     = ?,
                        MODIFIEDDATETIME     = GETUTCDATE(),
                        MODIFIEDBY           = 'PORTAL',
                        RECVERSION           = ISNULL(RECVERSION,0) + 1

                    WHERE RFQID = ?
                      AND VENDORACCOUNT = ?
                    """,

                    payload_json,
                    confirm_save,

                    total,
                    confirmed,
                    drafted,
                    unfilled,

                    STATUS_PENDING,

                    rfq_id,
                    vendor_account
                )

                conn.commit()

                print(
                    f"[REPLY] Updated existing "
                    f"ID={existing[0]} "
                    f"RFQ={rfq_id}"
                )

                return int(existing[0])

            # =========================================
            # INSERT NEW
            # =========================================

            cur.execute(
                f"""
                INSERT INTO {RFQ_REPLIES_TABLE}
                (
                    RFQCASEID,
                    RFQID,
                    VENDORACCOUNT,

                    EXPIRYDATE,
                    RECEIPTDATE,

                    PAYLOADJSON,

                    TOTALLINES,
                    CONFIRMEDLINECOUNT,
                    DRAFTLINECOUNT,
                    UNCONFIRMEDLINECOUNT,

                    SUBMISSIONSTATUS,
                    CONFIRMSAVE,
                    ATTEMPTS,

                    CREATEDDATETIME,
                    CREATEDBY
                )

                OUTPUT INSERTED.ID

                VALUES
                (
                    ?, ?, ?,

                    TRY_CONVERT(datetime2, ?),
                    TRY_CONVERT(datetime2, ?),

                    ?,

                    ?, ?,
                    ?, ?,

                    ?, ?,
                    0,

                    GETUTCDATE(),
                    'PORTAL'
                )
                """,

                rfq_case_id,
                rfq_id,
                vendor_account,

                expiry_date,
                receipt_date,

                payload_json,

                total,
                confirmed,
                drafted,
                unfilled,

                STATUS_PENDING,
                confirm_save
            )

            inserted_row = cur.fetchone()

            if not inserted_row:
                raise Exception(
                    "Insert succeeded but no ID returned"
                )

            inserted_id = inserted_row[0]

            if inserted_id is None:
                raise Exception(
                    "Inserted ID is NULL"
                )

            conn.commit()

            print(
                f"[REPLY] Inserted new "
                f"ID={inserted_id} "
                f"RFQ={rfq_id}"
            )

            return int(inserted_id)

    except Exception as e:

        try:
            conn.rollback()
        except:
            pass

        print(f"[INSERT_REPLY_ERROR] {e}")

        raise Exception(
            f"[VENDORPORTAL] Connection failed: {str(e)}"
        )
# def insert_reply(payload: Dict[str, Any]) -> int:
#     """
#     INSERT into HIQ_VENDORRFQREPLIES.
#     If already exists for same RFQ+vendor, UPDATE instead.
#     Returns ID.
#     """
#     rfq_case_id    = payload.get("rfqCaseId")
#     rfq_id         = payload.get("rfqId")
#     vendor_account = payload.get("vendorAccount")
#     expiry_date    = parse_date_for_db(payload.get("expiryDate"))
#     receipt_date   = payload.get("receiptDate") or None
#     payload_json   = json.dumps(payload, ensure_ascii=False, default=str)
#     confirm_save   = payload.get("confirmSave") or "save_progress"

#     total, drafted, confirmed, unfilled = _calculate_line_counts(payload)

#     with get_connection() as conn:
#         cur = conn.cursor()

#         # Check existing
#         cur.execute(
#             f"SELECT ID FROM {RFQ_REPLIES_TABLE} WHERE RFQID=? AND VENDORACCOUNT=?",
#             rfq_id, vendor_account
#         )
#         existing = cur.fetchone()

#         if existing:
#             cur.execute(
#                 f"""
#                 UPDATE {RFQ_REPLIES_TABLE} 
#                 SET    PAYLOADJSON          = ?,
#                        CONFIRMSAVE          = ?,
#                        TOTALLINES           = ?,
#                        CONFIRMEDLINECOUNT   = ?,
#                        DRAFTLINECOUNT       = ?,
#                        UNCONFIRMEDLINECOUNT = ?,
#                        SUBMISSIONSTATUS     = ?,
#                        MODIFIEDDATETIME     = GETUTCDATE(),
#                        MODIFIEDBY           = 'PORTAL',
#                        RECVERSION           = RECVERSION + 1
#                 WHERE  RFQID = ? AND VENDORACCOUNT = ?
#                 """,
#                 payload_json, confirm_save,
#                 total, confirmed, drafted, unfilled,
#                 STATUS_PENDING,
#                 rfq_id, vendor_account
#             )
#             conn.commit()
#             print(f"[REPLY] Updated existing ID={existing[0]} for RFQ={rfq_id}")
#             return int(existing[0])

#         # INSERT new
#         cur.execute(
#             f"""
#             INSERT INTO {RFQ_REPLIES_TABLE} 
#             (
#                 RFQCASEID, RFQID, VENDORACCOUNT,
#                 EXPIRYDATE, RECEIPTDATE,
#                 PAYLOADJSON,
#                 TOTALLINES, CONFIRMEDLINECOUNT,
#                 DRAFTLINECOUNT, UNCONFIRMEDLINECOUNT,
#                 SUBMISSIONSTATUS, CONFIRMSAVE, ATTEMPTS,
#                 CREATEDDATETIME, CREATEDBY
#             )
#             VALUES
#             (
#                 ?, ?, ?,
#                 TRY_CONVERT(datetime2, ?), TRY_CONVERT(datetime2, ?),
#                 ?,
#                 ?, ?,
#                 ?, ?,
#                 ?, ?, 0,
#                 GETUTCDATE(), 'PORTAL'
#             )
#             """,
#             rfq_case_id, rfq_id, vendor_account,
#             expiry_date, receipt_date,
#             payload_json,
#             total, confirmed,
#             drafted, unfilled,
#             STATUS_PENDING, confirm_save
#         )
#         cur.execute("SELECT SCOPE_IDENTITY()")
#         new_id = int(cur.fetchone()[0])
#         conn.commit()
#         print(f"[REPLY] Inserted new ID={new_id} for RFQ={rfq_id}")
#         return new_id


def update_reply(payload: Dict[str, Any]) -> int:
    """UPDATE existing HIQ_VENDORRFQREPLIES with new payload."""
    rfq_id         = payload.get("rfqId")
    vendor_account = payload.get("vendorAccount")
    confirm_save   = payload.get("confirmSave") or "save_progress"
    payload_json   = json.dumps(payload, ensure_ascii=False, default=str)

    total, drafted, confirmed, unfilled = _calculate_line_counts(payload)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE {RFQ_REPLIES_TABLE} 
            SET    PAYLOADJSON          = ?,
                   CONFIRMSAVE          = ?,
                   TOTALLINES           = ?,
                   CONFIRMEDLINECOUNT   = ?,
                   DRAFTLINECOUNT       = ?,
                   UNCONFIRMEDLINECOUNT = ?,
                   SUBMISSIONSTATUS     = ?,
                   MODIFIEDDATETIME     = GETUTCDATE(),
                   MODIFIEDBY           = 'PORTAL',
                   RECVERSION           = RECVERSION + 1
            WHERE  RFQID = ? AND VENDORACCOUNT = ?
            """,
            payload_json, confirm_save,
            total, confirmed, drafted, unfilled,
            STATUS_PENDING,
            rfq_id, vendor_account
        )
        conn.commit()
        cur.execute(
            f"SELECT ID FROM {RFQ_REPLIES_TABLE}  WHERE RFQID=? AND VENDORACCOUNT=?",
            rfq_id, vendor_account
        )
        row = cur.fetchone()
        return int(row[0]) if row else -1


# ══════════════════════════════════════════════════════════
# GET PENDING FOR SCHEDULER
# Picks confirmed bids whose expiry has passed
# ══════════════════════════════════════════════════════════

def get_pending_for_scheduler() -> List[Dict[str, Any]]:
    """
    Returns latest pending/failed records ready to process.
    Only picks CONFIRMSAVE='confirmSave' (vendor confirmed submission).
    Only picks records where expiry date has passed.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                ID, RFQCASEID, RFQID, VENDORACCOUNT,
                PAYLOADJSON, ATTEMPTS, SENDTOD365AT, EXPIRYDATE
            FROM (
                SELECT
                    ID, RFQCASEID, RFQID, VENDORACCOUNT,
                    PAYLOADJSON, ATTEMPTS, SENDTOD365AT,
                    EXPIRYDATE, SUBMISSIONSTATUS, CONFIRMSAVE,
                    ROW_NUMBER() OVER (
                        PARTITION BY RFQID, VENDORACCOUNT
                        ORDER BY ID DESC
                    ) AS rn
                FROM {RFQ_REPLIES_TABLE} 
            ) t
            WHERE rn                = 1
              AND SUBMISSIONSTATUS  IN (?, ?)
              AND CONFIRMSAVE       = 'confirmSave'
              AND CAST(EXPIRYDATE AS DATE) < CAST(GETDATE() AS DATE)
            ORDER BY ID ASC
            """,
            STATUS_PENDING, STATUS_FAILED
        )
        rows = cur.fetchall()

    return [
        {
            "id":             int(r[0]),
            "rfq_case_id":    r[1],
            "rfq_id":         r[2],
            "vendor_account": r[3],
            "payload":        json.loads(r[4]) if r[4] else {},
            "attempts":       int(r[5] or 0),
            "last_sent":      r[6],
            "expiry_date":    r[7],
        }
        for r in rows
    ]


# ══════════════════════════════════════════════════════════
# INSERT HIQ_VENDORBIDSUBMISSIONHEADER
# Called by scheduler after picking up pending record
# ══════════════════════════════════════════════════════════
def insert_bid_header(
    rfq_replies_id: int,
    payload: dict
) -> int:
    """
    INSERT into HIQ_VENDORBIDSUBMISSIONHEADER.
    If already exists, returns existing ID.
    """

    rfq_id = payload.get("rfqId")
    vendor_account = payload.get("vendorAccount")

    try:
        with get_connection() as conn:
            cur = conn.cursor()

            # =====================================
            # IDEMPOTENT CHECK
            # =====================================
            cur.execute(
                f"""
                SELECT ID
                FROM {RFQ_BID_SUB}
                WHERE RFQID = ?
                  AND VENDORACCOUNT = ?
                """,
                rfq_id,
                vendor_account
            )

            existing = cur.fetchone()

            if existing:
                print(
                    f"[HEADER] Already exists "
                    f"ID={existing[0]} RFQ={rfq_id}"
                )
                return int(existing[0])

            # =====================================
            # INSERT HEADER
            # =====================================
            cur.execute(
                f"""
                INSERT INTO {RFQ_BID_SUB}
                (
                    VENDORRFQREPLIESID,

                    RFQCASEID,
                    RFQID,
                    DOCUMENTTITLE,
                    VENDORACCOUNT,

                    EXPIRYDATE,
                    RECEIPTDATE,

                    MODEOFDELIVERY,
                    DELIVERYTERMS,

                    METHODOFPAYMENT,
                    TERMSOFPAYMENT,

                    CURRENCY,
                    BIDTYPE,
                    ISSEALED,

                    VENDORCOMMENTS,

                    REPLYDELIVERYTERMS,
                    REPLYDELIVERYDATE,
                    REPLYDELIVERYDATETIME,

                    REPLYMODEOFDELIVERY,
                    CONFIRMSAVE,

                    ISLOCKED,
                    STATUS,

                    ISSENTTOD365,
                    SUBMITTEDTOD365AT,

                    CREATEDDATETIME,
                    CREATEDBY
                )

                OUTPUT INSERTED.ID

                VALUES
                (
                    ?,

                    ?, ?, ?, ?,

                    TRY_CONVERT(datetime2, ?),
                    TRY_CONVERT(datetime2, ?),

                    ?, ?,

                    ?, ?,

                    ?, ?, ?,

                    ?,

                    ?,
                    TRY_CONVERT(date, ?),
                    TRY_CONVERT(date, ?),

                    ?, ?,

                    0,
                    0,

                    1,
                    GETUTCDATE(),

                    GETUTCDATE(),
                    'SCHEDULER'
                )
                """,

                rfq_replies_id,

                payload.get("rfqCaseId"),
                rfq_id,
                payload.get("documentTitle")
                or payload.get("rfqCaseId"),
                vendor_account,

                parse_date_for_db(
                    payload.get("expiryDate")
                ),

                parse_date_for_db(
                    payload.get("receiptDate")
                ),

                payload.get("modeOfDelivery") or "",
                payload.get("DeliveryTerms") or "",

                payload.get("methodOfPayment") or "",
                payload.get("termsOfPayment") or "",

                payload.get("currency") or "",
                payload.get("bidType") or "",

                1 if payload.get("isSealed") else 0,

                payload.get("vendorComments") or "",

                payload.get("replyDeliveryTerms") or "",

                parse_date_for_db(
                    payload.get("replyDeliveryDate")
                ),

                parse_date_for_db(
                    payload.get("replyDeliveryDatetime")
                    or payload.get("replyDeliveryDate")
                ),

                payload.get("replyModeOfDelivery") or "",

                payload.get("confirmSave") or "confirmSave"
            )

            inserted = cur.fetchone()

            if not inserted:
                raise Exception(
                    "Header insert succeeded but no ID returned"
                )

            header_id = inserted[0]

            if header_id is None:
                raise Exception("Header ID returned NULL")

            conn.commit()

            print(
                f"[HEADER] Inserted "
                f"ID={header_id} RFQ={rfq_id}"
            )

            return int(header_id)

    except Exception as e:
        try:
            conn.rollback()
        except:
            pass

        print(f"[HEADER_ERROR] {e}")

        raise Exception(
            f"[VENDORPORTAL] Header insert failed: {str(e)}"
        )
def insert_bid_lines(
    header_id: int,
    rfq_id: str,
    vendor_account: str,
    payload: dict
) -> int:

    """
    INSERT only CONFIRMED line items into HIQ_VENDORBIDSUBMISSIONLINE.
    Draft lines and zero-price lines are skipped.
    """

    items = payload.get("Item", []) or payload.get("rfqItems", [])

    if not items:
        print(f"[LINES] No items for RFQ={rfq_id}")
        return 0

    inserted = 0

    with get_connection() as conn:

        cur = conn.cursor()

        for item in items:

            line_number = (
                item.get("lineNumber")
                or item.get("line_number")
                or 0
            )

            # -----------------------------------
            # LINE STATUS
            # -----------------------------------

            line_status = item.get(
                "lineStatus",
                True
            )

            if isinstance(line_status, str):
                line_status = (
                    line_status.lower() == "true"
                )

            # -----------------------------------
            # SKIP DRAFT LINES
            # -----------------------------------

            if not line_status:
                print(
                    f"[LINES] Skipping draft line "
                    f"{line_number}"
                )
                continue

            # -----------------------------------
            # SKIP ZERO PRICE LINES
            # -----------------------------------

            unit_price = float(
                item.get("unitPrice") or 0
            )

            if unit_price <= 0:
                print(
                    f"[LINES] Skipping zero-price line "
                    f"{line_number}"
                )
                continue

            try:

                quantity = float(
                    item.get("quantity") or 0
                )

                net_amount = float(
                    item.get("netAmount") or 0
                )

                cur.execute(
                    f"""
                    INSERT INTO {RFQ_LINEBID}
                    (
                        HEADERID,

                        RFQID,
                        VENDORACCOUNT,

                        LINENUMBER,
                        ITEMNUMBER,

                        QUANTITY,
                        UNITOFMEASURE,

                        UNITPRICE,
                        NETAMOUNT,

                        VENDORCOMMENTS,
                        LINESTATUS,

                        CREATEDDATETIME,
                        CREATEDBY,

                        REPLYDELIVERYDATETIME
                    )

                    VALUES
                    (
                        ?,

                        ?, ?,

                        ?, ?,

                        ?, ?,

                        ?, ?,

                        ?, ?,

                        GETUTCDATE(),
                        'SCHEDULER',

                        TRY_CONVERT(date, ?)
                    )
                    """,

                    # HEADER
                    header_id,

                    # RFQ
                    rfq_id,
                    vendor_account,

                    # LINE
                    line_number,

                    str(
                        item.get("itemNumber")
                        or ""
                    ),

                    # QTY/UOM
                    quantity,

                    item.get(
                        "unitOfMeasure"
                    ) or "",

                    # PRICE
                    unit_price,

                    net_amount,

                    # COMMENTS
                    item.get(
                        "vendorComments"
                    ) or "",

                    # LINE STATUS
                    1 if line_status else 0,

                    # DELIVERY DATE
                    parse_date_for_db(
                        item.get(
                            "replyDeliveryDatetime"
                        )
                        or item.get(
                            "deliveryDate"
                        )
                    )
                )

                inserted += 1

            except Exception as e:

                print(
                    f"[LINES] "
                    f"Line {line_number} skip: {e}"
                )

                continue

        conn.commit()

    print(
        f"[LINES] "
        f"{inserted} confirmed lines inserted "
        f"for RFQ={rfq_id}"
    )

    return inserted

# ══════════════════════════════════════════════════════════
# UPDATE HIQ_VENDORRFQREPLIES AFTER SUCCESS
# ══════════════════════════════════════════════════════════

def mark_all_sent_for_rfq(rfq_id: str, vendor_account: str):
    """
    UPDATE HIQ_VENDORRFQREPLIES → SUBMISSIONSTATUS=1.
    Called after header+line inserted successfully.
    No D365 response needed — data moved to Azure SQL tables.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE {RFQ_REPLIES_TABLE}
            SET    SUBMISSIONSTATUS = ?,
                   SENDTOD365AT     = GETUTCDATE(),
                   MODIFIEDDATETIME = GETUTCDATE(),
                   MODIFIEDBY       = 'SCHEDULER',
                   RECVERSION = ISNULL(RECVERSION,0) + 1
                   --RECVERSION       = RECVERSION + 1
            WHERE  RFQID           = ?
              AND  VENDORACCOUNT   = ?
              AND  SUBMISSIONSTATUS IN (?, ?)
            """,
            STATUS_SENT,
            rfq_id, vendor_account,
            STATUS_PENDING, STATUS_FAILED
        )
        conn.commit()
        print(f"[REPLY] RFQ={rfq_id} vendor={vendor_account} → SUBMISSIONSTATUS=1")


def mark_failed(row_id: int, error: str, current_attempts: int):
    """
    UPDATE HIQ_VENDORRFQREPLIES → SUBMISSIONSTATUS=2 (Failed).
    Scheduler retries on next run.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE {RFQ_REPLIES_TABLE}
            SET    SUBMISSIONSTATUS = ?,
                   LASTERROR        = ?,
                   ATTEMPTS         = ?,
                   SENDTOD365AT     = GETUTCDATE(),
                   MODIFIEDDATETIME = GETUTCDATE(),
                   MODIFIEDBY       = 'SCHEDULER',
                   RECVERSION = ISNULL(RECVERSION,0) + 1
                   --RECVERSION       = RECVERSION + 1
            WHERE  ID = ?
            """,
            STATUS_FAILED,
            error[:4000],
            current_attempts + 1,
            row_id
        )
        conn.commit()
        print(f"[REPLY] ID={row_id} → FAILED (attempt {current_attempts + 1})")


def increment_attempts(row_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {RFQ_REPLIES_TABLE} SET ATTEMPTS=ATTEMPTS+1, SENDTOD365AT=GETUTCDATE() WHERE ID=?",
            row_id
        )
        conn.commit()


# ══════════════════════════════════════════════════════════
# EXPIRY REMINDER EMAILS
# ══════════════════════════════════════════════════════════

def already_sent_reminder(vendor_account: str, rfq_case_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(1) FROM {VEN_NOT}
            WHERE VENDORACCOUNT=? AND REFERENCEID=? AND NOTIFTYPE=1
            """,
            vendor_account, rfq_case_id
        )
        return cur.fetchone()[0] > 0

def get_all_expiring_rfqs_with_vendors():

    q = f"""
    SELECT

        C.RFQCASEID,

        T.RFQID,

        C.NAME,

        C.EXPIRYDATETIME,

        V.VENDACCOUNT

    FROM {SCHEMA}.D365_PURCHRFQCASETABLE C
    WITH (NOLOCK)

    INNER JOIN {SCHEMA}.D365_PURCHRFQVENDLINK V
    WITH (NOLOCK)

        ON V.RFQCASEID = C.RFQCASEID

    INNER JOIN {SCHEMA}.D365_PURCHRFQTABLE T
    WITH (NOLOCK)

        ON T.RFQCASEID = C.RFQCASEID
       AND T.VENDACCOUNT = V.VENDACCOUNT

    WHERE CAST(C.EXPIRYDATETIME AS DATE)
            =
          CAST(DATEADD(DAY,1,GETDATE()) AS DATE)

      AND C.EXPIRYDATETIME >= GETDATE()

      AND C.EXPIRYDATETIME <
            DATEADD(HOUR,24,GETDATE())
    """

    with get_connection() as conn:

        cur = conn.cursor()

        cur.execute(q)

        rows = cur.fetchall()

        if not rows:
            return []

        cols = [
            c[0].lower()
            for c in cur.description
        ]

        return [
            dict(zip(cols, row))
            for row in rows
        ]
# def get_all_expiring_rfqs_with_vendors():
#     q = """
#     SELECT C.RFQCASEID, T.RFQID, C.NAME, C.EXPIRYDATETIME, V.VENDACCOUNT
#     FROM PURCHRFQCASETABLE C WITH (NOLOCK)
#     INNER JOIN PURCHRFQVENDLINK V WITH (NOLOCK)
#         ON V.RFQCASEID=C.RFQCASEID AND V.DATAAREAID=C.DATAAREAID
#     INNER JOIN PURCHRFQTABLE T WITH (NOLOCK)
#         ON T.RFQCASEID=C.RFQCASEID AND T.VENDACCOUNT=V.VENDACCOUNT AND T.DATAAREAID=C.DATAAREAID
#     WHERE C.DATAAREAID=?
#       AND CAST(C.EXPIRYDATETIME AS DATE)=CAST(DATEADD(DAY,1,GETDATE()) AS DATE)
#       AND C.EXPIRYDATETIME >= GETDATE()
#       AND C.EXPIRYDATETIME <  DATEADD(HOUR,24,GETDATE())
#     """
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute(q, settings.D365_COMPANY)
#         rows = cur.fetchall()
#         if not rows:
#             return []
#         cols = [c[0].lower() for c in cur.description]
#         return [dict(zip(cols, row)) for row in rows]


def send_expiry_reminder_emails():
    from app.services.email_service import send_rfq_expiry_reminder
    from app.services.vendormaterial_service import fetch_vendor_profile
    from app.services.notification_repo import insert_notification

    print("[REMINDER] Checking RFQs expiring in 24h...")
    expiring = get_all_expiring_rfqs_with_vendors()
    if not expiring:
        print("[REMINDER] None found.")
        return

    vendor_groups = defaultdict(list)
    for item in expiring:
        vendor_groups[item["vendaccount"]].append(item)

    for vendor_account, rfq_list in vendor_groups.items():
        unsent = [r for r in rfq_list if not already_sent_reminder(vendor_account, r["rfqcaseid"])]
        if not unsent:
            continue
        try:
            profile      = fetch_vendor_profile(vendor_account)
            vendor_email = profile.get("email") if profile else None
            vendor_name  = profile.get("name", vendor_account) if profile else vendor_account
        except Exception as e:
            print(f"[REMINDER] No profile {vendor_account}: {e}")
            continue
        if not vendor_email:
            continue
        try:
            send_rfq_expiry_reminder(to_email=vendor_email, vendor_name=vendor_name, rfq_list=unsent)
            for r in unsent:
                insert_notification(
                    vendor_account=vendor_account,
                    notif_type="RFQ_EXPIRING",
                    title="RFQ Expiring Soon",
                    message=f"RFQ {r['rfqcaseid']} expires on {str(r['expirydatetime'])[:10]}.",
                    reference_id=r["rfqcaseid"]
                )
            print(f"[REMINDER] Sent → {vendor_email} | {len(unsent)} RFQs")
        except Exception as e:
            print(f"[REMINDER] Failed {vendor_account}: {e}")


# ══════════════════════════════════════════════════════════
# READ LINES (for portal display)
# ══════════════════════════════════════════════════════════

def get_rfq_lines_with_rfqid(rfq_id: str, vendor_account: str):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT LINENUMBER, ITEMNUMBER, QUANTITY,
                   UNITOFMEASURE, UNITPRICE, NETAMOUNT,
                   VENDORCOMMENTS, LINESTATUS
            FROM {RFQ_LINEBID}
            WHERE RFQID=? AND VENDORACCOUNT=?
            ORDER BY LINENUMBER
            """,
            rfq_id, vendor_account
        )
        rows = cur.fetchall()
    return [
        {
            "lineNumber":     r[0],
            "itemNumber":     r[1],
            "quantity":       r[2],
            "unitOfMeasure":  r[3],
            "unitPrice":      r[4],
            "netAmount":      r[5],
            "vendorComments": r[6],
            "lineStatus":     bool(r[7])
        }
        for r in rows
    ]



# import json
# from typing import List, Dict, Any
# from app.db.base import get_connection
# from app.core.config import settings 

# from app.services.notification_service import notify_rfq_expiring


# STATUS_PENDING = 0
# STATUS_SENT = 1
# STATUS_FAILED = 2

# PARTITION_ID = 5637144576
# DATAAREA_ID = "dat"

# from datetime import datetime  
# def parse_date_for_db(val):
#     if not val:
#         return None
#     val = str(val).strip()
#     if "/" in val:
#         try:
#             return datetime.strptime(val, "%d/%m/%Y").strftime("%Y-%m-%d 23:59:59")
#         except:
#             pass
#     return val or None

# def get_next_id(cursor) -> int:
#     cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 FROM HIQ_VENDORRFQREPLIES")
#     return int(cursor.fetchone()[0])

# def _calculate_unfilled_count(payload: Dict[str, Any]) -> int:
#     """
#     unfilled = unitPrice is 0 or null, regardless of lineStatus
#     """
#     unfilled = 0
#     for item in payload.get("Item", []):
#         unit_price = float(item.get("unitPrice") or 0)
#         if unit_price <= 0:
#             unfilled += 1
#     return unfilled
# def _calculate_line_counts(payload: dict[str, Any]):
#     items = payload.get("Item", []) or payload.get("rfqItems", [])

#     total = len(items)
#     confirmed = 0
#     drafted = 0
#     unfilled = 0

#     for item in items:
#         # line status
#         status = item.get("lineStatus", False)

#         if isinstance(status, str):
#             status = status.lower() == "true"

#         if status:
#             confirmed += 1
#         else:
#             drafted += 1

#         # unit price check
#         unit_price = float(item.get("unitPrice") or 0)
#         if unit_price <= 0:
#             unfilled += 1

#     return total, drafted, confirmed, unfilled
    
# def insert_reply(payload: Dict[str, Any]) -> int:
#     rfq_case_id    = payload.get("rfqCaseId")
#     rfq_id         = payload.get("rfqId")
#     vendor_account = payload.get("vendorAccount")
#     expiry_date    = parse_date_for_db(payload.get("expiryDate"))
#     receipt_date   = (payload.get("receiptDate"))
#     payload_json   = json.dumps(payload, ensure_ascii=False)
#     confirm_save = payload.get("confirmSave") or "save_progress"  # ← default if null
#     total, drafted, confirmed,unfilled = _calculate_line_counts(payload)
 
 
#     with get_connection() as conn:
#         cur = conn.cursor()
#         next_id = get_next_id(cur)
 
#         cur.execute("""
#             INSERT INTO HIQ_VENDORRFQREPLIES
#             (
#                 PARTITION, DATAAREAID, ID,
#                 RFQ_CASE_ID, RFQ_ID, VENDOR_ACCOUNT,
#                 EXPIRY_DATE, EXPIRY_DATETZID,
#                 RECEIPT_DATE, RECEIPT_DATETZID,
#                 PAYLOAD_JSON,
#                 CREATED_AT, CREATED_ATTZID,
#                 ATTEMPTS, SUBMISSION_STATUS,
#                 CONFIRM_SAVE,UNCONFIRMEDLINECOUNT,TOTALLINES,
#                 DRAFTLINECOUNT,
#                 CONFIRMEDLINECOUNT
                
#             )
#             VALUES (?, ?, ?, ?, ?, ?,
#                     TRY_CONVERT(datetime, ?), 37001,
#                     TRY_CONVERT(datetime, ?), 37001,
#                     ?,
#                     GETDATE(), 37001,
#                     0, ?,?,?,?,?,?)
#         """, (
#             PARTITION_ID, DATAAREA_ID, next_id,
#             rfq_case_id, rfq_id, vendor_account,
#             expiry_date, receipt_date,
#             payload_json, STATUS_PENDING,
#             # confirm_save,unfilled,total,drafted,confirmed
#             confirm_save, drafted, total, drafted, confirmed  # ← save it
#         ))
 
#         conn.commit()
#         return next_id
 
# # def insert_reply(payload: Dict[str, Any]) -> int:
# #     rfq_case_id = payload.get("rfqCaseId")
# #     rfq_id = payload.get("rfqId")
# #     vendor_account = payload.get("vendorAccount")
# #     expiry_date = payload.get("expiryDate")
# #     receipt_date = payload.get("receiptDate")
# #     payload_json = json.dumps(payload, ensure_ascii=False)

# #     with get_connection() as conn:
# #         cur = conn.cursor()
# #         next_id = get_next_id(cur)

# #         cur.execute("""
# #             INSERT INTO HIQ_VENDORRFQREPLIES
# #             (
# #                 PARTITION, DATAAREAID, ID,
# #                 RFQ_CASE_ID, RFQ_ID, VENDOR_ACCOUNT,
# #                 EXPIRY_DATE, EXPIRY_DATETZID,
# #                 RECEIPT_DATE, RECEIPT_DATETZID,
# #                 PAYLOAD_JSON,
# #                 CREATED_AT, CREATED_ATTZID,
# #                 ATTEMPTS, SUBMISSION_STATUS
# #             )
# #             VALUES (?, ?, ?, ?, ?, ?,
# #                     TRY_CONVERT(datetime, ?), 37001,
# #                     TRY_CONVERT(datetime, ?), 37001,
# #                     ?,
# #                     GETDATE(), 37001,
# #                     0, ?)
# #         """, (
# #             PARTITION_ID, DATAAREA_ID, next_id,
# #             rfq_case_id, rfq_id, vendor_account,
# #             expiry_date, receipt_date,
# #             payload_json, STATUS_PENDING
# #         ))

# #         conn.commit()
# #         return next_id

# def get_expired_pending() -> List[Dict[str, Any]]:
#     with get_connection() as conn:
#         cur = conn.cursor()

#         cur.execute("""
#             SELECT ID, PAYLOAD_JSON, ATTEMPTS, SEND_TO_D365_AT
#             FROM (
#                 SELECT
#                     ID,
#                     PAYLOAD_JSON,
#                     ATTEMPTS,
#                     SEND_TO_D365_AT,
#                     SUBMISSION_STATUS,
#                     EXPIRY_DATE,
#                     CONFIRM_SAVE,
#                     RFQ_ID,
#                     VENDOR_ACCOUNT,
#                     ROW_NUMBER() OVER (
#                         PARTITION BY RFQ_ID, VENDOR_ACCOUNT
#                         ORDER BY ID DESC
#                     ) AS rn
#                 FROM HIQ_VENDORRFQREPLIES
#             ) t
#             WHERE rn = 1
#               AND SUBMISSION_STATUS IN (?, ?)
#               AND CAST(EXPIRY_DATE AS DATE) < CAST(GETDATE() AS DATE)
#               --AND CAST(DATEADD(MINUTE, 330, EXPIRY_DATE) AS DATE) < CAST(GETDATE() AS DATE)
#               --AND EXPIRY_DATE <= GETDATE()
#               AND CONFIRM_SAVE = 'confirmSave'
#             ORDER BY ID ASC
#         """, (STATUS_PENDING, STATUS_FAILED))

#         rows = cur.fetchall()

#         return [
#             {
#                 "id": int(r[0]),
#                 "payload": json.loads(r[1]),
#                 "attempts": int(r[2] or 0),
#                 "last_sent": r[3]
#             }
#             for r in rows
#         ]
# # def get_expired_pending() -> List[Dict[str, Any]]:
# #     with get_connection() as conn:
# #         cur = conn.cursor()
# #         cur.execute("""
# #                 SELECT ID, PAYLOAD_JSON
# #                 FROM HIQ_VENDORRFQREPLIES
# #                 WHERE 
# #                     SUBMISSION_STATUS IN (?, ?)
# #                     AND EXPIRY_DATE <= GETDATE()
# #                     AND CONFIRM_SAVE = 'confirmSave'
# #                     AND (
# #                         -- first 5 attempts → every 5 minutes
# #                         (ATTEMPTS < 5 AND (
# #                             SEND_TO_D365_AT IS NULL
# #                             OR DATEDIFF(MINUTE, SEND_TO_D365_AT, GETDATE()) >= 5
# #                         ))

# #                         OR

# #                         -- after 5 attempts → every 1 hour
# #                         (ATTEMPTS >= 5 AND (
# #                             SEND_TO_D365_AT IS NULL
# #                             OR DATEDIFF(HOUR, SEND_TO_D365_AT, GETDATE()) >= 1
# #                         ))
# #                     )
# #                 ORDER BY ID ASC
# #                     """, (STATUS_PENDING, STATUS_FAILED))
# #         # cur.execute("""
# #         #     SELECT ID, PAYLOAD_JSON
# #         #     FROM HIQ_VENDORRFQREPLIES
# #         #     WHERE 
# #         #         SUBMISSION_STATUS IN (?, ?)   -- ✅ Pending + Failed
# #         #         AND EXPIRY_DATE <= GETDATE()
# #         #         AND ATTEMPTS < 5              -- ✅ Retry limit
# #         #         AND CONFIRM_SAVE = 'confirmSave'  
# #         #         AND (
                    
# #         #             --  First 5 attempts → quick retry (every 5 mins)
# #         #             (ATTEMPTS < 5 AND (
# #         #                 SEND_TO_D365_AT IS NULL
# #         #                 OR DATEDIFF(MINUTE, SEND_TO_D365_AT, GETDATE()) >= 5
# #         #             ))

# #         #             OR

# #         #             -- After 5 attempts → retry every 1 hour
# #         #             (ATTEMPTS >= 5 AND (
# #         #                 SEND_TO_D365_AT IS NULL
# #         #                 OR DATEDIFF(HOUR, SEND_TO_D365_AT, GETDATE()) >= 1
# #         #             ))

# #         #         )

# #         #     ORDER BY ID ASC
# #         # """, (STATUS_PENDING, STATUS_FAILED))
# # # AND (
# # #                     SEND_TO_D365_AT IS NULL
# # #                     OR DATEDIFF(MINUTE, SEND_TO_D365_AT, GETDATE()) >= 5
# # #                 ) 
# #         rows = cur.fetchall()

# #         return [
# #             {
# #                 "id": int(r[0]),
# #                 "payload": json.loads(r[1])
# #             }
# #             for r in rows
# #         ]

# def mark_sent(row_id: int, d365_response: str):
#     with get_connection() as conn:
#         cur = conn.cursor()
        
#         cur.execute("""
#             UPDATE HIQ_VENDORRFQREPLIES
#             SET SUBMISSION_STATUS = ?,
#                 D365_RESPONSE = ?,
#                 LAST_ERROR = NULL,
#                 SEND_TO_D365_AT = GETDATE(),
#                 SEND_TO_D365_ATTZID = 37001
#             WHERE ID = ?
#         """, (STATUS_SENT, d365_response, row_id))
#         conn.commit()


# def mark_failed(row_id: int, err: str):
#     if not err:
#         err = "Unknown error"
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             UPDATE HIQ_VENDORRFQREPLIES
#             SET SUBMISSION_STATUS = ?,
#                 LAST_ERROR = ?,
#                 ATTEMPTS = ATTEMPTS + 1,
#                 SEND_TO_D365_AT = GETDATE()  
#             WHERE ID = ?
#         """, (STATUS_FAILED, err, row_id))
#         conn.commit()


# def get_failed(limit: int = 50) -> List[Dict[str, Any]]:
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT TOP (?) ID, PAYLOAD_JSON, ATTEMPTS
#             FROM HIQ_VENDORRFQREPLIES
#             WHERE SUBMISSION_STATUS = ?
#             ORDER BY ID ASC
#         """, (limit, STATUS_FAILED))

#         return [
#             {"id": int(r[0]), "payload": json.loads(r[1]), "attempts": int(r[2])}
#             for r in cur.fetchall()
#         ]


# def increment_attempts(row_id: int):
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             UPDATE HIQ_VENDORRFQREPLIES
#             SET ATTEMPTS = ATTEMPTS + 1
#             WHERE ID = ?
#         """, (row_id,))
#         conn.commit()
# def get_rfq_lines_with_rfqid(rfq_case_id: str, vendor_account: str) -> dict:
#     with get_connection() as conn:
#         cur = conn.cursor()

#         cur.execute("""
#             SELECT TOP 1 RFQID 
#             FROM PURCHRFQTABLE
#             WHERE RFQCASEID = ?
#             AND DATAAREAID = 'hi-q'
#             AND VENDACCOUNT = ?
#         """, (rfq_case_id, vendor_account))

#         row = cur.fetchone()
#         rfq_id = row[0] if row else rfq_case_id

#         cur.execute("""
#             SELECT 
#                 pl.LINENUM,
#                 pl.ITEMID,
#                 pl.PURCHQTY,
#                 pl.PURCHUNIT
#             FROM PURCHRFQREPLYLINE rl
#             INNER JOIN PURCHRFQLINE pl
#                 ON rl.RFQLINERECID = pl.RECID
#             WHERE rl.RFQID = ?
#             AND rl.DATAAREAID = 'hi-q'
#             ORDER BY rl.LINENUM ASC
#         """, (rfq_id,))

#         lines = []
#         for r in cur.fetchall():
#             lines.append({
#                 "lineNumber": int(float(r[0])),
#                 "itemId":     str(r[1]).strip(),
#                 "quantity":   float(r[2]),
#                 "unit":       str(r[3]).strip()
#             })

#         return {"rfqId": rfq_id, "lines": lines} 

# def mark_all_sent_for_rfq(rfq_id: str, vendor_account: str, d365_resp: str):
#     """Mark ALL pending/failed rows for this RFQ+vendor as SENT, not just the latest."""
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             UPDATE HIQ_VENDORRFQREPLIES
#             SET SUBMISSION_STATUS = ?,
#                 SEND_TO_D365_AT   = GETDATE(),
#                 D365_RESPONSE     = ?
#             WHERE RFQ_ID          = ?
#               AND VENDOR_ACCOUNT  = ?
#               AND SUBMISSION_STATUS IN (?, ?)
#         """, (
#             STATUS_SENT, d365_resp,
#             rfq_id, vendor_account,
#             STATUS_PENDING, STATUS_FAILED
#         ))
#         conn.commit()

# from app.services.email_service import send_rfq_expiry_reminder
# from app.services.vendormaterial_service import fetch_vendor_profile


# def get_all_expiring_rfqs_with_vendors():
#     """
#     Get all RFQs expiring in 23-24 hours.
#     Uses PURCHRFQVENDLINK to get all vendors regardless of submission.
#     """
#     q = """
#     SELECT
#         C.RFQCASEID,
#         T.RFQID,
#         C.NAME,
#         C.EXPIRYDATETIME,
#         V.VENDACCOUNT

#     FROM PURCHRFQCASETABLE C WITH (NOLOCK)

#     INNER JOIN PURCHRFQVENDLINK V WITH (NOLOCK)
#         ON  V.RFQCASEID  = C.RFQCASEID
#         AND V.DATAAREAID = C.DATAAREAID

#     INNER JOIN PURCHRFQTABLE T WITH (NOLOCK)
#         ON  T.RFQCASEID   = C.RFQCASEID
#         AND T.VENDACCOUNT = V.VENDACCOUNT
#         AND T.DATAAREAID  = C.DATAAREAID

#     WHERE C.DATAAREAID = ?
#     AND CAST(C.EXPIRYDATETIME AS DATE) = CAST(DATEADD(DAY, 1, GETDATE()) AS DATE)
#     AND C.EXPIRYDATETIME >= GETDATE()
#     AND C.EXPIRYDATETIME <  DATEADD(HOUR, 24, GETDATE())
#     --AND C.EXPIRYDATETIME >= DATEADD(HOUR, 23, GETDATE())
#     --AND C.EXPIRYDATETIME <  DATEADD(HOUR, 24, GETDATE())
#     """
#     from app.db.base import get_connection
#     with get_connection() as conn:
#         cur = conn.cursor()
#         cur.execute(q, settings.D365_COMPANY)
#         rows = cur.fetchall()
#         if not rows:
#             return []
#         cols = [c[0].lower() for c in cur.description]
#         return [dict(zip(cols, row)) for row in rows]
# def send_expiry_reminder_emails():
#     print("[REMINDER] Checking RFQs expiring in 24 hours...")

#     expiring = get_all_expiring_rfqs_with_vendors()

#     if not expiring:
#         print("[REMINDER] No expiring RFQs found.")
#         return

#     # ── Group by vendor ───────────────────────────────────────
#     vendor_groups = defaultdict(list)
#     for item in expiring:
#         vendor_groups[item["vendaccount"]].append(item)

#     # ── One email per vendor ──────────────────────────────────
#     for vendor_account, rfq_list in vendor_groups.items():

#         # Filter out RFQs we already sent reminder for
#         unsent = [
#             r for r in rfq_list
#             if not already_sent_reminder(vendor_account, r["rfqcaseid"])
#         ]

#         if not unsent:
#             print(f"[REMINDER] {vendor_account} — all reminders already sent, skipping")
#             continue

#         # Get vendor email
#         try:
#             profile      = fetch_vendor_profile(vendor_account)
#             vendor_email = profile.get("email") if profile else None
#             vendor_name  = profile.get("name", vendor_account) if profile else vendor_account
#         except Exception as e:
#             print(f"[REMINDER] No profile for {vendor_account}: {e}")
#             continue

#         if not vendor_email:
#             print(f"[REMINDER] No email for {vendor_account} — skipping")
#             continue

#         # Send grouped email
#         try:
#             send_rfq_expiry_reminder(
#                 to_email    = vendor_email,
#                 vendor_name = vendor_name,
#                 rfq_list    = unsent
#             )

#             # Insert notification for each unsent RFQ — acts as sent flag
#             from app.services.notification_repo import insert_notification
#             for r in unsent:
#                 insert_notification(
#                     vendor_account = vendor_account,
#                     notif_type     = "RFQ_EXPIRING",
#                     title          = "RFQ Expiring Soon ⚠️",
#                     message        = f"RFQ {r['rfqcaseid']} expires on {str(r['expirydate'])[:10]}.",
#                     reference_id   = r["rfqcaseid"]   
#                 )

#             print(f"[REMINDER] Sent → {vendor_email} | {len(unsent)} RFQs")

#         except Exception as e:
#             print(f"[REMINDER] Failed for {vendor_account}: {e}")

# # def send_expiry_reminder_emails():
# #     print("Checking RFQs expiring in 1 day...")

# #     expiring = get_all_expiring_rfqs_with_vendors()

# #     if not expiring:
# #         print("No expiry reminders to send.")
# #         return

# #     from collections import defaultdict
# #     vendor_groups = defaultdict(list)

# #     for item in expiring:
# #         vendor_groups[item["vendaccount"]].append(item)

# #     for vendor_account, rfq_list in vendor_groups.items():
# #         try:
# #             profile      = fetch_vendor_profile(vendor_account)
# #             vendor_email = profile.get("email") if profile else None
# #             vendor_name  = profile.get("name", vendor_account) if profile else vendor_account
# #         except Exception as e:
# #             print(f"[REMINDER] No profile for {vendor_account}: {e}")
# #             continue

# #         if not vendor_email:
# #             print(f"[REMINDER] No email for {vendor_account} — skipping")
# #             continue

# #         # ── Insert notification for each RFQ ──────────────────
# #         for rfq in rfq_list:
# #             try:
# #                 notify_rfq_expiring(
# #                     vendor_account = vendor_account,
# #                     rfq_id         = rfq["rfqid"],          # ← rfqid
# #                     expiry_date    = str(rfq["expirydatetime"])[:10]
# #                 )
# #             except Exception as e:
# #                 print(f"[NOTIF] Failed for {rfq['rfqid']}: {e}")

# #         # ── Send email ─────────────────────────────────────────
# #         try:
# #             send_rfq_expiry_reminder_grouped(
# #                 to_email    = vendor_email,
# #                 vendor_name = vendor_name,
# #                 rfq_list    = rfq_list
# #             )
# #             rfq_ids = [r["rfqid"] for r in rfq_list]       # ← rfqid
# #             print(f"[REMINDER] Grouped email → {vendor_email} | {len(rfq_list)} RFQs: {rfq_ids}")
# #         except Exception as e:
# #             print(f"[REMINDER] Failed for {vendor_account}: {e}")
# # # def send_expiry_reminder_emails():
# # #     print("Checking RFQs expiring in 1 day...")

# # #     expiring = get_all_expiring_rfqs_with_vendors()

# # #     if not expiring:
# # #         print("No expiry reminders to send.")
# # #         return

# # #     # ── Group by vendor_account ───────────────────────────────
# # #     from collections import defaultdict
# # #     vendor_groups = defaultdict(list)

# # #     for item in expiring:
# # #         vendor_groups[item["vendaccount"]].append(item)

# # #     # ── Send ONE email per vendor with ALL their RFQs ─────────
# # #     for vendor_account, rfq_list in vendor_groups.items():
# # #         try:
# # #             profile      = fetch_vendor_profile(vendor_account)
# # #             vendor_email = profile.get("email") if profile else None
# # #             vendor_name  = profile.get("name", vendor_account) if profile else vendor_account
# # #         except Exception as e:
# # #             print(f"[REMINDER] No profile for {vendor_account}: {e}")
# # #             continue

# # #         if not vendor_email:
# # #             print(f"[REMINDER] No email for {vendor_account} — skipping")
# # #             continue

# # #         try:
# # #             send_rfq_expiry_reminder_grouped(
# # #                 to_email     = vendor_email,
# # #                 vendor_name  = vendor_name,
# # #                 rfq_list     = rfq_list
# # #             )
# # #             rfq_ids = [r["rfqcaseid"] for r in rfq_list]
# # #             print(f"[REMINDER] Grouped email → {vendor_email} | {len(rfq_list)} RFQs: {rfq_ids}")
# # #         except Exception as e:
# # #             print(f"[REMINDER] Failed for {vendor_account}: {e}")