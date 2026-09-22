"""A Doctor's personal SOAP phrases: "My Phrases" (favorites) + "Recently used" (Task #2 enhancement).

Both lists are scoped to the authenticated Doctor within their clinic and to ONE
field - a phrase for `chief_complaint` is never offered for `treatment_plan`.

Privacy is the same as the clinic-wide list where it applies: every phrase must
pass `is_suggestible` (no emails/URLs/phones/ids/uuids/test junk), be at most 80
characters and a single line. "Recently used" additionally drops any phrase that
contains the name of the patient it was written for. Multi-line saved text is split
into its individual lines; a whole multi-line block is never a phrase. Nothing here
modifies historical SOAP rows.
"""

import re
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.soap_phrase_favorite import PHRASE_MAX_LENGTH
from app.repositories.soap_personal_phrase_repository import RecentRow, SoapPersonalPhraseRepository
from app.repositories.soap_suggestion_repository import SOAP_SUGGESTION_FIELDS
from app.services.soap_suggestion_service import is_suggestible

MAX_FAVORITES_PER_FIELD = 30
DEFAULT_RECENT_LIMIT = 10
_NAME_TOKEN = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


class InvalidPhrase(ValueError):
    """The text is not an acceptable reusable phrase (message is safe to show the Doctor)."""


class FavoritesLimitReached(Exception):
    pass


def is_supported_field(field: str) -> bool:
    return field in SOAP_SUGGESTION_FIELDS


def normalize_phrase(text: str) -> str:
    return " ".join(text.split())


def phrase_key(text: str) -> str:
    return normalize_phrase(text).lower()


def _has_content(value: str) -> bool:
    return any(ch.isalnum() for ch in value)


def validate_phrase(field: str, raw: str) -> str:
    """Return the normalized phrase, or raise `InvalidPhrase`. Used for favorites."""
    stripped = raw.strip()
    if not stripped:
        raise InvalidPhrase("Enter a phrase to save.")
    if "\n" in stripped or "\r" in stripped:
        raise InvalidPhrase("Save one line at a time - a multi-line block cannot be a phrase.")
    value = normalize_phrase(stripped)
    if not _has_content(value):
        raise InvalidPhrase("That is not a reusable phrase.")
    if len(value) > PHRASE_MAX_LENGTH:
        raise InvalidPhrase(f"A phrase can be at most {PHRASE_MAX_LENGTH} characters.")
    if not is_suggestible(value, field):
        raise InvalidPhrase("That looks like patient-specific or identifying text and cannot be saved as a phrase.")
    return value


def _name_tokens(name_parts: tuple[str, ...]) -> set[str]:
    tokens: set[str] = set()
    for part in name_parts:
        tokens.update(t.lower() for t in _NAME_TOKEN.findall(part))
    return tokens


def _mentions_patient(value: str, tokens: set[str]) -> bool:
    if not tokens:
        return False
    words = {w.lower() for w in _NAME_TOKEN.findall(value)}
    return bool(words & tokens)


def extract_segments(text: str) -> list[str]:
    """The individual eligible lines of a saved value (whitespace-normalized, in order)."""
    out: list[str] = []
    for line in text.splitlines():
        value = normalize_phrase(line)
        if value and _has_content(value) and len(value) <= PHRASE_MAX_LENGTH:
            out.append(value)
    return out


class SoapPersonalPhraseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SoapPersonalPhraseRepository(session)

    async def personal(
        self, *, clinic_id: UUID, doctor_id: UUID, field: str, q: str | None, limit: int = DEFAULT_RECENT_LIMIT
    ) -> tuple[list[str], list[str]]:
        needle = q.strip().lower() if q and q.strip() else None

        favorites = await self.repo.list_favorites(clinic_id, doctor_id, field)
        favorite_keys = {f.phrase_key for f in favorites}
        fav_out = [f.phrase for f in favorites if needle is None or needle in f.phrase_key]

        rows: list[RecentRow] = await self.repo.recent_rows(clinic_id, doctor_id, field)
        seen: set[str] = set(favorite_keys)  # a phrase appears once, in the highest section (My phrases)
        recent_out: list[str] = []
        for row in rows:  # already newest first, deterministic tie-break in the query
            tokens = _name_tokens(row.name_parts)
            for value in extract_segments(row.text):
                key = value.lower()
                if key in seen:
                    continue
                if needle is not None and needle not in key:
                    continue
                if not is_suggestible(value, field) or _mentions_patient(value, tokens):
                    continue
                seen.add(key)
                recent_out.append(value)
                if len(recent_out) >= limit:
                    return fav_out, recent_out
        return fav_out, recent_out

    async def add_favorite(self, *, clinic_id: UUID, doctor_id: UUID, field: str, text: str) -> tuple[str, bool]:
        """Returns (phrase, created). A duplicate is idempotent: created=False, no second row."""
        value = validate_phrase(field, text)
        key = value.lower()
        existing = await self.repo.get_favorite(clinic_id, doctor_id, field, key)
        if existing is not None:
            return existing.phrase, False
        if await self.repo.count_favorites(clinic_id, doctor_id, field) >= MAX_FAVORITES_PER_FIELD:
            raise FavoritesLimitReached()
        self.repo.add_favorite(clinic_id=clinic_id, doctor_id=doctor_id, field=field, phrase=value, phrase_key=key)
        try:
            await self.session.commit()
        except IntegrityError:  # a concurrent identical save won the race - still idempotent
            await self.session.rollback()
            existing = await self.repo.get_favorite(clinic_id, doctor_id, field, key)
            if existing is None:
                raise
            return existing.phrase, False
        return value, True

    async def remove_favorite(self, *, clinic_id: UUID, doctor_id: UUID, field: str, text: str) -> bool:
        key = phrase_key(text)
        if not key:
            return False
        removed = await self.repo.delete_favorite(clinic_id, doctor_id, field, key)
        await self.session.commit()
        return removed > 0
