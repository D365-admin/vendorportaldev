
from __future__ import annotations

from pydantic import BaseModel, Field


class RequestOtpRequest(BaseModel):
    EMAIL: str


class VerifyOtpRequest(BaseModel):
    EMAIL: str

    OTP: str = Field(
        ...,
        min_length=6,
        max_length=6,
    )


# from __future__ import annotations

# from pydantic import BaseModel, EmailStr, Field


# class RequestOtpRequest(BaseModel):
#     EMAIL: EmailStr = Field(
#         ...,
#         description=(
#             "Email address registered in "
#             "d365_VendorProspect"
#         ),
#         examples=["vendor@example.com"],
#     )


# class VerifyOtpRequest(BaseModel):
#     EMAIL: EmailStr = Field(
#         ...,
#         description=(
#             "Email address used when requesting OTP"
#         ),
#         examples=["vendor@example.com"],
#     )

#     OTP: str = Field(
#         ...,
#         min_length=6,
#         max_length=6,
#         description="Six-digit OTP",
#         examples=["430237"],
#     )