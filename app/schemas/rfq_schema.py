from pydantic import BaseModel

class VendorRFQRequest(BaseModel):
    pass

class notifyid(BaseModel):
    notify_id: int
    
#  from pydantic import BaseModel

# class VendorRFQRequest(BaseModel):
#     vendor_account: str 

# class notifyid(BaseModel):
#     notify_id:int