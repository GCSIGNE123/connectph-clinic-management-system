"""Schemas for the SOAP / diagnosis learned-suggestions endpoint (Task #2)."""

from pydantic import BaseModel


class SoapSuggestion(BaseModel):
    """Suggestion text only - never a patient/consultation identifier or a
    usage count that could hint at an individual record."""

    text: str


class SoapSuggestionsResponse(BaseModel):
    field: str
    suggestions: list[SoapSuggestion]
