import os

from app.db.base import get_connection
from app.utils.date_utils import format_date
from app.utils.remainingdate import calculate_days_left


DB_SCHEMA = os.getenv("DB_SCHEMA")


def _table(table_name: str) -> str:
    """Return a schema-qualified SQL Server table name."""
    if not DB_SCHEMA:
        raise RuntimeError(
            "DB_SCHEMA environment variable is not configured. "
            "Set it to dev, sandbox, or prod in Azure App Service settings."
        )

    return f"[{DB_SCHEMA}].[{table_name}]"


# ============================================================
# BID MATERIALS
# ============================================================
def fetch_bid_materials(vendor_account: str) -> list[dict]:
    """Fetch currently valid approved materials for a vendor."""
    query = f"""
        SELECT
            P.ITEMID,
            I.NAME AS NAMEALIAS,
            P.VALIDFROM,
            P.VALIDTO
        FROM {_table('D365_PDSAPPROVEDVENDORLIST')} AS P WITH (NOLOCK)
        LEFT JOIN {_table('D365_INVENTTABLE')} AS I WITH (NOLOCK)
            ON LTRIM(RTRIM(I.ITEMID)) = LTRIM(RTRIM(P.ITEMID))
        WHERE LTRIM(RTRIM(P.PDSAPPROVEDVENDOR)) = ?
          AND P.VALIDFROM <= GETDATE()
          AND P.VALIDTO >= GETDATE()
        ORDER BY P.ITEMID
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(query, vendor_account)

            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()

            result = []
            for row in rows:
                data = dict(zip(columns, row))
                result.append(
                    {
                        "material_id": data["ITEMID"],
                        "material_description": data["NAMEALIAS"],
                        "valid_from": format_date(data["VALIDFROM"]),
                        "expiry_date": format_date(data["VALIDTO"]),
                        "days_left": calculate_days_left(data["VALIDTO"]),
                    }
                )

            return result
        finally:
            cursor.close()


# ============================================================
# VENDOR PROFILE
# ============================================================
def fetch_vendor_profile(vendor_account: str) -> dict:
    """Fetch the basic profile for a vendor account."""
    profile = {
        "email": None,
        "phone": None,
        "address": None,
        "name": None,
        "city": None,
    }

    query = f"""
        SELECT TOP 1
            NAME,
            EMAIL,
            PHONENUMBER,
            ADDRESS,
            CITY
        FROM {_table('D365_VENDORMASTER')} WITH (NOLOCK)
        WHERE LTRIM(RTRIM(ACCOUNTNUM)) = ?
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(query, vendor_account)
            row = cursor.fetchone()

            if row:
                profile["name"] = row.NAME
                profile["email"] = row.EMAIL
                profile["phone"] = row.PHONENUMBER
                profile["address"] = row.ADDRESS
                profile["city"] = row.CITY

            return profile
        finally:
            cursor.close()