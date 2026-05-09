"""Strategy API Pydantic 스키마.

설계서 10번 2절. ORM 모델과 분리하여 API 입출력 형식만 다룸.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    strategy_json: dict[str, Any]
    tags: list[str] = []
    favorite: bool = False


class StrategyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    strategy_json: dict[str, Any] | None = None
    tags: list[str] | None = None
    favorite: bool | None = None
    change_note: str = ""


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str
    strategy_json: dict[str, Any]
    tags: list[str]
    favorite: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
