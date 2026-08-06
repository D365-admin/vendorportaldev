from __future__ import annotations

import logging
from typing import Any

import pyodbc
from fastapi import (
    APIRouter,
    status,
)
from fastapi.responses import JSONResponse

from app.schemas.vendoronboarding_loginschema import (
    RequestOtpRequest,
    VerifyOtpRequest,
)
from app.services.vendoronboard.loginonboarding import (
    DuplicateVendorEmailError,
    OtpValidationError,
    VendorNotFoundError,
    request_vendor_otp,
    verify_vendor_otp,
)


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/vendor-auth",
    tags=["Vendor Authentication"],
)


# ============================================================
# ERROR RESPONSE
# ============================================================

def _error_response(
    status_code: int,
    message: str,
    errors: list[Any] | None = None,
) -> JSONResponse:

    content: dict[str, Any] = {
        "SUCCESS": False,
        "MESSAGE": message,
    }

    if errors:
        content["ERRORS"] = errors

    return JSONResponse(
        status_code=status_code,
        content=content,
    )


# ============================================================
# REQUEST OTP
# ============================================================

@router.post(
    "/request-otp",
    summary="Request vendor login OTP",
    description=(
        "Checks the email in d365_VendorProspect, "
        "generates a six-digit OTP, stores the OTP "
        "directly in HIQ_VendorOTP and sends it by email."
    ),
    status_code=status.HTTP_200_OK,
    response_model=None,
)
def request_otp(
    payload: RequestOtpRequest,
):
    try:
        return request_vendor_otp(
            email=str(payload.EMAIL)
        )

    except VendorNotFoundError as exc:
        return _error_response(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            message=str(exc),
        )

    except DuplicateVendorEmailError as exc:
        return _error_response(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            message=str(exc),
        )

    except OtpValidationError as exc:
        return _error_response(
            status_code=(
                status.HTTP_429_TOO_MANY_REQUESTS
            ),
            message=str(exc),
        )

    except pyodbc.IntegrityError:
        logger.exception(
            "Database integrity error while creating OTP"
        )

        return _error_response(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            message=(
                "Unable to create OTP because of "
                "a database conflict"
            ),
        )

    except pyodbc.Error:
        logger.exception(
            "Database error while requesting OTP"
        )

        return _error_response(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            message=(
                "Database error while requesting OTP"
            ),
        )

    except Exception:
        logger.exception(
            "Unexpected error while requesting OTP"
        )

        return _error_response(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            message="Unable to send OTP",
        )


# ============================================================
# VERIFY OTP
# ============================================================

@router.post(
    "/verify-otp",
    summary="Verify vendor login OTP",
    description=(
        "Verifies the OTP stored in HIQ_VendorOTP. "
        "After successful verification, it marks the OTP "
        "as used, generates a JWT token and returns vendor "
        "prospect information."
    ),
    status_code=status.HTTP_200_OK,
    response_model=None,
)
def verify_otp(
    payload: VerifyOtpRequest,
):
    try:
        return verify_vendor_otp(
            email=str(payload.EMAIL),
            otp=payload.OTP,
        )

    except VendorNotFoundError as exc:
        return _error_response(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            message=str(exc),
        )

    except DuplicateVendorEmailError as exc:
        return _error_response(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            message=str(exc),
        )

    except OtpValidationError as exc:
        return _error_response(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            message=str(exc),
        )

    except pyodbc.Error:
        logger.exception(
            "Database error while verifying OTP"
        )

        return _error_response(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            message=(
                "Database error while verifying OTP"
            ),
        )

    except Exception:
        logger.exception(
            "Unexpected error while verifying OTP"
        )

        return _error_response(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            message="Unable to verify OTP",
        )