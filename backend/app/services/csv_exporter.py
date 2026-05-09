"""CSV / ZIP Export (설계서 09번).

UTF-8 with BOM 기본 (Excel 호환). KRW 통화는 정수.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile

from sqlalchemy.orm import Session

from app.models.backtest import BacktestRun
from app.models.cash_event import CashEvent
from app.models.daily_equity import DailyEquity
from app.models.trade import TradeExecution, TradeGroup

UTF8_BOM = "﻿"


def _to_csv(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    buf.write(UTF8_BOM)
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def export_summary_csv(session: Session, run: BacktestRun) -> str:
    result = run.result
    row = {
        "run_id": run.id,
        "strategy_id": run.strategy_id,
        "run_name": run.run_name,
        "start_date": run.start_date.isoformat(),
        "end_date": run.end_date.isoformat(),
        "initial_cash": run.initial_cash,
        "final_equity": result.final_equity if result else "",
        "total_return_pct": result.total_return_pct if result else "",
        "annual_return_pct": result.annual_return_pct if result else "",
        "mdd_pct": result.mdd_pct if result else "",
        "trade_count": result.trade_count if result else 0,
        "win_rate": result.win_rate if result else "",
        "avg_holding_days": result.avg_holding_days if result else "",
        "profit_factor": result.profit_factor if result else "",
        "status": run.status.value,
    }
    return _to_csv([row], list(row.keys()))


def export_trades_csv(session: Session, run: BacktestRun) -> str:
    rows = []
    tgs = (
        session.query(TradeGroup)
        .filter_by(run_id=run.id)
        .order_by(TradeGroup.entry_date)
        .all()
    )
    for tg in tgs:
        execs = (
            session.query(TradeExecution)
            .filter_by(trade_group_id=tg.id)
            .order_by(TradeExecution.execution_date)
            .all()
        )
        last_sell = next(
            (e for e in reversed(execs) if e.execution_type.value != "BUY"), None
        )
        rows.append({
            "trade_group_id": tg.id,
            "symbol": tg.symbol,
            "name": tg.name,
            "entry_date": tg.entry_date.isoformat(),
            "entry_price": tg.entry_price,
            "entry_quantity": tg.entry_quantity,
            "exit_date": last_sell.execution_date.isoformat() if last_sell else "",
            "exit_price": last_sell.price if last_sell else "",
            "exit_reason": last_sell.exit_reason if last_sell else "",
            "remaining_quantity": tg.remaining_quantity,
            "realized_profit": tg.final_profit if tg.final_profit is not None else "",
            "realized_profit_pct": tg.final_profit_rate if tg.final_profit_rate is not None else "",
        })
    return _to_csv(rows, [
        "trade_group_id", "symbol", "name",
        "entry_date", "entry_price", "entry_quantity",
        "exit_date", "exit_price", "exit_reason",
        "remaining_quantity", "realized_profit", "realized_profit_pct",
    ])


def export_daily_equity_csv(session: Session, run: BacktestRun) -> str:
    rows = (
        session.query(DailyEquity)
        .filter_by(run_id=run.id)
        .order_by(DailyEquity.date)
        .all()
    )
    return _to_csv(
        [
            {
                "date": eq.date.isoformat(),
                "cash": eq.cash,
                "stock_value": eq.stock_value,
                "total_equity": eq.total_equity,
                "drawdown_pct": eq.drawdown,
                "positions_count": eq.positions_count,
            }
            for eq in rows
        ],
        ["date", "cash", "stock_value", "total_equity", "drawdown_pct", "positions_count"],
    )


def export_cash_events_csv(session: Session, run: BacktestRun) -> str:
    rows = (
        session.query(CashEvent)
        .filter_by(run_id=run.id)
        .order_by(CashEvent.date)
        .all()
    )
    return _to_csv(
        [
            {
                "date": ev.date.isoformat(),
                "event_type": ev.event_type,
                "cash_before": ev.cash_before,
                "required_cash": ev.required_cash if ev.required_cash is not None else "",
                "cash_after": ev.cash_after,
                "action": ev.action or "",
                "symbol": ev.symbol or "",
                "sell_quantity": ev.sell_quantity if ev.sell_quantity is not None else "",
                "sell_amount": ev.sell_amount if ev.sell_amount is not None else "",
                "reason": ev.reason or "",
            }
            for ev in rows
        ],
        ["date", "event_type", "cash_before", "required_cash", "cash_after",
         "action", "symbol", "sell_quantity", "sell_amount", "reason"],
    )


def export_strategy_snapshot_json(run: BacktestRun) -> str:
    return json.dumps(run.strategy_snapshot_json, ensure_ascii=False, indent=2)


def export_zip(session: Session, run: BacktestRun) -> bytes:
    """5개 CSV + strategy_snapshot.json을 ZIP으로 묶음."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.csv", export_summary_csv(session, run))
        zf.writestr("trades.csv", export_trades_csv(session, run))
        zf.writestr("daily_equity.csv", export_daily_equity_csv(session, run))
        zf.writestr("cash_events.csv", export_cash_events_csv(session, run))
        zf.writestr(
            "strategy_snapshot.json",
            export_strategy_snapshot_json(run),
        )
    return buf.getvalue()
