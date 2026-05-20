from app.db.base import get_connection,get_d365_connection
from typing import Dict, Any


# ============================================================
# API — MASTER DROPDOWNS
# /rfq/dropdowns
#
# Returns plain lists of "CODE - Full Description" strings
# ============================================================
def fetch_rfq_dropdowns() -> Dict[str, Any]:
    with get_d365_connection() as conn:
        cur = conn.cursor()

        # ── Delivery Mode ───────────────────────────────────────
        cur.execute("""
            SELECT CODE + ' - ' + ISNULL(TXT, CODE)
            FROM DLVMODE WITH (NOLOCK)
            WHERE DATAAREAID = 'hi-q'
            ORDER BY TXT
        """)
        delivery_modes = [row[0] for row in cur.fetchall()]

        # ── Delivery Term ───────────────────────────────────────
        cur.execute("""
            SELECT CODE + ' - ' + ISNULL(TXT, CODE)
            FROM DLVTERM WITH (NOLOCK)
            WHERE DATAAREAID = 'hi-q'
            ORDER BY TXT
        """)
        delivery_terms = [row[0] for row in cur.fetchall()]

        # ── Payment Term ────────────────────────────────────────
        cur.execute("""
            SELECT PAYMTERMID 
            FROM PAYMTERM WITH (NOLOCK)
            WHERE DATAAREAID = 'hi-q'
            ORDER BY DESCRIPTION
        """)
        payment_terms = [row[0] for row in cur.fetchall()]

        # ── Payment Mode ────────────────────────────────────────
        cur.execute("""
            SELECT PAYMMODE + ' - ' + ISNULL(NAME, PAYMMODE)
            FROM VENDPAYMMODETABLE WITH (NOLOCK)
            WHERE DATAAREAID = 'hi-q'
            ORDER BY NAME
        """)
        payment_modes = [row[0] for row in cur.fetchall()]

    return {
        "success": True,
        "data": {
            "delivery_modes": delivery_modes,
            "delivery_terms": delivery_terms,
            "payment_terms":  payment_terms,
            "payment_modes":  payment_modes,
        }
    }