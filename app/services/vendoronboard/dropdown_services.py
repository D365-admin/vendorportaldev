from app.db.base import get_connection
from app.core.config import settings

OTHER_ID = "OTH"
OTHER_NAME = "Others"

PRIMARY_SCHEMA = settings.DB_SCHEMA

# Secondary database schema.
SECONDARY_SCHEMA = getattr(
    settings,
    "SECONDARY_DB_SCHEMA",
    settings.DB_SCHEMA,
)

def _clean(value):
    if value is None:
        return None

    value = str(value).strip()

    return value if value else None


def _append_others(
    rows: list[dict],
    id_key: str | None = None,
    name_key: str | None = None,
) -> list[dict]:
    """
    Add Others only if not already present.
    """

    for row in rows:
        values = [
            str(v).strip().upper()
            for v in row.values()
            if v is not None
        ]

        if OTHER_ID in values or OTHER_NAME.upper() in values:
            return rows

    if id_key and name_key:
        rows.append(
            {
                id_key: OTHER_ID,
                name_key: OTHER_NAME,
            }
        )

    elif name_key:
        rows.append(
            {
                name_key: OTHER_NAME,
            }
        )

    return rows


def company_address_country():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT DISTINCT
                COUNTRYREGIONID,
                COALESCE(NULLIF(Country, ''), COUNTRYREGIONID) AS CountryName
            FROM {PRIMARY_SCHEMA}.d365_LogisticsAddressCountryRegion
            WHERE COUNTRYREGIONID IS NOT NULL
            ORDER BY CountryName
            """
        )

        rows = [
            {
                "CountryId": _clean(row[0]),
                "CountryName": _clean(row[1]),
            }
            for row in cursor.fetchall()
            if _clean(row[0]) is not None
        ]

        return _append_others(
            rows,
            id_key="CountryId",
            name_key="CountryName",
        )
def company_address_state(country_name):
    country_name = _clean(country_name)

    if not country_name:
        return [{"StateName": OTHER_NAME}]

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT DISTINCT
                s.NAME
            FROM {PRIMARY_SCHEMA}.d365_LogisticsAddressState s
            INNER JOIN {PRIMARY_SCHEMA}.d365_LogisticsAddressCountryRegion c
                ON c.COUNTRYREGIONID = s.COUNTRYREGIONID
            WHERE c.Country = ?
            ORDER BY s.NAME
            """,
            (country_name,),
        )

        rows = [
            {"StateName": _clean(row[0])}
            for row in cursor.fetchall()
            if _clean(row[0]) is not None
        ]

        return _append_others(rows, name_key="StateName")

# def company_address_state(country):
#     country = _clean(country)

#     if not country:
#         return [
#             {
#                 "StateId": OTHER_ID,
#                 "StateName": OTHER_NAME,
#             }
#         ]

#     with get_connection() as conn:
#         cursor = conn.cursor()

#         cursor.execute(
#             """
#             SELECT DISTINCT
#                 STATEID,
#                 NAME
#             FROM {PRIMARY_SCHEMA}.d365_LogisticsAddressState
#             WHERE COUNTRYREGIONID = ?
#               AND STATEID IS NOT NULL
#             ORDER BY NAME
#             """,
#             (country,),
#         )

#         rows = [
#             {
#                 "StateId": _clean(row[0]),
#                 "StateName": _clean(row[1]),
#             }
#             for row in cursor.fetchall()
#             if _clean(row[0]) is not None
#         ]

