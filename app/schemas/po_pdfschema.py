# from pydantic import BaseModel
# class popdfschema(BaseModel):
#     vendAccount:str 
#     confirmed:str
#     purchId:str 
from pydantic import BaseModel

class popdfschema(BaseModel):
    # confirmed: str
    purchId: str