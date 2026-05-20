from fastapi import APIRouter, Depends
from app.schemas.rfq_detailschema import VendorRFQDetailRequest
from app.services.rfq_expiredlineservice import fetch_rfq_detail
from app.core.security import get_current_vendor

router = APIRouter(prefix="/expiry", tags=["RFQS"])


@router.post("/expired-detail")
def get_expired_rfq_detail(
    payload: VendorRFQDetailRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    return fetch_rfq_detail(
        payload.rfq_id,
        vendor_account
    )



# from app.schemas.rfq_detailschema import VendorRFQDetailRequest
# from fastapi import APIRouter
# from app.services.rfq_expiredlineservice import fetch_rfq_detail

# router=APIRouter(prefix="/expiry",tags=["RFQS"])

# @router.post("/expired-detail")
# def get_submitted_rfq_detail(payload:VendorRFQDetailRequest):
#     """API 2 — Detail view with all lines + HiQ decision"""
#     return fetch_rfq_detail(payload.rfq_id,payload.vendor_account)
