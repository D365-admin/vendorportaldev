from fastapi import APIRouter, Depends
from app.schemas.rfq_detailschema import VendorRFQDetailRequest
from app.services.rfq_linefetchservice import fetch_rfq_detail
from app.core.security import get_current_vendor

router = APIRouter(prefix="/rfqfetch", tags=["RFQS"])


@router.post("/rfq-detail")
def get_rfq_detail(
    payload: VendorRFQDetailRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    return fetch_rfq_detail(
        payload.rfq_id,
        vendor_account
    )
# from app.schemas.rfq_detailschema import VendorRFQDetailRequest
# from app.services.rfq_linefetchservice import fetch_rfq_detail
# from fastapi import APIRouter
# router = APIRouter(prefix="/rfqfetch", tags=["RFQS"])

# @router.post("/rfq-detail")
# def get_rfq_detail(payload:VendorRFQDetailRequest):
#     """
#     Input: rfq_id, vendor_account
#     """
#     return fetch_rfq_detail(payload.rfq_id,payload.vendor_account)