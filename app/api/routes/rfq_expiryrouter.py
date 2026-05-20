from fastapi import APIRouter, Depends
from app.schemas.rfq_schema import VendorRFQRequest
from app.services.rfq_expiryservice import fetch_vendor_expired_rfqs
from app.core.security import get_current_vendor

router = APIRouter(prefix="/expiry", tags=["RFQS"])


@router.post("/expired")
def get_expired_rfqs(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    rfqs = fetch_vendor_expired_rfqs(vendor_account)

    return {
        "status": "success",
        "rfqs": rfqs,
        "count": len(rfqs)
    }
# from app.schemas.rfq_schema import VendorRFQRequest
# from app.services.rfq_expiryservice import fetch_vendor_expired_rfqs
# from fastapi import APIRouter
# router = APIRouter(prefix="/expiry", tags=["RFQS"])

# @router.post("/expired")
# def get_expired_rfqs(payload:VendorRFQRequest):
#     """
#     RFQs where expiry passed and vendor never submitted a bid
#     """
#     rfqs = fetch_vendor_expired_rfqs(payload.vendor_account)
#     return {
#         "status": "success",
#         "rfqs":   rfqs,
#         "count":  len(rfqs)
#     }  