from datetime import datetime
from datetime import datetime, timedelta

IST_OFFSET = timedelta(hours=5, minutes=30)

def calculate_days_left(expiry_date):
    if not expiry_date:
        return None

    today  = (datetime.utcnow() + IST_OFFSET).date()   # today in IST
    expiry = (expiry_date + IST_OFFSET).date()          # expiry in IST

    return (expiry - today).days

# def calculate_days_left(expiry_date):
#     if not expiry_date:
#         return None

#     today = datetime.today().date()
#     expiry = expiry_date.date()

#     return (expiry - today).days 

def format_expiry_label(expiry_date):

    days = calculate_days_left(expiry_date)

    if days < 0:
        return "Expired"

    elif days == 0:
        return "Today"

    elif days == 1:
        return "1 day"

    else:
        return f"{days} days"