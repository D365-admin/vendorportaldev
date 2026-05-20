from fastapi import APIRouter, Depends
from app.services.notification_repo import (
    get_unread_notifications,
    get_all_notifications,
    get_unread_count,
    mark_notification_read,
    mark_all_read,
    delete_all_read,
)
from app.schemas.rfq_schema import notifyid
from app.core.security import get_current_vendor


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)


@router.get("/count")
def unread_count(
    user=Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    return {
        "unread_count": get_unread_count(vendor_account)
    }


@router.post("/unread")
def unread(
    user=Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    items = get_unread_notifications(vendor_account)

    return {
        "count": len(items),
        "notifications": items,
    }


@router.post("/all")
def all_notifications(
    user=Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    items = get_all_notifications(vendor_account)

    return {
        "notifications": items
    }


@router.post("/read")
def read_one(
    payload: notifyid,
    user=Depends(get_current_vendor)
):
    mark_notification_read(payload.notify_id)

    return {
        "status": "OK"
    }


@router.post("/read-all")
def read_all(
    user=Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    mark_all_read(vendor_account)

    return {
        "status": "OK"
    }


@router.delete("/clear-read")
def clear_read(
    user=Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    delete_all_read(vendor_account)

    return {
        "status": "OK"
    }


# from fastapi import APIRouter, Query
# from app.services.notification_repo import (
#     get_unread_notifications,
#     get_all_notifications,
#     get_unread_count,
#     mark_notification_read,
#     mark_all_read,
#     delete_all_read
# )
# from app.schemas.rfq_schema import VendorRFQRequest,notifyid
# router = APIRouter(prefix="/notifications", tags=["Notifications"])


# @router.get("/count")
# def unread_count(vendor_account: str = Query(...)):
#     return {"unread_count": get_unread_count(vendor_account)}


# @router.post("/unread")
# def unread(payload:VendorRFQRequest):
#     items = get_unread_notifications(payload.vendor_account)
#     return {"count": len(items), "notifications": items}


# @router.post("/all")
# def all_notifications(payload:VendorRFQRequest):
#     items = get_all_notifications(payload.vendor_account)
#     return {"notifications": items}


# @router.post("/read")
# def read_one(payload:notifyid):
#     mark_notification_read(payload.notify_id)
#     return {"status": "OK"}


# @router.post("/read-all")
# def read_all(payload:VendorRFQRequest):
#     mark_all_read(payload.vendor_account)
#     return {"status": "OK"}


# @router.delete("/clear-read")
# def clear_read(payload:VendorRFQRequest):
#     delete_all_read(payload.vendor_account)
#     return {"status": "OK"}