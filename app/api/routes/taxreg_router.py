from fastapi import APIRouter
from app.schemas.taxreg_schema import taxreg
from app.services.vendoronboard.taxregistrationcheck_services import tax_registration_check

router = APIRouter()

@router.post("/tax-registration-check")
def check_tax_registration(tax_reg: taxreg):
    return tax_registration_check(tax_reg.tax_registration_number)