from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from jose import jwt
from datetime import datetime, timedelta, timezone

from app.services import auth_service
from app.schemas.auth_schema import (
    AdminCreateVendorReq,
    IdentifierReq,
    SetPasswordReq,
    LoginReq,
    OtpSendReq,
    OtpVerifyReq
)

from app.core.config import settings
from app.core.security import create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


# =========================================================
# SEND SET PASSWORD LINK
# =========================================================

@router.post("/send-set-password-link")
def send_set_password_link(payload: IdentifierReq):
    return auth_service.send_set_password_link(
        payload.identifier
    )


# =========================================================
# FORGOT PASSWORD
# =========================================================

@router.post("/forgot-password")
def forgot_password(payload: IdentifierReq):
    return auth_service.forgot_password(
        payload.identifier
    )


# =========================================================
# LOGIN WITH PASSWORD
# =========================================================

@router.post("/login")
def login(payload: LoginReq, request: Request):

    ip = (
        request.client.host
        if request.client
        else None
    )

    return auth_service.login_with_password(
        payload.identifier,
        payload.password,
        ip
    )


# =========================================================
# SEND LOGIN OTP
# =========================================================

@router.post("/otp/send")
def otp_send(payload: OtpSendReq):

    return auth_service.send_login_otp(
        payload.identifier,
        payload.channel
    )


# =========================================================
# VERIFY LOGIN OTP
# =========================================================

@router.post("/otp/verify")
def verify_otp(
    payload: OtpVerifyReq,
    request: Request
):

    ip = (
        request.client.host
        if request.client
        else None
    )

    result = auth_service.verify_login_otp(
        identifier=payload.identifier,
        channel=payload.channel,
        otp_code=payload.otp_code,
        ip=ip
    )

    if not result["ok"]:
        return result

    # GET TOKENS
    refresh_token = result["refresh_token"]

    # RESPONSE
    response = JSONResponse(
        content={
            "ok": True,
            "access_token": result["access_token"],
            "data": result["data"]
        }
    )

    # SET COOKIE
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,   # TRUE in HTTPS production
        samesite="Lax",
        path="/",
        max_age=7 * 24 * 60 * 60,
        expires=datetime.now(timezone.utc) + timedelta(days=7)
    )

    return response


# =========================================================
# ADMIN CREATE VENDOR
# =========================================================

@router.post("/admin/create-vendor")
def admin_create_vendor(payload: AdminCreateVendorReq):

    return auth_service.admin_create_vendor(
        payload.vendor_account,
        payload.email,
        payload.phone
    )


# =========================================================
# START SET PASSWORD
# =========================================================

@router.post("/set-password/start")
def start_set_password(payload: IdentifierReq):

    return auth_service.start_set_password(
        payload.identifier
    )


# =========================================================
# VERIFY SET PASSWORD OTP
# =========================================================

@router.post("/set-password/verify-otp")
def verify_set_password_otp(payload: OtpVerifyReq):

    return auth_service.verify_set_password_otp(
        payload.identifier,
        payload.otp_code
    )


# =========================================================
# CONFIRM SET PASSWORD
# =========================================================

@router.post("/set-password/confirm")
def set_password(
    payload: SetPasswordReq,
    request: Request
):

    ip = (
        request.client.host
        if request.client
        else None
    )

    result = auth_service.set_password_after_otp(
        payload.identifier,
        payload.new_password,
        ip
    )

    print("SET PASSWORD RESULT:", result)

    if not result["ok"]:
        return result

    # IMPORTANT
    refresh_token = result["refresh_token"]

    # RESPONSE
    response = JSONResponse(
        content={
            "ok": True,
            "message": result["message"],
            "access_token": result["access_token"],
            "data": result["data"]
        }
    )

    # SET COOKIE
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,   # TRUE in HTTPS production
        samesite="Lax",
        path="/",
        max_age=7 * 24 * 60 * 60,
        expires=datetime.now(timezone.utc) + timedelta(days=7)
    )

    return response


# =========================================================
# REFRESH ACCESS TOKEN
# =========================================================

@router.post("/refresh")
def refresh_token(request: Request):

    refresh_token = request.cookies.get(
        "refresh_token"
    )

    # print("COOKIE RECEIVED:", refresh_token)

    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token missing"
        )

    try:

        payload = jwt.decode(
            refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        print("DECODED PAYLOAD:", payload)

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401,
                detail="Invalid token type"
            )

        new_access_token = create_access_token({
            "sub": payload["sub"],
            "vendor_account": payload.get(
                "vendor_account"
            ),
            "email": payload.get("email"),
            "role": payload.get("role")
        })

        return {
            "ok": True,
            "access_token": new_access_token
        }

    except Exception as e:

        print("REFRESH ERROR:", str(e))

        raise HTTPException(
            status_code=401,
            detail=f"Error: {str(e)}"
        )


# =========================================================
# LOGOUT
# =========================================================

