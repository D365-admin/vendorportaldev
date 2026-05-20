from fastapi import APIRouter, Depends
from app.schemas.rfq_schema import VendorRFQRequest
from app.schemas.rfq_detailschema import VendorRFQDetailRequest
from app.services.rfq_submissionservice import fetch_submitted_rfqs, fetch_submitted_rfq_detail
from app.core.security import get_current_vendor

router = APIRouter(prefix="/sub", tags=["RFQS"])


@router.post("/submitted")
def get_submitted_rfqs(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    rfqs = fetch_submitted_rfqs(vendor_account)

    return {
        "status": "success",
        "rfqs": rfqs,
        "count": len(rfqs)
    }


@router.post("/completed-detail")
def get_submitted_rfq_detail(
    payload: VendorRFQDetailRequest,
    user = Depends(get_current_vendor)
):
    vendor_account = user.get("vendor_account")

    return fetch_submitted_rfq_detail(
        payload.rfq_id,
        vendor_account
    )

# from fastapi import APIRouter
# from app.schemas.rfq_schema import VendorRFQRequest
# from app.schemas.rfq_detailschema import VendorRFQDetailRequest
# from app.services.rfq_submissionservice import fetch_submitted_rfqs,fetch_submitted_rfq_detail
# from fastapi import APIRouter
# router=APIRouter(prefix="/sub",tags=["RFQS"])

# @router.post("/submitted")
# def get_submitted_rfqs(payload:VendorRFQRequest):
#     """
#     Submitted tab — SUBMISSION_STATUS = 1 (SENT to D365)
#     Shows: RFQ No, Submitted Date, Bid Value, Delivery Date, Mode, Term
#     """
#     rfqs = fetch_submitted_rfqs(payload.vendor_account)
#     return {
#         "status": "success",
#         "rfqs":   rfqs,
#         "count":  len(rfqs)
#     }

# @router.post("/completed-detail")
# def get_submitted_rfq_detail(payload:VendorRFQDetailRequest):
#     """API 2 — Detail view with all lines + HiQ decision"""
#     return fetch_submitted_rfq_detail(payload.rfq_id,payload.vendor_account)