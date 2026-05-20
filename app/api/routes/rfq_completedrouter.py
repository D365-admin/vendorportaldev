from fastapi import APIRouter, Depends
from app.services.rfq_completedservice import (
    fetch_completed_rfqs,
    fetch_completed_rfq_detail
)
from app.schemas.rfq_schema import VendorRFQRequest
from app.schemas.rfq_detailschema import VendorRFQDetailRequest
from app.core.security import get_current_vendor

router = APIRouter(prefix="/rfq", tags=["RFQS"])


@router.post("/completed")
def get_completed_rfqs(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    rfqs = fetch_completed_rfqs(vendor_account)

    return {
        "status": "success",
        "rfqs": rfqs,
        "count": len(rfqs)
    }


@router.post("/completed-detail")
def get_completed_rfq_detail(
    payload: VendorRFQDetailRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    return fetch_completed_rfq_detail(
        payload.rfq_id,
        vendor_account
    )


# from fastapi import APIRouter
# from app.services.rfq_completedservice import (
#     fetch_completed_rfqs,
#     fetch_completed_rfq_detail
# )
# from app.schemas.rfq_schema import VendorRFQRequest
# from app.schemas.rfq_detailschema import VendorRFQDetailRequest
# router = APIRouter(prefix="/rfq", tags=["RFQS"])


# @router.post("/completed")
# def get_completed_rfqs(payload:VendorRFQRequest):
#     """API 1 — List view"""
#     rfqs = fetch_completed_rfqs(payload.vendor_account)
#     return {"status": "success", "rfqs": rfqs, "count": len(rfqs)}


# @router.post("/completed-detail")
# def get_completed_rfq_detail(payload:VendorRFQDetailRequest):
#     """API 2 — Detail view with all lines + HiQ decision"""
#     return fetch_completed_rfq_detail(payload.rfq_id,payload.vendor_account)
