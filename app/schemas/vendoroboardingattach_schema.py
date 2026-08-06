from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


NULL_TEXT_VALUES = {
    "",
    "null",
    "none",
    "undefined",
    "n/a",
}


class AttachmentContentRequest(BaseModel):
    """
    Request payload for fetching raw attachment content.

    VendAccount accepts a real vendor account, JSON null,
    an empty string, or text such as "null"/"undefined".
    Null-like values are normalized to Python None.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    AttachmentId: int = Field(
        ...,
        gt=0,
        examples=[21],
    )

    ProspectId: str = Field(
        ...,
        min_length=1,
        max_length=20,
        examples=["PR0783"],
    )

    AttachmentFor: Literal[
        "FactoryLicense",
        "OEMCert",
        "Certification",
    ]

    VendAccount: str | None = Field(
        default=None,
        examples=["V0001", None],
    )

    FileName: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["HiQ-00012526.pdf"],
    )

    @field_validator(
        "ProspectId",
        mode="before",
    )
    @classmethod
    def normalize_prospect_id(
        cls,
        value: Any,
    ) -> str:
        normalized = str(
            value or ""
        ).strip().upper()

        if not normalized:
            raise ValueError(
                "ProspectId is required"
            )

        return normalized

    @field_validator(
        "VendAccount",
        mode="before",
    )
    @classmethod
    def normalize_vend_account(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(
            value
        ).strip()

        if normalized.lower() in NULL_TEXT_VALUES:
            return None

        return normalized.upper()

    @field_validator(
        "FileName",
        mode="before",
    )
    @classmethod
    def normalize_file_name(
        cls,
        value: Any,
    ) -> str:
        raw_value = str(
            value or ""
        ).strip().replace("\\", "/")

        file_name = Path(
            raw_value
        ).name.strip()

        if not file_name:
            raise ValueError(
                "FileName is required"
            )

        return file_name



# from __future__ import annotations

# from pathlib import Path
# from typing import Literal, Optional

# from pydantic import (
#     BaseModel,
#     ConfigDict,
#     Field,
#     field_validator,
# )


# class AttachmentContentRequest(BaseModel):
#     """
#     Request payload for fetching raw attachment content.
#     """

#     model_config = ConfigDict(
#         extra="forbid",
#         str_strip_whitespace=True,
#     )

#     AttachmentId: int = Field(
#         ...,
#         gt=0,
#         examples=[21],
#     )

#     ProspectId: str = Field(
#         ...,
#         min_length=1,
#         max_length=20,
#         examples=["PR0783"],
#     )

#     AttachmentFor: Literal[
#         "FactoryLicense",
#         "OEMCert",
#         "Certification",
#     ]

#     VendAccount: Optional[str] = Field(
#         default=None,
#         examples=["V0001"],
#     )

#     FileName: str = Field(
#         ...,
#         min_length=1,
#         max_length=255,
#         examples=["HiQ-00012526.pdf"],
#     )

#     @field_validator("ProspectId")
#     @classmethod
#     def normalize_prospect_id(
#         cls,
#         value: str,
#     ) -> str:
#         normalized = value.strip().upper()

#         if not normalized:
#             raise ValueError(
#                 "ProspectId is required"
#             )

#         return normalized

#     @field_validator("VendAccount")
#     @classmethod
#     def normalize_vend_account(
#         cls,
#         value: Optional[str],
#     ) -> Optional[str]:
#         if value is None:
#             return None

#         normalized = value.strip().upper()

#         return normalized or None

#     @field_validator("FileName")
#     @classmethod
#     def normalize_file_name(
#         cls,
#         value: str,
#     ) -> str:
#         file_name = Path(value).name.strip()

#         if not file_name:
#             raise ValueError(
#                 "FileName is required"
#             )

#         return file_name