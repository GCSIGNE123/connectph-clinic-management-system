"""Learned SOAP / diagnosis suggestions (Task #2).

Only obvious identifying or junk values are screened out here (emails, URLs,
phone-like numbers, patient/visit/invoice-style identifiers, a few unmistakable
test artifacts). This is deliberately NOT medical-text classification and it
never touches or deletes the stored SOAP/diagnosis data - it only decides what
is shown as a suggestion.
"""

import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.soap_suggestion_repository import SOAP_SUGGESTION_FIELDS, SoapSuggestionRepository

DEFAULT_LIMIT = 10
ICD_CODE_FIELDS = {"icd10_code"}

_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_URL = re.compile(r"(https?://|www\.)|\b[a-z0-9-]+\.(com|net|org|ph|io|gov|edu)\b", re.IGNORECASE)
_PHONE = re.compile(r"(\+?\d[\d\s().-]{6,}\d)")
_ID_PREFIX = re.compile(r"\b(PAT|VIS|INV|ORD|RX|CERT|LAB|APT|QUE)-?\d{2,}", re.IGNORECASE)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_TEST_START = re.compile(r"^(test|testing|asdf|adsf|qwerty|dummy|lorem|xxx+)\b", re.IGNORECASE)
_TEST_ANYWHERE = re.compile(r"\b(regression|verification|e2e|uat)\b", re.IGNORECASE)


def is_suggestible(value: str, field: str) -> bool:
    """False for values that are obviously identifying or a test artifact."""
    if _EMAIL.search(value) or _URL.search(value) or _UUID.search(value) or _ID_PREFIX.search(value):
        return False
    if _TEST_START.search(value) or _TEST_ANYWHERE.search(value):
        return False
    # ICD-10 codes (e.g. J06.9) are code-like by nature and must not be treated as junk.
    if field not in ICD_CODE_FIELDS:
        if _PHONE.search(value):
            return False
        # A long single token containing digits looks like an identifier/code, not a phrase.
        if any(len(tok) >= 10 and re.search(r"\d", tok) for tok in value.split()):
            return False
    return True


class SoapSuggestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = SoapSuggestionRepository(session)

    @staticmethod
    def is_supported(field: str) -> bool:
        return field in SOAP_SUGGESTION_FIELDS

    async def suggestions(self, *, clinic_id: UUID, field: str, q: str | None, limit: int = DEFAULT_LIMIT) -> list[str]:
        if not self.is_supported(field):
            raise ValueError(f"unsupported field '{field}'")
        candidates = await self.repo.candidates(clinic_id, field, q)
        seen: set[str] = set()
        out: list[str] = []
        for value in candidates:  # already ordered: most patients first, then alphabetical
            key = value.lower()
            if key in seen or not is_suggestible(value, field):
                continue
            seen.add(key)
            out.append(value)
            if len(out) >= limit:
                break
        return out