@router.post("/logout")
def logout():

    response = JSONResponse(
        content={
            "ok": True,
            "message": "Logged out successfully"
        }
    )

    response.delete_cookie(
        key="refresh_token",
        path="/"
    )

    return response

# from fastapi import APIRouter, Request
# from pydantic import BaseModel
# from app.services import auth_service
# from app.schemas.auth_schema import AdminCreateVendorReq,IdentifierReq,SetPasswordReq,LoginReq,OtpSendReq,OtpVerifyReq 
# from jose import jwt
# from fastapi import HTTPException
# from app.core.config import settings
# from app.core.security import create_access_token
# from fastapi.responses import JSONResponse
# from fastapi import Response
# from fastapi.responses import JSONResponse
# from datetime import datetime,timedelta,timezone
# router = APIRouter(prefix="/auth", tags=["Auth"])


# @router.post("/send-set-password-link")
# def send_set_password_link(payload: IdentifierReq):
#     return auth_service.send_set_password_link(payload.identifier)


# # @router.post("/forgot-password")
# # def forgot_password(payload: IdentifierReq):
# #     return auth_service.forReq, request: Request)got_password(payload.identifier)


# @router.post("/login")
# def login(payload: LoginReq, request: Request):
#     ip = request.client.host if request.client else None
#     return auth_service.login_with_password(payload.identifier, payload.password, ip)

# @router.post("/otp/send")
# def otp_send(payload: OtpSendReq):
#     return auth_service.send_login_otp(payload.identifier, payload.channel)
# @router.post("/otp/verify")
# def verify_otp(
#     payload: OtpVerifyReq,
#     response: Response,
#     request: Request
# ):

#     ip = request.client.host if request.client else None

#     result = auth_service.verify_login_otp(
#         identifier=payload.identifier,
#         channel=payload.channel,
#         otp_code=payload.otp_code,
#         ip=ip
#     )

#     if not result["ok"]:
#         return result

#     # IMPORTANT
#     refresh_token = result["refresh_token"]

#     response = JSONResponse(content={
#         "ok": True,
#         "access_token": result["access_token"],
#         "data": result["data"]
#     })

#     response.set_cookie(
#         key="refresh_token",
#         value=refresh_token,
#         httponly=True,
#         secure=False,
#         samesite="Lax",
#         path="/",
#         max_age=7 * 24 * 60 * 60,
#         expires=datetime.now(timezone.utc) + timedelta(days=7)
#     )

#     return response
# # @router.post("/otp/verify")
# # def verify_otp(
# #     payload: OtpVerifyReq,
# #     response: Response,
# #     request: Request
# # ):

# #     ip = request.client.host if request.client else None

# #     result = auth_service.verify_login_otp(
# #         identifier=payload.identifier,
# #         channel=payload.channel,
# #         otp_code=payload.otp_code,
# #         ip=ip
# #     )

# #     if not result["ok"]:
# #         return result

# #     # refresh_token = result.pop("refresh_token")
# #     response=JSONResponse(content={"ok":True,"access_token":result["access_token"],"data":result["data"]})
# #     response.set_cookie(
# #         key="refresh_token",
# #         value=refresh_token,
# #         httponly=True,
# #         secure=False,   # TRUE in production HTTPS
# #         samesite=None,
# #         # "Lax",
# #         path="/",
# #         max_age=7 * 24 * 60 * 60,
# #         expires=datetime.now(timezone.utc)+timedelta(days=7)
# #         )

# #     return response
# @router.post("/admin/create-vendor")
# def admin_create_vendor(payload: AdminCreateVendorReq):
#     """
#     Admin adds a new vendor to the portal.
#     Automatically sends 'Set Your Password' welcome email.

#     Steps:
#     1. POST this with vendor_account + email
#     2. Vendor receives email with set-password link
#     3. Vendor clicks link → sets password → can login
#     """
#     return auth_service.admin_create_vendor(
#         payload.vendor_account,
#         payload.email,
#         payload.phone
#     )

# @router.post("/set-password/start")
# def start_set_password(payload: IdentifierReq):
#     return auth_service.start_set_password(payload.identifier)


# @router.post("/set-password/verify-otp")
# def verify_set_password_otp(payload: OtpVerifyReq):
#     return auth_service.verify_set_password_otp(
#         payload.identifier,
#         payload.otp_code
#     )


# from fastapi import (
#     Response,
#     Request
# )
# @router.post("/set-password/confirm")
# def set_password(
#     payload: SetPasswordReq,
#     request: Request
# ):

#     ip = (
#         request.client.host
#         if request.client
#         else None
#     )

#     result = auth_service.set_password_after_otp(
#         payload.identifier,
#         payload.new_password,
#         ip
#     )

#     if not result["ok"]:
#         return result

#     # GET REFRESH TOKEN
#     refresh_token = result["refresh_token"]

#     # CREATE RESPONSE
#     response = JSONResponse(
#         content={
#             "ok": True,
#             "message": result["message"],
#             "access_token": result["access_token"],
#             "data": result["data"]
#         }
#     )

