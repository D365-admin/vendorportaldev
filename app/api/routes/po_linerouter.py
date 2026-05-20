from fastapi import APIRouter, HTTPException, Depends
from app.services.po_lineservice import get_po_details
from app.schemas.po_lineschema import PoDetailRequest
from app.core.security import get_current_vendor   

router = APIRouter(prefix="/po", tags=["PO"])


@router.post("/details")
def get_po_linedetails(
    payload: PoDetailRequest,
    user = Depends(get_current_vendor)   # TOKEN VALIDATION
):
    try:
        # ✅ Get vendor from token (NOT from payload)
        vendor_account = user.get("vendor_account")

        data = get_po_details(
            payload.purch_id,
            vendor_account   #SAFE
        )

        if not data:
            raise HTTPException(status_code=404, detail="PO not found")

        return {
            "status": "success",
            "data": data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# from fastapi import APIRouter, HTTPException
# from app.services.po_lineservice import get_po_details
# from app.schemas.po_lineschema import PoDetailRequest
# router = APIRouter(prefix="/po", tags=["PO"])

# @router.post("/details")
# def get_po_linedetails(payload: PoDetailRequest):

#     data = get_po_details(
#         payload.purch_id,
#         payload.vendor_account
#     )

#     if not data:
#         raise HTTPException(status_code=404, detail="PO not found")

#     return {
#         "status": "success",
#         "data": data
#     }