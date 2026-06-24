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

from datetime import datetime, date


def format_utc_iso(dt) -> str | None:
    """
    Converts datetime/date/dd-MM-yyyy string
    into UTC ISO format.

    Output:
    2026-05-30T00:00:00Z
    """

    if dt is None:
        return None

    # datetime object
    if isinstance(dt, datetime):
        return dt.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    # SQL DATE object (important fix)
    if isinstance(dt, date):
        return datetime.combine(
            dt,
            datetime.min.time()
        ).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    # dd/MM/yyyy string
    if isinstance(dt, str):
        try:
            parsed = datetime.strptime(
                dt,
                "%d/%m/%Y"
            )

            return parsed.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        except Exception:
            return None

    return None
# def format_utc_iso(dt) -> str | None:
#     """
#     Returns UTC ISO string for frontend timezone conversion.
#     Frontend browser auto-converts to user's local time.
#     """
#     if dt is None:
#         return None
#     if isinstance(dt, datetime):
#         return dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # → "2026-04-22T18:30:00Z"
#     return None 



