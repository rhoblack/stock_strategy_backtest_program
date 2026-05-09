"""User 모델 테스트."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user import User


def test_create_user_with_minimum_fields(db_session):
    user = User(email="user@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.is_active is True
    assert user.display_name == ""
    assert user.hashed_password is None
    assert user.created_at is not None
    assert user.updated_at is not None


def test_email_unique_constraint(db_session):
    db_session.add(User(email="dup@example.com"))
    db_session.commit()

    db_session.add(User(email="dup@example.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_with_full_fields(db_session):
    now = datetime.now(UTC)
    user = User(
        email="full@example.com",
        display_name="홍길동",
        hashed_password="$argon2id$v=19$m=65536$...",
        is_active=False,
        last_login_at=now,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.display_name == "홍길동"
    assert user.is_active is False
    assert user.last_login_at is not None


def test_user_repr(db_session):
    user = User(email="repr@example.com")
    db_session.add(user)
    db_session.commit()
    s = repr(user)
    assert "repr@example.com" in s
    assert "User" in s
