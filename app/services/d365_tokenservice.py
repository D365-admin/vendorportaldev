import time
from threading import Lock
from fastapi import HTTPException
import msal

from app.core.config import settings

AUTHORITY = f"https://sndfs.hiqelectronics.com/{settings.AAD_TENANT_ID}/oauth2/token"
# f"https://login.microsoftonline.com/{settings.D365_TENANT_ID}"

SCOPE = [f"{settings.D365_RESOURCE}/.default"]


msal_app = msal.ConfidentialClientApplication(
    settings.D365_CLIENT_ID,
    authority=AUTHORITY,
    client_credential=settings.D365_CLIENT_SECRET
)


_token_cache = {
    "access_token": None,
    "expires_at": 0
}

_token_lock = Lock()


def get_d365_token():

    with _token_lock:

        if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
            return _token_cache["access_token"]

        result = msal_app.acquire_token_for_client(scopes=SCOPE)

        if "access_token" not in result:
            raise HTTPException(
                status_code=500,
                detail=f"D365 token error: {result}"
            )

        _token_cache["access_token"] = result["access_token"]
        _token_cache["expires_at"] = (
            time.time() + result.get("expires_in", 3600) - 60
        )

        return _token_cache["access_token"]