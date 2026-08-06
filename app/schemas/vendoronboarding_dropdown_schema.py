from pydantic import BaseModel

class StateDropdown(BaseModel):
    country: str

class CityDropdown(BaseModel):
    country: str
    state: str

class ZipDropdown(BaseModel):
    country: str