#         return _append_others(
#             rows,
#             id_key="StateId",
#             name_key="StateName",
#         )
def company_address_city(country_name, state_name):
    country_name = _clean(country_name)
    state_name = _clean(state_name)

    if not country_name or not state_name:
        return [{"CityName": OTHER_NAME}]

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT DISTINCT
                city.NAME
            FROM {PRIMARY_SCHEMA}.d365_LogisticsAddressCity city
            INNER JOIN {PRIMARY_SCHEMA}.d365_LogisticsAddressState state
                ON city.COUNTRYREGIONID = state.COUNTRYREGIONID
               AND city.STATEID = state.STATEID
            INNER JOIN {PRIMARY_SCHEMA}.d365_LogisticsAddressCountryRegion country
                ON state.COUNTRYREGIONID = country.COUNTRYREGIONID
            WHERE country.Country = ?
              AND state.NAME = ?
            ORDER BY city.NAME
            """,
            (
                country_name,
                state_name,
            ),
        )

        rows = [
            {"CityName": _clean(row[0])}
            for row in cursor.fetchall()
            if _clean(row[0]) is not None
        ]

        return _append_others(rows, name_key="CityName")

# def company_address_city(country, state):
#     country = _clean(country)
#     state = _clean(state)

#     if not country or not state:
#         return [
#             {
#                 "CityName": OTHER_NAME,
#             }
#         ]

#     with get_connection() as conn:
#         cursor = conn.cursor()

#         cursor.execute(
#             """
#             SELECT DISTINCT
#                 NAME
#             FROM {PRIMARY_SCHEMA}.d365_LogisticsAddressCity
#             WHERE COUNTRYREGIONID = ?
#               AND STATEID = ?
#               AND NAME IS NOT NULL
#             ORDER BY NAME
#             """,
#             (
#                 country,
#                 state,
#             ),
#         )

#         rows = [
#             {
#                 "CityName": _clean(row[0]),
#             }
#             for row in cursor.fetchall()
#             if _clean(row[0]) is not None
#         ]

#         return _append_others(
#             rows,
#             name_key="CityName",
#         )

def company_address_zipcode(country_name):
    country_name = _clean(country_name)

    if not country_name:
        return [
            {
                "ZipCode": "OTH",
            }
        ]

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT DISTINCT
                z.ZIPCODE
            FROM {PRIMARY_SCHEMA}.d365_LogisticsAddressZipCode z
            INNER JOIN {PRIMARY_SCHEMA}.d365_LogisticsAddressCountryRegion c
                ON z.COUNTRYREGIONID = c.COUNTRYREGIONID
            WHERE c.Country = ?
              AND z.ZIPCODE IS NOT NULL
            ORDER BY z.ZIPCODE
            """,
            (country_name,),
        )

        rows = [
            {
                "ZipCode": _clean(row[0]),
            }
            for row in cursor.fetchall()
            if _clean(row[0]) is not None
        ]

        # Add OTH only if not already present
        exists_oth = any(
            str(row["ZipCode"]).strip().upper() == "OTH"
            for row in rows
        )

        if not exists_oth:
            rows.append(
                {
                    "ZipCode": "OTH",
                }
            )

        return rows
# from app.db.base import get_connection

# def company_address_country():
#     with get_connection() as conn:
#         cursor = conn.cursor()

#         cursor.execute("""
#             SELECT COUNTRYREGIONID, Country
#             FROM dev.d365_LogisticsAddressCountryRegion
#             ORDER BY COUNTRYREGIONID
#         """)

#         return [
#             {
#                 "CountryId": row[0],
#                 "CountryName": row[1]
#             }
#             for row in cursor.fetchall()
#         ]
    
# def company_address_state(country):
#     with get_connection() as conn:
#         cursor = conn.cursor()

#         cursor.execute("""
#             SELECT STATEID, NAME
#             FROM dev.d365_LogisticsAddressState
#             WHERE COUNTRYREGIONID = ?
#             ORDER BY NAME
#         """, (country,))

#         return [
#             {
#                 "StateId": row[0],
#                 "StateName": row[1]
#             }
#             for row in cursor.fetchall()
#         ]
    

# def company_address_city(country, state):
#     with get_connection() as conn:
#         cursor = conn.cursor()

#         cursor.execute("""
#             SELECT NAME
#             FROM dev.d365_LogisticsAddressCity
#             WHERE COUNTRYREGIONID = ?
#             AND STATEID = ?
#             ORDER BY NAME
#         """, (country, state))

#         return [
#             {
#                 "CityName": row[0]
#             }
#             for row in cursor.fetchall()
#         ]
    

# def company_address_zipcode(country):
#     with get_connection() as conn:
#         cursor = conn.cursor()

#         cursor.execute("""
#             SELECT ZIPCODE
#             FROM dev.d365_LogisticsAddressZipCode
#             WHERE COUNTRYREGIONID = ?
#             ORDER BY ZIPCODE
#         """, (country,))

#         return [
#             {
#                 "ZipCode": row[0]
#             }
#             for row in cursor.fetchall()
#         ]
    

