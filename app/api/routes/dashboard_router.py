from fastapi import APIRouter, HTTPException, Depends
from app.services.dashboard_service import (
    fetch_dashboard_metrics,
    fetch_rfq_summary,
    fetch_rfq_counts
)
from app.schemas.rfq_schema import VendorRFQRequest
from app.core.security import get_current_vendor  

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ─────────────────────────────────────────────
# Dashboard Counts
# ─────────────────────────────────────────────
@router.post("/counts")
def get_dashboard_counts(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)   
):
    try:
        # ✅ ALWAYS take vendor_account from token (NOT payload)
        vendor_account = user.get("vendor_account")

        result = fetch_dashboard_metrics(vendor_account)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# RFQ Summary
# ─────────────────────────────────────────────
@router.post("/rfq-summary")
def get_rfq_summary(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)  
):
    try:
        vendor_account = user.get("vendor_account")

        summary = fetch_rfq_summary(vendor_account)

        return {
            "status": "success",
            "summary": summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# RFQ Counts
# ─────────────────────────────────────────────
@router.post("/rfqcounts")
def get_rfq_counts(
    payload: VendorRFQRequest,
    user = Depends(get_current_vendor)   
):
    try:
        vendor_account = user.get("vendor_account")

        return fetch_rfq_counts(vendor_account)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# from fastapi import APIRouter, Query, HTTPException
# from app.services.dashboard_service import fetch_dashboard_metrics,fetch_rfq_summary
# from app.schemas.rfq_schema import VendorRFQRequest
# from app.services.dashboard_service import fetch_rfq_counts
# router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# @router.post("/counts")
# def get_dashboard_counts(
#     payload:VendorRFQRequest
# ):
#     try:
#         result = fetch_dashboard_metrics(payload.vendor_account)
#         return result
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @router.post("/rfq-summary")
# def get_rfq_summary(payload:VendorRFQRequest):
#     """
#     RFQ Summary KPIs:
#     - Total Active RFQs
#     - RFQs Closing Soon (3 days)
#     - Awaiting Confirmation
#     - Submitted Bids
#     """
#     summary = fetch_rfq_summary(payload.vendor_account)
#     return {
#         "status":  "success",
#         "summary": summary
#     }

# @router.post("/rfqcounts")
# def get_rfq_counts(payload:VendorRFQRequest):
#     return fetch_rfq_counts(payload.vendor_account)