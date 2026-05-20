# from datetime import datetime

# def format_date(value):
#     if value:
#         return value.strftime("%d/%m/%Y")
#     return None

from datetime import datetime

def format_date(value):
    if not value:
        return None

    #
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")


    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", ""))
            return dt.strftime("%d/%m/%Y")
        except:
            return value  

    return str(value)






# app/utils/date_utils.py

def format_utc_iso(dt) -> str | None:
    """
    Returns UTC ISO string for frontend timezone conversion.
    Frontend browser auto-converts to user's local time.
    """
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # → "2026-04-22T18:30:00Z"
    return None 

