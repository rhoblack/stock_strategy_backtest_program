"""UniverseHistory 모델 (07번 §14 / 06번 §14 / 14번 §10).

백테스트 시점의 universe 스냅샷을 영속화한다 — **재현성 + 디버깅 + 영향 분석** 목적.
019 UniverseSelector.select_with_details의 결과를 본 테이블에 저장하면, 같은 시점의
universe를 나중에 재계산하지 않고 그대로 가져올 수 있다 (13.13 / 14.10 생존편향
영향 분석에 활용).

본 step(027)은 다음을 보존한다:
    - as_of_date (universe 선정 기준일)
    - market (KOSPI / KOSDAQ / KONEX — 시장 구분)
    - selection_method (ALL / MARKET_CAP_TOP_N / LIQUIDITY_TOP_N — 06번 §9)
    - config_json (UniverseSelector에 입력한 dict 전체 — 재현용 스냅샷)
    - config_hash (config_json의 안정 해시 — UniqueConstraint 키)
    - symbols_json (선정된 종목 코드 리스트 — symbol ASC, 결정론)
    - run_id (선택 — backtest_runs FK, NULL 허용. preview 스냅샷도 보존 가능)
    - created_at

UniqueConstraint(as_of_date, market, selection_method, config_hash):
    동일 시점 + 동일 시장 + 동일 method + 동일 config는 1건만 (재계산 결과 동일성 보장).
    config_hash가 없는 옛 row는 NULL로 들어와도 SQLite NULL UNIQUE 의미상 중복 허용.
    실제 작성 시 호출자가 config_hash를 항상 채울 것을 권장.

인덱스 (as_of_date):
    "최근 universe 스냅샷부터 N건" 같은 시계열 조회용.
인덱스 (run_id):
    backtest_runs 단위 조회 (재현 / Reports에서 활용).

JSON 컬럼:
    - 07번 §16: SQLite는 TEXT로 보존, PostgreSQL은 JSONB. 본 step은 SQLAlchemy JSON 타입을
      사용해 두 DB 모두 호환.
    - symbols_json: list[str] — 종목 코드 리스트 (symbol ASC). 메타(이름/시가총액)는
      재현 시점에 다시 조회하면 됨.
    - config_json: dict[str, Any] — UniverseSelector에 들어간 입력 그대로.

13.13 / 14.10 생존편향 정합:
    - universe_history는 "그 시점에 살아있던 종목"을 그대로 보존하므로, 나중에 폐지된 종목도
      symbols_json에 포함된 채로 남는다 → 재현 시 생존편향 없음.

13.15 look-ahead bias 정합:
    - universe 선정 시점의 정보만 사용해 저장 → 재계산 없이 미래 데이터 누설 0.

결정론 (CLAUDE.md #8 / 13.12):
    - symbols_json은 symbol ASC로 정렬해 저장 (UniverseSelector가 이미 정렬되어 있음).
    - config_json의 키 순서가 dict 순회에 의존하지 않도록 호출자가 정렬해 직렬화 권장
      (config_hash가 일관되도록).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

if TYPE_CHECKING:
    pass


class UniverseHistory(Base):
    """universe_history 테이블 — 백테스트 시점별 universe 스냅샷.

    019 UniverseSelector 결과를 직렬화해 보존. 재계산 비용 없이 동일 universe 재현.

    Args/필드:
        as_of_date: universe 선정 기준일.
        market: KOSPI / KOSDAQ / KONEX.
        selection_method: ALL / MARKET_CAP_TOP_N / LIQUIDITY_TOP_N (06번 §9).
        config_json: UniverseSelector 입력 dict 전체 (재현용).
        config_hash: config_json의 안정 해시 (예: SHA-256). UniqueConstraint 키.
        symbols_json: 선정된 종목 코드 리스트 (symbol ASC).
        run_id: backtest_runs FK (선택 — preview 스냅샷이면 NULL).
        created_at: 본 row 생성 시각.
    """

    __tablename__ = "universe_history"
    __table_args__ = (
        UniqueConstraint(
            "as_of_date",
            "market",
            "selection_method",
            "config_hash",
            name="uq_universe_history_date_market_method_hash",
        ),
        Index("ix_universe_history_as_of_date", "as_of_date"),
        Index("ix_universe_history_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    as_of_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    selection_method: Mapped[str] = mapped_column(String(40), nullable=False)

    # JSON 컬럼 (07번 §16 — SQLite TEXT / PostgreSQL JSONB 자동 호환)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbols_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    # 선택: backtest_runs FK (preview 스냅샷이면 NULL)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        count = len(self.symbols_json) if isinstance(self.symbols_json, list) else 0
        return (
            f"<UniverseHistory {self.as_of_date} {self.market} "
            f"{self.selection_method} count={count}>"
        )
