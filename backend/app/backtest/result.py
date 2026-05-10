"""백테스트 결과 객체.

설계서 04번 12절 + 07번 daily_equity / trade_executions 스키마를
런타임 dataclass로 표현. DB 저장은 Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type


@dataclass
class DailyEquity:
    """일별 자산 스냅샷 (07번 9절 daily_equity와 매핑)."""

    date: date_type
    cash: float
    stock_value: float
    total_equity: float
    drawdown: float = 0.0  # 누적 최고점 대비 -%
    positions_count: int = 0


@dataclass
class BacktestResult:
    """단일 백테스트 실행 결과 컨테이너.

    Phase 1에서는 list로 보관. Phase 2에서 DB 저장 + summary metrics 추가.

    Phase 10 step 023 — event_log 필드 추가 (04-n + 13-p + 13-q).
    BacktestEngine.event_log를 그대로 옮겨 영속화 가능한 형태로 노출.
    각 항목은 dict이며 키 명세는 BacktestEngine._log_event 참조:
        {
          "date": date_type,                # 발생일 (today)
          "symbol": str,                    # 대상 종목 코드
          "event_type": str,                # "skip" | "force_sell"
          "reason": str,                    # 표준 사유 코드 (engine.py 상수 참조)
          "detail": dict[str, Any],         # 사유별 추가 정보 (cumulative cost 등)
        }
    DB 영속화는 후속 step (event_log DB 모델 + alembic + service 매핑).
    """

    daily_equity: list[DailyEquity] = field(default_factory=list)
    trade_executions: list[dict] = field(default_factory=list)
    event_log: list[dict] = field(default_factory=list)
    final_cash: float = 0.0
    final_equity: float = 0.0
    initial_cash: float = 0.0

    @property
    def total_return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.final_equity - self.initial_cash) / self.initial_cash * 100

    @property
    def trade_count(self) -> int:
        """매수 → 매도 페어 수가 아닌 SELL execution 수.

        부분 매도가 있으면 그 수만큼 카운트. Phase 8 Metrics에서 trade_group
        단위 집계로 보강.
        """
        return sum(1 for ex in self.trade_executions if ex["execution_type"] in ("SELL", "PARTIAL_SELL"))
