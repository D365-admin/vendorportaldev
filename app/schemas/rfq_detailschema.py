# from pydantic import BaseModel
 
# class VendorRFQDetailRequest(BaseModel):
#     vendor_account: str
#     rfq_id:str 


from pydantic import BaseModel

class VendorRFQDetailRequest(BaseModel):
    rfq_id: str