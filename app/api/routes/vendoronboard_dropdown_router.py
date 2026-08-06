from fastapi import APIRouter

from app.schemas.vendoronboarding_dropdown_schema import (
    StateDropdown,
    CityDropdown,
    ZipDropdown
)

from app.services.vendoronboard.dropdown_services import (
    company_address_country,
    company_address_state,
    company_address_city,
    company_address_zipcode
)

router = APIRouter(
    prefix="/dropdown",
    tags=["Company Address Dropdown"]
)


@router.get("/country")
def country():
    return company_address_country()


@router.post("/state")
def state(payload: StateDropdown):
    return company_address_state(payload.country)


@router.post("/city")
def city(payload: CityDropdown):
    return company_address_city(
        payload.country,
        payload.state
    )


@router.post("/zipcode")
def zipcode(payload: ZipDropdown):
    return company_address_zipcode(payload.country)