#     # SET REFRESH TOKEN COOKIE
#     response.set_cookie(
#         key="refresh_token",
#         value=refresh_token,
#         httponly=True,
#         secure=False,   # True in HTTPS production
#         samesite="Lax",
#         path="/",
#         max_age=7 * 24 * 60 * 60,
#         expires=datetime.now(timezone.utc) + timedelta(days=7)
#     )

#     return response
# # @router.post("/set-password/confirm")
# # def set_password(
# #     payload: SetPasswordReq,
# #     request: Request
# # ):

# #     ip = (
# #         request.client.host
# #         if request.client
# #         else None
# #     )

# #     result = auth_service.set_password_after_otp(
# #         payload.identifier,
# #         payload.new_password,
# #         ip
# #     )

# #     if not result["ok"]:
# #         return result

# #     # ============================================
# #     # REMOVE REFRESH TOKEN FROM JSON
# #     # ============================================

# #     # refresh_token = result.pop(
# #     #     "_refresh_token"
# #     # )

# #     # ============================================
# #     # CREATE RESPONSE
# #     # ============================================

# #     response = JSONResponse(
# #         content={
# #             "ok": True,

# #             "message":
# #                 result["message"],

# #             "access_token":
# #                 result["access_token"],

# #             "data":
# #                 result["data"]
# #         }
# #     )

# #     # ============================================
# #     # SET REFRESH TOKEN COOKIE
# #     # ============================================

# #     response.set_cookie(
# #         key="refresh_token",

# #         value=refresh_token,

# #         httponly=True,

# #         secure=False,   # TRUE in production HTTPS

# #         samesite=None,

# #         path="/",

# #         max_age=7 * 24 * 60 * 60
# #     )

# #     return response

# @router.post("/refresh")
# def refresh_token(request: Request):
 
 
#     refresh_token = request.cookies.get("refresh_token")
 
#     print("COOKIE RECEIVED:", refresh_token)  # ← ADD THIS
 
#     if not refresh_token:
#         raise HTTPException(status_code=401, detail="Refresh token missing")
 
#     try:
#         payload = jwt.decode(
#             refresh_token,
#             settings.JWT_SECRET_KEY,
#             algorithms=[settings.JWT_ALGORITHM]
#         )
 
#         print("DECODED PAYLOAD:", payload)  # ← ADD THIS
 
#         if payload.get("type") != "refresh":
#             raise HTTPException(status_code=401, detail="Invalid token")
 
#         new_access_token = create_access_token({
#             "sub": payload["sub"],
#             "vendor_account": payload.get("vendor_account"),
#             "email": payload.get("email"),
#             "role": payload.get("role")
#         })
 
#         return {"ok": True, "access_token": new_access_token}
 
#     except Exception as e:
#         print("REFRESH ERROR:", str(e))  # ← ADD THIS
#         raise HTTPException(status_code=401, detail=f"Error: {str(e)}")
 
# # @router.post("/refresh")
# # def refresh_token(request: Request):

# #     refresh_token = request.cookies.get("refresh_token")
# #     print(refresh_token)
# #     if not refresh_token:
# #         raise HTTPException(
# #             status_code=401,
# #             detail="Refresh token missing"
# #         )

# #     try:

# #         payload = jwt.decode(
# #             refresh_token,
# #             settings.JWT_SECRET_KEY,
# #             algorithms=[settings.JWT_ALGORITHM]
# #         )

# #         if payload.get("type") != "refresh":
# #             raise HTTPException(
# #                 status_code=401,
# #                 detail="Invalid token"
# #             )

# #         new_access_token = create_access_token({
# #             "sub": payload["sub"],
# #             "vendor_account": payload.get("vendor_account"),
# #             "email": payload.get("email"),
# #             "role": payload.get("role")
# #         })

# #         return {
# #             "ok": True,
# #             "access_token": new_access_token
# #         }

# #     except Exception as e:
# #         print("refresh error",str(e))
# #         raise HTTPException(
# #             status_code=401,
# #             detail="Invalid or expired refresh token"
# #         )
    
# @router.post("/logout")
# def logout():

#     response = JSONResponse(content={
#         "ok": True,
#         "message": "Logged out successfully"
#     })

#     response.delete_cookie("refresh_token")

#     return response

  
# # @router.post("/refresh")
# # def refresh_token(refresh_token: str):
# #     try:
# #         payload = jwt.decode(
# #             refresh_token,
# #             settings.JWT_SECRET_KEY,
# #             algorithms=[settings.JWT_ALGORITHM]
# #         )

# #         if payload.get("type") != "refresh":
# #             raise HTTPException(status_code=401, detail="Invalid token")

# #         new_access_token = create_access_token({
# #             "sub": payload["sub"],
# #             "vendor_account": payload.get("vendor_account"),
# #             "email": payload.get("email"),
# #             "role": payload.get("role")
# #         })

# #         return {"access_token": new_access_token}

# #     except Exception:
# #         raise HTTPException(status_code=401, detail="Invalid or expired refresh token")