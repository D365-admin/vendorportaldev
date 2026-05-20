from fastapi import APIRouter, Depends
from app.schemas.rfq_schema import VendorRFQRequest
from app.services.rfq_newservice import fetch_vendor_rfqs
from app.core.security import get_current_vendor

router = APIRouter(prefix="/rfqnew", tags=["RFQS"])

@router.post("/newrfqlist")
def get_vendor_rfq(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    data = fetch_vendor_rfqs(vendor_account)

    return {
        "status": "success",
        "rfqs": data,
        "count": len(data)
    }


# from fastapi import APIRouter
# from app.schemas.rfq_schema import VendorRFQRequest
# from app.services.rfq_newservice import fetch_vendor_rfqs

# router=APIRouter(prefix="/rfqnew",tags=["RFQS"])

# @router.post("/newrfqlist")
# def get_vendor_rfq(payload:VendorRFQRequest):
#     data=fetch_vendor_rfqs(payload.vendor_account)
#     return{
#         "status":"success",
#         "rfqs":data,
#         "count":len(data)
#     }
