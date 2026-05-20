from fastapi import APIRouter, Depends
from app.schemas.rfq_schema import VendorRFQRequest
from app.services.rfq_inprogressservice import fetch_inprogress_rfqs
from app.core.security import get_current_vendor

router = APIRouter(prefix="/inprog", tags=["RFQS"])


@router.post("/inprogress")
def get_inprogress_rfqs(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    rfqs = fetch_inprogress_rfqs(vendor_account)

    return {
        "status": "success",
        "rfqs": rfqs,
        "count": len(rfqs)
    }
# from app.schemas.rfq_schema import VendorRFQRequest
# from fastapi import APIRouter
# from app.services.rfq_inprogressservice import fetch_inprogress_rfqs

# router=APIRouter(prefix="/inprog",tags=["RFQS"])


# @router.post("/inprogress")
# def get_inprogress_rfqs(payload:VendorRFQRequest):
#     """
#     RFQs where vendor has started filling / saved reply
#     but expiry not yet passed (still in progress)
#     """
#     rfqs = fetch_inprogress_rfqs(payload.vendor_account)
#     return {
#         "status": "success",
#         "rfqs":   rfqs,
#         "count":  len(rfqs)
#     }