"""Schemas for the SOAP / diagnosis learned-suggestions endpoint (Task #2)."""

from pydantic import BaseModel, ConfigDict


class SoapSuggestion(BaseModel):
    """Suggestion text only - never a patient/consultation identifier or a
    usage count that could hint at an individual record."""

    text: str


class SoapSuggestionsResponse(BaseModel):
    field: str
    suggestions: list[SoapSuggestion]


# --- Personal (Doctor-specific) suggestions: "My Phrases" + "Recently used" -----------------
# Sibling to the clinic-suggestions response above, which is deliberately left unchanged.


class SoapPersonalSuggestionsResponse(BaseModel):
    field: str
    favorites: list[SoapSuggestion]
    recent: list[SoapSuggestion]


class SoapFavoriteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    text: str


class SoapFavoriteRead(BaseModel):
    field: str
    text: str
