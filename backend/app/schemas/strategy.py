"""Strategy API Pydantic 스키마.

설계서 10번 2절. ORM 모델과 분리하여 API 입출력 형식만 다룸.

`strategy_json` 필드는 Pydantic 기본 검증 외에도 02번 5절 + 03번 4절 정책
검증을 거친다 (validate_strategy_json). 여기서 raise되는 AppError는
errors.py의 exception_handler가 표준 envelope으로 변환한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.strategy_json import validate_strategy_json


# ── 전략 버전 이력 스키마 (10-m / 10번 2절)

class StrategyVersionOut(BaseModel):
    """GET /api/strategies/{id}/versions 응답 단건."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    version_number: int  # StrategyVersion.version 컬럼 → alias 매핑 필요
    created_at: datetime
    change_note: str
    strategy_json_summary: dict  # 조건 개수 요약 (entry/exit_position 조건 수)

    @classmethod
    def from_orm_version(cls, v: Any) -> "StrategyVersionOut":
        """StrategyVersion ORM 인스턴스 → StrategyVersionOut 변환.

        strategy_json_summary는 ORM 컬럼이 아니므로 직접 계산.
        """
        sj: dict = v.strategy_json or {}
        entry_count = len((sj.get("entry") or {}).get("conditions") or [])
        exit_signal_count = len((sj.get("exit_signal") or {}).get("conditions") or [])
        exit_position_count = len((sj.get("exit_position") or {}).get("conditions") or [])
        return cls(
            id=v.id,
            strategy_id=v.strategy_id,
            version_number=v.version,  # ORM은 .version
            created_at=v.created_at,
            change_note=v.change_note or "",
            strategy_json_summary={
                "entry_condition_count": entry_count,
                "exit_signal_condition_count": exit_signal_count,
                "exit_position_condition_count": exit_position_count,
            },
        )


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    strategy_json: dict[str, Any]
    tags: list[str] = []
    favorite: bool = False

    @model_validator(mode="after")
    def _validate_strategy_payload(self) -> StrategyCreate:
        """02번 5절 + 03번 4절 + 10번 7.1 검증.

        Pydantic은 ValidationError로 감싸지만 우리 핸들러는 AppError를 우선
        포착하므로, validator 안에서 AppError를 raise해도 envelope이 유지된다.

        FastAPI는 model_validator 내부의 raise를 RequestValidationError로
        변환하지 않고 원형 예외를 보존한다(pydantic v2 동작) — handler가
        AppError로 매칭한다.
        """
        validate_strategy_json(self.strategy_json)
        return self


class StrategyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    strategy_json: dict[str, Any] | None = None
    tags: list[str] | None = None
    favorite: bool | None = None
    change_note: str = ""

    @model_validator(mode="after")
    def _validate_strategy_payload(self) -> StrategyUpdate:
        if self.strategy_json is not None:
            validate_strategy_json(self.strategy_json)
        return self


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
