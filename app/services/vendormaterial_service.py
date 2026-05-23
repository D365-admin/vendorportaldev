from app.db.base import (
    get_connection
)

from app.utils.date_utils import (
    format_date
)

from app.utils.remainingdate import (
    calculate_days_left
)

# ============================================================
# BID MATERIALS
# ============================================================
def fetch_bid_materials(
    vendor_account: str
):

    query = """
        SELECT

            P.ITEMID,

            I.NAME
                AS NAMEALIAS,

            P.VALIDFROM,

            P.VALIDTO

        FROM D365_PDSAPPROVEDVENDORLIST P
        WITH (NOLOCK)

        LEFT JOIN D365_INVENTTABLE I
        WITH (NOLOCK)

            ON I.ITEMID = P.ITEMID

        WHERE P.PDSAPPROVEDVENDOR = ?

          AND P.VALIDFROM <= GETDATE()

          AND P.VALIDTO >= GETDATE()

        ORDER BY P.ITEMID
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            query,
            vendor_account
        )

        columns = [
            col[0]
            for col in cursor.description
        ]

        rows = cursor.fetchall()

        result = []

        for row in rows:

            data = dict(
                zip(columns, row)
            )

            result.append({

                "material_id":
                    data["ITEMID"],

                "material_description":
                    data["NAMEALIAS"],

                "valid_from":
                    format_date(
                        data["VALIDFROM"]
                    ),

                "expiry_date":
                    format_date(
                        data["VALIDTO"]
                    ),

                "days_left":
                    calculate_days_left(
                        data["VALIDTO"]
                    )
            })

        return result


# ============================================================
# VENDOR PROFILE
# ============================================================
def fetch_vendor_profile(
    vendor_account: str
):

    profile = {

        "email": None,

        "phone": None,

        "address": None,

        "name": None,

        "city": None
    }

    query = """
        SELECT TOP 1

            NAME,

            EMAIL,

            PHONENUMBER,

            ADDRESS,

            CITY

        FROM D365_VENDORMASTER
        WITH (NOLOCK)

        WHERE ACCOUNTNUM = ?
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            query,
            vendor_account
        )

        row = cursor.fetchone()

        if row:

            profile["name"] = row.NAME

            profile["email"] = row.EMAIL

            profile["phone"] = row.PHONENUMBER

            profile["address"] = row.ADDRESS

            profile["city"] = row.CITY

        cursor.close()

    return profile

# from app.db.base import (
#     get_connection
# )

# from app.utils.date_utils import (
#     format_date
# )

# from app.utils.remainingdate import (
#     calculate_days_left
# )


# # ============================================================
# # BID MATERIALS
# # ============================================================
# def fetch_bid_materials(
#     vendor_account: str
# ):

#     query = """
#         SELECT

#             P.ITEMID,

#             IT.NAME
#                 AS NAMEALIAS,

#             P.VALIDFROM,

#             P.VALIDTO

#         FROM D365_PDSAPPROVEDVENDORLIST P
#         WITH (NOLOCK)

#         LEFT JOIN D365_INVENTTABLE IT
#         WITH (NOLOCK)

#             ON IT.ITEMID = P.ITEMID

#         WHERE P.PDSAPPROVEDVENDOR = ?

#           AND P.VALIDFROM <= GETDATE()

#           AND P.VALIDTO >= GETDATE()

#         ORDER BY P.ITEMID
#     """

#     with get_connection() as conn:

#         cursor = conn.cursor()

#         cursor.execute(
#             query,
#             vendor_account
#         )

#         columns = [
#             col[0]
#             for col in cursor.description
#         ]

#         rows = cursor.fetchall()

#         result = []

#         for row in rows:

#             data = dict(
#                 zip(columns, row)
#             )

#             result.append({

#                 "material_id":
#                     data["ITEMID"],

#                 "material_description":
#                     data["NAMEALIAS"],

#                 "valid_from":
#                     format_date(
#                         data["VALIDFROM"]
#                     ),

#                 "expiry_date":
#                     format_date(
#                         data["VALIDTO"]
#                     ),

#                 "days


# from app.db.base import get_connection,get_connection
# from app.utils.date_utils import format_date
# from app.utils.remainingdate import calculate_days_left

