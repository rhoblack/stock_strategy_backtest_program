"""Position 및 TradeGroup 데이터 모델.

설계서 05번 4절 + 정확성 정책 13.9 (추가매수 가중평균).

부분 매도가 핵심 차별 기능이므로 한 종목 보유 단위를 trade_group으로 쪼갠다.
하나의 Position은 여러 TradeGroup을 가질 수 있다 (allow_pyramiding=True 시).

부분 매도는 trade_group의 remaining_quantity만 줄이고 entry_price는 절대
바꾸지 않는다 — 정확성 정책 13.9.3 보장.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type


@dataclass
class TradeGroup:
    """매수 lot 1개. 부분 매도 진행 중에도 entry 정보 유지."""

    trade_group_id: int
    entry_date: date_type
    entry_price: float
    entry_quantity: int
    remaining_quantity: int


@dataclass
class Position:
    """한 종목의 보유 상태. 여러 TradeGroup을 묶어서 관리."""

    symbol: str
    name: str = ""
    current_price: float = 0.0
    peak_price: float = 0.0  # trailing_stop용 (전일까지의 high 갱신)
    trade_groups: list[TradeGroup] = field(default_factory=list)

    @property
    def quantity(self) -> int:
        """전체 trade_group의 remaining_quantity 합."""
        return sum(tg.remaining_quantity for tg in self.trade_groups)

    @property
    def avg_entry_price(self) -> float:
        """모든 trade_group의 가중평균 평단가. 보유 0이면 0."""
        total_qty = self.quantity
        if total_qty == 0:
            return 0.0
        return (
            sum(tg.entry_price * tg.remaining_quantity for tg in self.trade_groups)
            / total_qty
        )

    @property
    def entry_price(self) -> float:
        """포지션 조건 함수(03번 §14)가 요구하는 진입가 별칭.

        ConditionRegistry에 등록된 take_profit/stop_loss/trailing_stop 함수가
        `position.entry_price`를 읽도록 명세돼 있으므로, 가중평균 평단가를 그대로
        노출한다. 부분매도 후에도 entry_price는 갱신되지 않는다(13.9.3).
        """
        return self.avg_entry_price

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_profit(self) -> float:
        return (self.current_price - self.avg_entry_price) * self.quantity

    @property
    def unrealized_return_pct(self) -> float:
        if self.avg_entry_price == 0:
            return 0.0
        return (self.current_price - self.avg_entry_price) / self.avg_entry_price * 100

    @property
    def first_entry_date(self) -> date_type:
        """가장 오래된 trade_group의 entry_date (FIFO 기준)."""
        if not self.trade_groups:
            raise ValueError("보유 trade_group이 없습니다")
        return min(tg.entry_date for tg in self.trade_groups)
