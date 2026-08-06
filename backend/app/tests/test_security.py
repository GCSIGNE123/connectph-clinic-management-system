"""Tests for password hashing and JWT create/decode round trips."""

import uuid

import pytest

from app.core.security import (
    TokenPayloadError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify_roundtrip() -> None:
    plain = "SuperSecret123!"
    hashed = hash_password(plain)

    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    clinic_id = uuid.uuid4()

    token = create_access_token(user_id=user_id, clinic_id=clinic_id, role="Owner")
    payload = decode_token(token, expected_type=TokenType.ACCESS)

    assert payload["user_id"] == str(user_id)
    assert payload["clinic_id"] == str(clinic_id)
    assert payload["role"] == "Owner"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    clinic_id = uuid.uuid4()

    token = create_refresh_token(user_id=user_id, clinic_id=clinic_id, role="Doctor")
    payload = decode_token(token, expected_type=TokenType.REFRESH)

    assert payload["user_id"] == str(user_id)
    assert payload["type"] == "refresh"


def test_decode_rejects_wrong_token_type() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, clinic_id=None, role=None)

    with pytest.raises(TokenPayloadError):
        decode_token(token, expected_type=TokenType.REFRESH)


def test_decode_rejects_garbage_token() -> None:
    with pytest.raises(TokenPayloadError):
        decode_token("not-a-real-token")
