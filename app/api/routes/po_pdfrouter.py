from fastapi import APIRouter
from app.schemas.po_pdfschema import popdfschema
from app.services.po_pdfservice import fetch_po_pdf

router = APIRouter(prefix="/po", tags=["PO"])

@router.post("/document")
def get_po_document(req: popdfschema):
    return fetch_po_pdf(req.purchId)


# from fastapi import APIRouter
# from fastapi.responses import Response

# from app.schemas.po_pdfschema import popdfschema
# from app.services.po_pdfservice import fetch_po_pdf

# router = APIRouter(prefix="/po", tags=["PO"])


# @router.post("/document")
# def get_po_document(req: popdfschema):

#     result = fetch_po_pdf(req.purchId)

#     return Response(
#         content=result["file_content"],
#         media_type="application/pdf",
#         headers={
#             "Content-Disposition":
#             f'inline; filename="{result["file_name"]}"'
#         }
#     )
# # from fastapi import APIRouter, Depends
# # from app.schemas.po_pdfschema import popdfschema
# # from app.services.po_pdfservice import fetch_po_pdf_base64
# # from app.core.security import get_current_vendor

# # router = APIRouter(prefix="/po", tags=["PO"])


# # @router.post("/pdf")
# # def get_po_pdf(
# #     payload: popdfschema,
# #     user = Depends(get_current_vendor)
# # ):
# #     vendor_account = user.get("vendor_account")

# #     # OPTIONAL: pass vendor_account if service supports validation
# #     base64_pdf = fetch_po_pdf_base64(payload)

# #     return {
# #         "status": "success",
# #         "base64": base64_pdf
# #     }


# # # from fastapi import APIRouter
# # # from app.schemas.po_pdfschema import popdfschema
# # # from app.services.po_pdfservice import fetch_po_pdf_base64

# # # router = APIRouter(prefix="/po", tags=["PO"])


# # # @router.post("/pdf")
# # # def get_po_pdf(payload: popdfschema):
# # #     base64_pdf = fetch_po_pdf_base64(payload)

# # #     return {
# # #         "status": "success",
# # #         "base64": base64_pdf
# # #     }