# def fetch_bid_materials(vendor_account: str):
#     query = """
#         SELECT
#             P.ITEMID,
#             P.NAME AS NAMEALIAS,
#             P.VALIDFROM,
#             P.VALIDTO
#         FROM D365_PDSAPPROVEDVENDORLIST P WITH (NOLOCK)
#         WHERE LTRIM(RTRIM(P.PDSAPPROVEDVENDOR)) = ?
#           AND P.VALIDFROM <= GETDATE()
#           AND P.VALIDTO >= GETDATE()
#         ORDER BY P.ITEMID
#         """
# #     query = """
# #         SELECT
# #     P.ITEMID,
# #     I.NAMEALIAS,
# #     P.VALIDFROM,
# #     P.VALIDTO
# # FROM PDSAPPROVEDVENDORLIST P WITH (NOLOCK)
# # LEFT JOIN INVENTTABLE I WITH (NOLOCK)
# #     ON LTRIM(RTRIM(P.ITEMID)) = LTRIM(RTRIM(I.ITEMID))
# # WHERE LTRIM(RTRIM(P.PDSAPPROVEDVENDOR)) = ?
# # AND P.VALIDFROM <= GETDATE()
# # AND P.VALIDTO >= GETDATE()
# # ORDER BY P.ITEMID
# #     """
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute(query, vendor_account)

#         columns = [col[0] for col in cursor.description]
#         rows = cursor.fetchall()

#         result = []

#         for row in rows:
#             data = dict(zip(columns, row))

#             result.append({
#                 "material_id": data["ITEMID"],
#                 "material_description": data["NAMEALIAS"],
#                 "valid_from": format_date(data["VALIDFROM"]),
#                 "expiry_date": format_date(data["VALIDTO"]),
#                 "days_left":calculate_days_left(data["VALIDTO"])
 
#             })

#         return result

# def fetch_vendor_profile(vendor_account: str):

#     profile = {
#         "email": None,
#         "phone": None,
#         "address": None,
#         "name":None,
#         "city":None
#     }

#     with get_connection()  as conn:
#         cursor = conn.cursor()
#         query="""SELECT TOP 1
#             NAME,
#             EMAIL,
#             PHONENUMBER,
#             ADDRESS,
#             CITY
#         FROM D365_VENDORMASTER WITH (NOLOCK)
#         WHERE LTRIM(RTRIM(ACCOUNTNUM)) = ?
#     """

#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute(query, vendor_account)

#         row = cursor.fetchone()

#         if row:
#             profile["name"] = row.NAME
#             profile["email"] = row.EMAIL
#             profile["phone"] = row.PHONENUMBER
#             profile["address"] = row.ADDRESS
#             profile["city"] = row.CITY

#         cursor.close()

#     return profile
#         # # 🔹 Fetch Email + Phone
#         # electronic_query = """
#         #     SELECT TYPE, LOCATOR
#         #     FROM HIQ_vendorELECTRONICADDRESSVIEW WITH (NOLOCK)
#         #     WHERE ACCOUNTNUM = ?
#         #     AND ISPRIMARY1 = 1
#         # """

#     #     cursor.execute(electronic_query, vendor_account)
#     #     electronic_rows = cursor.fetchall()

#     #     for row in electronic_rows:
#     #         type = row.TYPE
#     #         locator = row.LOCATOR
 
#     #         if type == 2:
#     #             profile["email"] = locator
#     #         elif type == 1:
#     #             profile["phone"] = locator

#     #     # 🔹 Fetch Address
#     #     address_query = """
#     #         SELECT TOP 1 ADDRESS,NAME,city
#     #         FROM HIQ_vendorPostalADDRESSVIEW WITH (NOLOCK)
#     #         WHERE ACCOUNTNUM = ?
#     #         AND ISPRIMARY = 1
#     #     """

#     #     cursor.execute(address_query, vendor_account)
#     #     address_row = cursor.fetchone()

#     #     if address_row:
#     #         profile["address"] = address_row.ADDRESS
#     #         profile["name"]=address_row.NAME
#     #         profile["city"]=address_row.city
#     #     cursor.close()

#     # return profile 
