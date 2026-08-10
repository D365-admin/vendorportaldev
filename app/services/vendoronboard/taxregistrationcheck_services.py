                        
from app.db.base import get_secondary_connection
from app.core.config import settings
PRIMARY_SCHEMA = settings.DB_SCHEMA

# Secondary database schema.
SECONDARY_SCHEMA = getattr(
    settings,
    "SECONDARY_DB_SCHEMA",
    settings.DB_SCHEMA,
)


def tax_registration_check(tax_registration_number: str) -> dict:
    tax_registration_number = tax_registration_number.strip()

    with get_connection()as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT TOP 1 RegistrationNumber
            FROM {SECONDARY_SCHEMA}.TAXREGISTRATIONNUMBERS_IN
            WHERE UPPER(LTRIM(RTRIM(RegistrationNumber))) = UPPER(?)
            """,
            (tax_registration_number,),
        )

        result = cursor.fetchone()

        if result:
            return {
                "exists": True,
                "message": "Tax registration number already exists",
            }

        return {
            "exists": False,
            "message": "Tax registration number does not exist",
        }