from fastapi import APIRouter,Depends
from app.services.dropdownservice import fetch_rfq_dropdowns
from app.core.security import get_current_vendor 
router=APIRouter(prefix="/dropdown",tags=["Dropdownlist"])

@router.post("/list")
def dropdown(user = Depends(get_current_vendor)): 
# def dropdown():
    data=fetch_rfq_dropdowns()
    return data 
    
