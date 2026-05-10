"""PositionSizer — 매수 수량 계산기.

설계서 05번 §8.

지원 방식:
- fixed_amount:  config.position_size_amount 고정 금액 (하위 호환 default)
- fixed_ratio:   portfolio.total_equity() × sizing_ratio → 금액 → 수량
- equal_weight:  portfolio.total_equity() / max_positions → 균등 비중 → 수량

모듈 책임 분리 (04번 §3 + CLAUDE.md):
    체결가 계산(슬리피지·호가 단위)은 ExecutionModel 책임.
    매수 가능 현금 확인은 Portfolio 책임.
    PositionSizer는 오직 "주어진 exec_price에 대해 몇 주 살 것인가"만 결정한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.backtest.config import BacktestConfig
    from app.portfolio.portfolio import Portfolio


class PositionSizer:
    """매수 수량 계산기.

    config.sizing_method에 따라 매수 금액을 결정하고,
    exec_price로 나눠 정수 수량을 반환한다.

    exec_price <= 0 이면 0을 반환한다 (제로 나눗셈 방지).
    amount < exec_price 이면 0을 반환한다 (1주도 못 사는 상황).
    """

    def calculate_quantity(
        self,
        exec_price: float,
        portfolio: Portfolio,
        config: BacktestConfig,
    ) -> int:
        """매수 수량 계산. 0 이하 결과면 0 반환 (매수 불가 신호).

        Parameters
        ----------
        exec_price : float
            슬리피지·호가 단위가 이미 적용된 체결 예정가.
        portfolio : Portfolio
            총자산(total_equity) 조회에 사용.
            fixed_amount 방식에서는 portfolio 값을 읽지 않는다.
        config : BacktestConfig
            sizing_method / position_size_amount / sizing_ratio / max_positions
            필드를 읽는다.

        Returns
        -------
        int
            매수 수량. 0이면 매수 불가.
        """
        if exec_price <= 0:
            return 0

        method = config.sizing_method

        if method == "fixed_amount":
            amount: float = float(config.position_size_amount)
        elif method == "fixed_ratio":
            if config.sizing_ratio is None:
                raise ValueError(
                    "sizing_method='fixed_ratio'는 sizing_ratio가 필요합니다"
                )
            amount = portfolio.total_equity() * config.sizing_ratio
        elif method == "equal_weight":
            if config.max_positions is None:
                raise ValueError(
                    "sizing_method='equal_weight'는 max_positions가 필요합니다"
                )
            amount = portfolio.total_equity() / config.max_positions
        else:
            raise ValueError(f"지원하지 않는 sizing_method: {method!r}")

        return int(amount // exec_price)
