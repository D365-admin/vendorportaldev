from typing import List, Optional, Any
from pydantic import BaseModel, Field

class RFQItemReply(BaseModel):
    itemNumber: str       # Material Code e.g. "HRC IS:1079"
    lineNumber: int       # SI No from frontend e.g. 1, 2
    quantity: float
    unitOfMeasure: str
    unitPrice: float
    netAmount: float
    vendorComments: Optional[str] = ""
    lineStatus: Optional[bool] = False
    deliveryDate: Optional[str] = None 

class RFQReplyPayload(BaseModel):
    rfqCaseId: str
    documentTitle: Optional[str] = ""
    rfqId: str
    expiryDate: str                        # ← remove Optional, make required
    receiptDate: Optional[str] = None
    modeOfDelivery: Optional[str] = None
    DeliveryTerms: Optional[Any] = None
    methodOfPayment: Optional[str] = None
    termsOfPayment: Optional[Any] = None
    currency: Optional[str] = None
    vendorAccount: Optional[str] = None
    bidType: Optional[str] = None
    isSealed: Optional[bool] = False
    Item: List[RFQItemReply] = Field(default_factory=list)
    vendorComments: Optional[str] = ""
    replyDeliveryTerms: Optional[str] = None
    replyDeliveryDate: Optional[str] = None
    replyModeOfDelivery: Optional[str] = None
    confirmSave: Optional[str] = None
 