
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):

    # ── App ──────────────────────────────────────────────────
    APP_ENV: str = "local"
    DEBUG: bool = True
    APP_NAME: str = "VendorPortal"

    # ── VendorPortal DB ──────────────────────────────────────
    VENDOR_DB_SERVER: str = ""
    VENDOR_DB_NAME: str = ""
    VENDOR_DB_USER: str = ""
    VENDOR_DB_PASSWORD: str = ""
    DB_SCHEMA:str =""

    
    # ── JWT ──────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # ── HTTP ────────────────────────────────────────────────
    HTTP_TIMEOUT_SECONDS: int = 60

    # ── Email ───────────────────────────────────────────────
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_PORT: int = 587
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "noreply@vendorportal.com"

    # ── Frontend ────────────────────────────────────────────
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # ── Storage ─────────────────────────────────────────────
    PO_PDF_STORAGE_PATH: str = "./storage/po_pdfs"

    # ── Scheduler ───────────────────────────────────────────
    BID_EXPIRY_CHECK_INTERVAL_MINUTES: int = 60

    # ── CORS ────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000"

    # ── Properties ──────────────────────────────────────────
    @property
    def is_local(self) -> bool:                    # ← ADDED
        return self.APP_ENV == "local"

    @property
    def is_production(self) -> bool:               # ← ADDED
        return self.APP_ENV == "production"
    
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def vendorportal_conn_str(self) -> str:
        return (
            f"DSN={self.SQL_DSN};"
            f"UID={self.SQL_USERNAME};"
            f"PWD={self.SQL_PASSWORD};"
        )

    @property
    def d365_conn_str(self) -> str:
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={self.D365_DB_SERVER};"
            f"DATABASE={self.D365_DB_NAME};"
            f"UID={self.D365_DB_USER};"
            f"PWD={self.D365_DB_PASSWORD};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=15;"
        )

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()