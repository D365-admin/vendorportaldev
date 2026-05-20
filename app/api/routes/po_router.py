from fastapi import APIRouter, Depends
from app.services import po_service
from app.schemas.rfq_schema import VendorRFQRequest
from app.core.security import get_current_vendor

router = APIRouter(prefix="/po", tags=["PO"])


@router.post("/list")
def get_po_list(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    data = po_service.get_po_list(vendor_account)

    return {
        "status": "success",
        "count": len(data),
        "po_list": data
    }


@router.post("/kpi")
def get_po_kpi(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    data = po_service.get_vendor_po_kpi(vendor_account)

    return {
        "status": "success",
        "data": data
    }

# from fastapi import APIRouter
# from pydantic import BaseModel
# from app.services import po_service
# from app.schemas.rfq_schema import VendorRFQRequest
# router = APIRouter(prefix="/po", tags=["PO"])


# @router.post("/list")
# def get_po_list(payload: VendorRFQRequest):
#     data = po_service.get_po_list(payload.vendor_account)

#     return {
#         "status": "success",
#         "count": len(data),
#         "po_list": data
#     }

# @router.post("/kpi")
# def get_po_list(payload: VendorRFQRequest):
#     data = po_service.get_vendor_po_kpi(payload.vendor_account)

#     return {
#         "status": "success",
#         "count": len(data),
#         "po_list": data
#     }