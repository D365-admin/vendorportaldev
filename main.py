from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import urllib3

from app.core.config import settings

# Routers
from app.api.routes.rfq_newrouter import router as rfq_router
from app.api.routes.vendormat_router import router as my_profile
from app.api.routes.auth_router import router as auth_router
from app.api.routes.po_router import router as po_router
from app.api.routes.po_linerouter import router as po_linerouter
from app.api.routes.rfq_expiryrouter import router as rfq_expiryrouter
from app.api.routes.rfq_linefetchrouter import router as rfq_linefetchrouter
from app.api.routes.rfq_submissionrouter import router as rfq_submissionrouter
from app.api.routes.rfq_completedrouter import router as rfq_completedrouter
from app.api.routes.rfq_inprogressrouter import router as rfq_inprogressrouter
from app.api.routes.dashboard_router import router as dashboard_router
from app.api.routes.dropdownrouter import router as dropdown
from app.api.routes.rfq_expirylinerouter import router as rfq_expirylinerouter
from app.api.routes.notification_router import router as notification_router
from app.api.routes.po_pdfrouter import router as po_pdfrouter
# RFQ Reply Scheduler
from app.api.routes.rfq_reply import (
    router as rfq_replyrouter,
    start_scheduler,
    stop_scheduler
)

# Disable SSL warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# FastAPI App
app = FastAPI(
    title="Vendor Portal API"
)

# ======================================
# CORS Configuration
# ======================================

origins = [
    "https://hiqvendorportal.azurewebsites.net",
    "https://hiqvendorportal.azurewebsites.net/",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,

    # TEMP DEBUG ONLY
    # Uncomment below to test if issue is CORS
    # allow_origins=["*"],
    # allow_credentials=False,

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================
# Register Routers
# ======================================

app.include_router(auth_router)
app.include_router(rfq_router)
app.include_router(my_profile)
app.include_router(po_router)
app.include_router(po_linerouter)
app.include_router(rfq_expiryrouter)
app.include_router(rfq_linefetchrouter)
app.include_router(rfq_submissionrouter)
app.include_router(rfq_completedrouter)
app.include_router(rfq_inprogressrouter)
app.include_router(dashboard_router)
app.include_router(dropdown)
app.include_router(rfq_expirylinerouter)
app.include_router(notification_router)
app.include_router(rfq_replyrouter)
app.include_router(po_pdfrouter)
# ======================================
# Startup / Shutdown Events
# ======================================

@app.on_event("startup")
def on_startup():
    print("Application Starting...")
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    print("Application Shutting Down...")
    stop_scheduler()

# ======================================
# Health Check
# ======================================

@app.get("/health")
def health():
    return {
        "status": "Running",
        "service": "Vendor Portal API"
    }

# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from app.core.config import settings
# from app.api.routes.rfq_newrouter import router as rfq_router
# from app.api.routes.vendormat_router import router as my_profile
# from app.api.routes.auth_router import router as auth_router
# from app.api.routes.po_router import router as po_router
# from app.api.routes.po_linerouter import router as po_linerouter
# from app.api.routes.rfq_expiryrouter import router as rfq_expiryrouter 
# from app.api.routes.rfq_linefetchrouter import router as rfq_linefetchrouter
# from app.api.routes.rfq_submissionrouter import router as rfq_submissionrouter
# # from app.api.routes.po_pdfrouter import router as po_pdfrouter
# from app.api.routes.rfq_completedrouter import router as rfq_completedrouter
# from app.api.routes.rfq_inprogressrouter import router as rfq_inprogressrouter 
# from app.api.routes.dashboard_router import router as dashboard_router
# from app.api.routes.dropdownrouter import router as dropdown
# from app.api.routes.rfq_expirylinerouter import router as rfq_expirylinerouter
# from app.api.routes.notification_router import router as notification_router


# app = FastAPI(
#     title="Vendor Portal API"
# )

# # ✅ Allowed Origins
# origins = [
#     "https://hiqvendorportal.azurewebsites.net", 
#     "http://localhost:3000",
#     # "https://hiqvpbackend.azurewebsites.net"
    
# ]
# # origins = [
# #     # "http://10.10.0.101:9000",
# #     # "http://10.10.0.101.8000",
# #     "https://hiqvendorportal.azurewebsites.net",
# #     "https://hiqvendorportal.azurewebsites.net/",
# #     "http://localhost:3000",
# #     "https://hiqvpbackend-gggnb9ekc8chg9bu.centralindia-01.azurewebsites.net/"
# #     # "http://127.0.0.1:3000",
# #     # "http://127.0.0.1:8000",
# #     # "http://localhost:8000",
# #     # "http://192.168.10.29:3000",
# #     # "http://192.168.10.29",
# #     # "http://10.50.20.89:8090"

# # ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     # allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# app.include_router(rfq_router)
# app.include_router(my_profile)
# app.include_router(auth_router)
# app.include_router(po_router)
# app.include_router(po_linerouter)
# app.include_router(rfq_expiryrouter)
# app.include_router(rfq_linefetchrouter)
# app.include_router(rfq_submissionrouter)
# # app.include_router(po_pdfrouter)
# app.include_router(rfq_completedrouter)
# app.include_router(rfq_inprogressrouter)
# app.include_router(dashboard_router)
# app.include_router(dropdown)
# app.include_router(rfq_expirylinerouter)
# app.include_router(notification_router)

 
# import urllib3
# from fastapi import FastAPI
# from app.api.routes.rfq_reply import router as rfq_replyrouter
# from app.api.routes.rfq_reply import start_scheduler, stop_scheduler
 
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
 
 
# app.include_router(rfq_replyrouter)
 
 
# @app.on_event("startup")
# def on_startup():
#     start_scheduler()
 
 
# @app.on_event("shutdown")
# def on_shutdown():
#     stop_scheduler()
 
 
# @app.get("/health")
# def health():
#     return {"status": "Running"}

