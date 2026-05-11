"""Watchlist / WatchlistItem Pydantic 스키마.

설계서 10번 5-t절 / 07번 13절.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field  # noqa: F401

# ── 요청 ──────────────────────────────────────────────────────────

class WatchlistCreate(BaseModel):
    """POST /api/watchlists 요청 본문."""

    name: str = Field(..., min_length=1, max_length=100, description="관심종목 그룹 이름")
    description: str = Field(default="", max_length=500, description="그룹 설명")


class WatchlistUpdate(BaseModel):
    """PATCH(또는 이름 변경 용도). 현재 MVP에서는 미노출이나 schema 준비."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class SymbolAddRequest(BaseModel):
    """POST /api/watchlists/{id}/symbols 요청 본문."""

    symbol: str = Field(..., min_length=1, max_length=20, description="종목코드")


# ── 응답 ──────────────────────────────────────────────────────────

class WatchlistItemOut(BaseModel):
    """WatchlistItem 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    watchlist_id: int
    symbol: str
    added_at: datetime


class WatchlistOut(BaseModel):
    """Watchlist 목록/생성 응답 (items 미포함)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    item_count: int = 0


class WatchlistDetailOut(BaseModel):
    """GET /api/watchlists/{id} 상세 응답 (items 포함)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    items: list[WatchlistItemOut] = Field(default_factory=list)
