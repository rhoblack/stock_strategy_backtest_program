"""백테스트 결과 지표 계산.

설계서 04번 13절의 MVP 지표.
trade_group 단위로 집계하여 부분매도가 여러 번 발생해도 한 거래로 카운트.

지표 단위:
    - 수익률 / MDD: 백분율 (예: 84.2 = 84.2%)
    - 거래 횟수 / 보유일: 정수
    - profit_factor: 비율 (손실 0이면 None)
"""

from __future__ import annotations

import math
from collections import defaultdict

from app.backtest.result import BacktestResult


def calculate_metrics(result: BacktestResult) -> dict:
    """전체 지표를 dict로 반환.

    반환 키: total_return_pct, annual_return_pct, mdd_pct, trade_count,
    win_rate, avg_holding_days, avg_profit_pct, avg_loss_pct, profit_factor,
    open_position_count, final_equity, initial_cash.
    """
    by_tg = _group_by_trade_group(result.trade_executions)

    closed_trades: list[dict] = []
    open_trades_count = 0

    for tg_id, executions in by_tg.items():
        buys = [e for e in executions if e["execution_type"] == "BUY"]
        sells = [e for e in executions if e["execution_type"] in ("SELL", "PARTIAL_SELL")]
        if not buys:
            # 비정상 — 매수 없이 trade_group 존재. skip.
            continue
        if not sells:
            open_trades_count += 1
            continue

        # 한 trade_group은 매수 1건 + 매도 N건 (부분매도) 가정
        buy = buys[0]
        entry_date = buy["date"]
        entry_qty = buy["quantity"]

        # 모든 SELL/PARTIAL_SELL의 quantity 합 == entry_qty이면 청산 완료
        sold_qty = sum(s["quantity"] for s in sells)
        if sold_qty < entry_qty:
            # 부분 매도만 진행되고 청산 미완료
            open_trades_count += 1
            continue

        last_exit_date = max(s["date"] for s in sells)
        holding_days = max(1, (last_exit_date - entry_date).days)

        total_realized = sum(s["realized_profit"] for s in sells)
        # 평균단가 기준 수익률 (각 매도가 같은 entry_price를 봐서 동일)
        # → trade_group 전체 수익률 = 총 실현 / (entry_price * entry_qty)
        invested_amount = buy["price"] * entry_qty
        profit_rate = (
            0.0 if invested_amount == 0 else total_realized / invested_amount * 100
        )

        closed_trades.append(
            {
                "trade_group_id": tg_id,
                "entry_date": entry_date,
                "exit_date": last_exit_date,
                "holding_days": holding_days,
                "realized_profit": total_realized,
                "profit_rate_pct": profit_rate,
            }
        )

    trade_count = len(closed_trades)

    if trade_count > 0:
        wins = [t for t in closed_trades if t["realized_profit"] > 0]
        losses = [t for t in closed_trades if t["realized_profit"] < 0]

        win_rate = len(wins) / trade_count * 100
        avg_holding_days = sum(t["holding_days"] for t in closed_trades) / trade_count
        avg_profit_pct = (
            sum(t["profit_rate_pct"] for t in wins) / len(wins) if wins else 0.0
        )
        avg_loss_pct = (
            -sum(t["profit_rate_pct"] for t in losses) / len(losses) if losses else 0.0
        )

        total_win_amount = sum(t["realized_profit"] for t in wins)
        total_loss_amount = -sum(t["realized_profit"] for t in losses)
        if total_loss_amount > 0:
            profit_factor: float | None = total_win_amount / total_loss_amount
        elif total_win_amount > 0:
            profit_factor = math.inf
        else:
            profit_factor = None
    else:
        win_rate = 0.0
        avg_holding_days = 0.0
        avg_profit_pct = 0.0
        avg_loss_pct = 0.0
        profit_factor = None

    mdd_pct = _calculate_mdd_pct(result)
    annual_return_pct = _calculate_annual_return_pct(result)

    return {
        "initial_cash": result.initial_cash,
        "final_equity": result.final_equity,
        "total_return_pct": result.total_return_pct,
        "annual_return_pct": annual_return_pct,
        "mdd_pct": mdd_pct,
        "trade_count": trade_count,
        "open_position_count": open_trades_count,
        "win_rate": win_rate,
        "avg_holding_days": avg_holding_days,
        "avg_profit_pct": avg_profit_pct,
        "avg_loss_pct": avg_loss_pct,
        "profit_factor": profit_factor,
    }


def _group_by_trade_group(executions: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for ex in executions:
        tg_id = ex.get("trade_group_id")
        if tg_id is None:
            continue
        grouped[tg_id].append(ex)
    return grouped


def _calculate_mdd_pct(result: BacktestResult) -> float:
    """daily_equity의 최대 낙폭 (음수 백분율)."""
    if not result.daily_equity:
        return 0.0
    return min((eq.drawdown for eq in result.daily_equity), default=0.0)


def _calculate_annual_return_pct(result: BacktestResult) -> float:
    """CAGR 계산. 기간 1년 미만이면 그냥 total_return을 연환산.

    공식: (final / initial)^(365/days) - 1
    초기 자본이 0이면 0 반환.
    """
    if not result.daily_equity or result.initial_cash == 0:
        return 0.0

    first_date = result.daily_equity[0].date
    last_date = result.daily_equity[-1].date
    days = max(1, (last_date - first_date).days)

    ratio = result.final_equity / result.initial_cash
    if ratio <= 0:
        # 자본이 0 또는 음수가 되었음
        return -100.0

    return (ratio ** (365 / days) - 1) * 100
