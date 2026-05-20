# from pydantic import BaseModel
# class PoDetailRequest(BaseModel):
#     purch_id: str
#     vendor_account: str

from pydantic import BaseModel

class PoDetailRequest(BaseModel):
    purch_id: str