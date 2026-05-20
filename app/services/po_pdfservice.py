import requests
from fastapi import HTTPException
from app.schemas.po_pdfschema import popdfschema
from app.core.config import settings
# from app.services.d365_tokenservice import get_d365_token
from app.core.d365_auth import get_d365_token
SERVICE_URL = settings.D365_PO_SERVICEURL


def fetch_po_pdf_base64(payload: popdfschema):

    token = get_d365_token()

    body = {
        "_request": {
            "vendAccount": payload.vendAccount,
            "confirmed": payload.confirmed,
            "purchId": payload.purchId,
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    print(">>> URL:", SERVICE_URL)
    print(">>> BODY:", body)
    print(">>> TOKEN:", token[:30], "...")

    try:
        response = requests.post(
            SERVICE_URL,
            json=body,
            headers=headers,
            verify=False, 
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"D365 error: {response.text}"
            )

        return response.json()
        print(">>> STATUS:", response.status_code)
        print(">>> RESPONSE:", response.text[:300])


    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="D365 request timed out"
        )

    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach D365: {str(e)}"
        )

