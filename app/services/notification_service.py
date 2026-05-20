# notification_service.py

from app.services.notification_repo import (
    insert_notification
)

# =========================================================
# NEW RFQ
# =========================================================

def notify_new_rfq(
    vendor_account: str,
    rfq_id: str,
    rfq_name: str
):

    return insert_notification(

        vendor_account=vendor_account,

        notif_type="NEW_RFQ",

        title="New RFQ Received",

        message=(
            f"A new RFQ "
            f"{rfq_id} - '{rfq_name}' "
            f"has been assigned to you."
        ),

        reference_id=rfq_id,
    )


# =========================================================
# RFQ EXPIRING
# =========================================================

def notify_rfq_expiring(
    vendor_account: str,
    rfq_id: str,
    expiry_date: str
):

    return insert_notification(

        vendor_account=vendor_account,

        notif_type="RFQ_EXPIRING",

        title="RFQ Expiring Tomorrow",

        message=(
            f"RFQ {rfq_id} "
            f"expires on {expiry_date}. "
            f"Please submit your bid."
        ),

        reference_id=rfq_id,
    )


# =========================================================
# PO CONFIRMED
# =========================================================

def notify_po_confirmed(
    vendor_account: str,
    po_number: str
):

    return insert_notification(

        vendor_account=vendor_account,

        notif_type="PO_CONFIRMED",

        title="Purchase Order Confirmed",

        message=(
            f"PO {po_number} "
            f"has been confirmed."
        ),

        reference_id=po_number,
    )


# =========================================================
# RFQ ACCEPTED
# =========================================================

def notify_rfq_accepted(
    vendor_account: str,
    rfq_id: str
):

    return insert_notification(

        vendor_account=vendor_account,

        notif_type="RFQ_ACCEPTED",

        title="RFQ Bid Accepted",

        message=(
            f"Your bid for "
            f"RFQ {rfq_id} "
            f"has been accepted."
        ),

        reference_id=rfq_id,
    )


# =========================================================
# RFQ REJECTED
# =========================================================

def notify_rfq_rejected(
    vendor_account: str,
    rfq_id: str
):

    return insert_notification(

        vendor_account=vendor_account,

        notif_type="RFQ_REJECTED",

        title="RFQ Bid Rejected",

        message=(
            f"Your bid for "
            f"RFQ {rfq_id} "
            f"was not selected."
        ),

        reference_id=rfq_id,
    )





# # notification_service.py
# from app.services.notification_repo import insert_notification  # ← fix path


# # def notify_new_rfq(vendor_account: str, rfq_id: str, title: str):
# #     insert_notification(
# #         vendor_account = vendor_account,
# #         notif_type     = "NEW_RFQ",   # ← back to string, repo handles conversion
# #         title          = "New RFQ Received",
# #         message        = f"A new RFQ '{title}' ({rfq_id}) has been assigned to you.",
# #         reference_id          = rfq_id
# #     )
# def notify_new_rfq(vendor_account: str, rfq_id: str, rfq_name: str):
#     insert_notification(
#         vendor_account = vendor_account,
#         notif_type     = "NEW_RFQ",
#         title          = "New RFQ Received",
#         message        = f"A new RFQ {rfq_id} - '{rfq_name}' has been assigned to you.",
#         reference_id   = rfq_id
#     )
# def notify_rfq_expiring(vendor_account: str, rfq_id: str, expiry_date: str):
#     insert_notification(
#         vendor_account = vendor_account,
#         notif_type     = "RFQ_EXPIRING",  # ← string
#         title          = "RFQ Expiring Tomorrow",
#         message        = f"RFQ {rfq_id} expires on {expiry_date}. Please submit your bid.",
#         reference_id          = rfq_id
#     )

# def notify_po_confirmed(vendor_account: str, po_number: str):
#     insert_notification(
#         vendor_account = vendor_account,
#         notif_type     = "PO_CONFIRMED",  # ← string
#         title          = "Purchase Order Confirmed",
#         message        = f"PO {po_number} has been confirmed. Please review.",
#         reference_id           = po_number
#     )

# def notify_rfq_accepted(vendor_account: str, rfq_id: str):
#     insert_notification(
#         vendor_account = vendor_account,
#         notif_type     = "RFQ_ACCEPTED",  # ← string
#         title          = "RFQ Bid Accepted",
#         message        = f"Your bid for RFQ {rfq_id} has been accepted!",
#         reference_id     = rfq_id
#     )

# def notify_rfq_rejected(vendor_account: str, rfq_id: str):
#     insert_notification(
#         vendor_account = vendor_account,
#         notif_type     = "RFQ_REJECTED",  # ← string
#         title          = "RFQ Bid Rejected",
#         message        = f"Your bid for RFQ {rfq_id} was not selected.",
#         reference_id        = rfq_id
#     )