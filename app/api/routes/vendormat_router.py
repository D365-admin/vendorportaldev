from fastapi import APIRouter, Depends
from app.schemas.vendormat_schema import VendorMaterialRequest
from app.services.vendormaterial_service import fetch_bid_materials, fetch_vendor_profile
from app.core.security import get_current_vendor

router = APIRouter(prefix="/vendor", tags=["Vendor"])


@router.post("/bid-materials")
def get_bid_materials(
    payload: VendorMaterialRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    materials = fetch_bid_materials(vendor_account)

    return {
        "status": "success",
        "count": len(materials),
        "materials": materials
    }


@router.post("/profile")
def get_vendor_profile(
    payload: VendorMaterialRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    profile = fetch_vendor_profile(vendor_account)

    return {
        "status": "success",
        "vendor_account": vendor_account,
        "profile": profile
    }

# from fastapi import APIRouter
# from app.schemas.vendormat_schema import VendorMaterialRequest
# from app.services.vendormaterial_service import fetch_bid_materials,fetch_vendor_profile
# router = APIRouter(prefix="/vendor", tags=["Vendor"])


# @router.post("/bid-materials")
# def get_bid_materials(payload: VendorMaterialRequest):

#     materials = fetch_bid_materials(payload.vendor_account)

#     return {
#         "status": "success",
#         "count": len(materials),
#         "materials": materials
#     }


# @router.post("/profile")
# def get_vendor_profile(payload: VendorMaterialRequest):

#     profile = fetch_vendor_profile(payload.vendor_account)

#     return {
#         "status": "success",
#         "vendor_account": payload.vendor_account,
#         "profile": profile
#     }