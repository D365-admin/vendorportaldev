import pyodbc
from contextlib import contextmanager
from app.core.config import settings          # ← import settings object, not variables

pyodbc.pooling = True


# # ── VENDORPORTAL DB (your 3 portal tables) ────────────────────
# CONNECTION_STRING = (
#     f"DSN={settings.SQL_DSN};"
#     f"UID={settings.SQL_USERNAME};"
#     f"PWD={settings.SQL_PASSWORD};"
#     "TrustServerCertificate=yes;"
# )
# VENDOR_CONNECTION_STRING = (
#     f"DSN={settings.VSQL_DSN};"
#     f"UID={settings.SQL_USERNAME};"
#     f"PWD={settings.SQL_PASSWORD};"
#     "TrustServerCertificate=yes;"
# )
VENDOR_DB_CONNECTION = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={settings.VENDOR_DB_SERVER};"
    f"DATABASE={settings.VENDOR_DB_NAME};"
    f"UID={settings.VENDOR_DB_USER};"
    f"PWD={settings.VENDOR_DB_PASSWORD};"
    "TrustServerCertificate=yes;"
    "Encrypt=yes;"
    "Connection Timeout=30;"
)
# # ── D365 SQL Server (direct read + write bids) ────────────────
# D365_CONNECTION_STRING = (
#     f"DRIVER={{ODBC Driver 17 for SQL Server}};"
#     f"SERVER={settings.D365_DB_SERVER};"
#     f"DATABASE={settings.D365_DB_NAME};"
#     f"UID={settings.D365_DB_USER};"
#     f"PWD={settings.D365_DB_PASSWORD};"
#     "TrustServerCertificate=yes;"
#     "Connection Timeout=60;"
# )

@contextmanager
def get_connection():
    conn = None
    try:
        conn = pyodbc.connect(VENDOR_DB_CONNECTION, timeout=10)
        yield conn
    except Exception as e:
        print(f"[VENDORPORTAL] Connection failed: {e}")  
        raise                                             
    finally:
        if conn:
            conn.close()
# @contextmanager
# def get_connection():
#     """VENDORPORTAL DB — vendor_portal_user, sync_log, notification_log"""
#     conn = None
#     try:
#         conn = pyodbc.connect(VENDOR_DB_CONNECTION, timeout=10)
#         yield conn
#     except Exception as e:
#         raise Exception(f"[VENDORPORTAL] Connection failed: {str(e)}")
#     finally:
#         if conn:
#             conn.close()


# @contextmanager
# def get_connection():
#     """D365 SQL Server — read RFQ/PO/vendor + write bids"""
#     conn = None
#     try:
#         conn = pyodbc.connect(D365_CONNECTION_STRING, timeout=10)
#         yield conn
#     except Exception as e:
#         raise Exception(f"[D365] Connection failed: {str(e)}")
#     finally:
#         if conn:
#             conn.close()


def rows_to_dict(cursor) -> list[dict]:
    """Converts all cursor rows → list of dicts with lowercase keys."""
    if not cursor.description:
        return []
    cols = [col[0].lower() for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def row_to_dict(cursor) -> dict | None:
    """Converts single cursor row → dict. Returns None if not found."""
    if not cursor.description:
        return None
    cols = [col[0].lower() for col in cursor.description]
    row  = cursor.fetchone()
    return dict(zip(cols, row)) if row else None

