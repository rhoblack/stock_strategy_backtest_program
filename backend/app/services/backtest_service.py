"""Backtest 실행 + 영속화 서비스.

Phase 1 BacktestEngine을 호출하고 결과를 Phase 2 모델 (BacktestResult,
TradeGroup, TradeExecution, DailyEquity)로 매핑해 저장한다.

흐름:
    1. create_backtest_run: BacktestRun 인스턴스 생성 (status=PENDING)
    2. run_backtest(run_id, df): 엔진 실행 + 결과 영속화
       - 예외 발생 시 status=FAILED + error_message 저장
"""

from __future__ import annotations

import copy
import traceback
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.backtest.metrics import calculate_metrics
from app.core.exceptions import BacktestRunNotFoundError
from app.models.backtest import BacktestResult, BacktestRun
from app.models.cash_event import CashEvent
from app.models.daily_equity import DailyEquity
from app.models.enums import BacktestStatus, TradeExecutionType
from app.models.trade import TradeExecution, TradeGroup
from app.portfolio.cash_manager import CashManager
from app.portfolio.portfolio import Portfolio
from app.services.strategy_service import get_strategy
from app.strategy.engine import StrategyEngine


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_backtest_run(
    session: Session,
    *,
    user_id: int,
    strategy_id: int,
    run_name: str,
    universe_config: dict[str, Any],
    start_date: date,
    end_date: date,
    initial_cash: float,
    fee_rate: float,
    tax_rate: Any,  # float | list[dict]
    slippage: float,
    execution_price_type: str = "next_open",
    use_adjusted_price: bool = True,
    tick_rounding: str = "buy_up_sell_down",
    priority_method: str = "trading_value_desc",
    priority_tie_breaker: str = "symbol_asc",
    random_seed: int | None = None,
) -> BacktestRun:
    """전략 스냅샷 + 정확성 정책 스냅샷을 함께 저장.

    user_id 스코프 강제 (10번 9절): 호출자 user_id가 strategy의 소유자가
    아니면 get_strategy가 STRATEGY_NOT_FOUND를 raise한다.
    """
    # validator 호출 (백테스트 큐 진입 전 마지막 안전망 — strategy create 시점에
    # 통과했더라도 정책 추가 후 기존 전략에 잘못된 형태가 남아있을 수 있어 재검증)
    from app.schemas.strategy_json import validate_strategy_json

    strategy = get_strategy(session, strategy_id, user_id=user_id)
    validate_strategy_json(strategy.strategy_json)

    run = BacktestRun(
        user_id=user_id,
        strategy_id=strategy_id,
        run_name=run_name,
        strategy_snapshot_json=copy.deepcopy(strategy.strategy_json),
        universe_config_json=copy.deepcopy(universe_config),
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        tax_rate_json=tax_rate,
        slippage=slippage,
        execution_price_type=execution_price_type,
        use_adjusted_price=use_adjusted_price,
        tick_rounding=tick_rounding,
        priority_method=priority_method,
        priority_tie_breaker=priority_tie_breaker,
        random_seed=random_seed,
        status=BacktestStatus.PENDING,
        created_at=_utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def run_backtest(
    session: Session, run_id: int, df: pd.DataFrame | None = None
) -> BacktestResult:
    """주어진 df에 대해 엔진을 실행하고 결과를 영속화. 동기 실행.

    df=None이면 universe_config의 synthetic_seed/synthetic_n로 합성 데이터 생성
    (Phase 14 데이터 파이프라인 미구현 시 dev 모드).
    """
    run = _get_run(session, run_id)

    if df is None:
        from app.services.synthetic_data import build_synthetic_series

        cfg = run.universe_config_json or {}
        seed = int(cfg.get("synthetic_seed", 42))
        n = int(cfg.get("synthetic_n", 90))
        df = build_synthetic_series(seed=seed, n=n, base_date=run.start_date)

    # 상태 전이: PENDING → RUNNING
    run.status = BacktestStatus.RUNNING
    run.started_at = _utcnow()
    run.progress_pct = 0.0
    session.commit()

    try:
        # 단일 종목 가정: universe_config["symbol"] 또는 df의 첫 종목 코드
        symbol = run.universe_config_json.get("symbol", "UNKNOWN")

        portfolio = Portfolio(initial_cash=run.initial_cash)
        execution_model = ExecutionModel(
            fee_rate=run.fee_rate,
            tax_rate=run.tax_rate_json,
            slippage=run.slippage,
            use_adjusted_price=run.use_adjusted_price,
            tick_rounding=run.tick_rounding,
        )
        config = BacktestConfig(
            symbol=symbol,
            start_date=run.start_date,
            end_date=run.end_date,
            position_size_amount=run.universe_config_json.get(
                "position_size_amount", run.initial_cash
            ),
            initial_cash=run.initial_cash,
        )
        # CashManager에 ExecutionModel 주입 — 강제 매도도 슬리피지/호가/세금 적용
        # (리뷰 011 C2 해소). market은 단일 종목 가정으로 KOSPI 기본.
        cash_manager = CashManager(
            run.strategy_snapshot_json.get("cash_management"),
            execution_model=execution_model,
            market="KOSPI",
        )

        engine = BacktestEngine(
            StrategyEngine(run.strategy_snapshot_json),
            portfolio,
            execution_model,
            config,
            cash_manager=cash_manager,
        )

        engine_result = engine.run(df)
        metrics = calculate_metrics(engine_result)

        # 영속화
        backtest_result = _persist_summary(session, run, metrics)
        _persist_trade_groups_and_executions(session, run, engine_result.trade_executions)
        _persist_daily_equity(session, run, engine_result.daily_equity)
        _persist_cash_events(session, run, engine.cash_events)

        # 상태 전이: RUNNING → COMPLETED
        run.status = BacktestStatus.COMPLETED
        run.finished_at = _utcnow()
        run.progress_pct = 100.0
        session.commit()
        session.refresh(backtest_result)
        return backtest_result

    except Exception as exc:  # noqa: BLE001
        run.status = BacktestStatus.FAILED
        run.finished_at = _utcnow()
        run.error_message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"[:4000]
        session.commit()
        raise


def get_backtest_summary(
    session: Session, run_id: int, *, user_id: int | None = None
) -> dict:
    """run + result + 거래 카운트 등 요약 dict.

    user_id가 주어지면 본인 run만 — 미소유 시 BACKTEST_RUN_NOT_FOUND.
    """
    run = _get_run(session, run_id, user_id=user_id)
    result = run.result
    return {
        "run_id": run.id,
        "status": run.status.value,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "progress_pct": run.progress_pct,
        "error_message": run.error_message,
        "summary": _summary_dict(result) if result else None,
    }


# === 내부 ===


def _get_run(
    session: Session, run_id: int, *, user_id: int | None = None
) -> BacktestRun:
    """단일 BacktestRun 조회.

    user_id가 주어지면 본인 run만 — 미일치 시 NOT_FOUND (정보 누설 방지).
    user_id=None은 백그라운드 실행 등 신뢰 가능한 컨텍스트에서만 사용.
    """
    run = session.get(BacktestRun, run_id)
    if run is None:
        raise BacktestRunNotFoundError(f"BacktestRun id={run_id} 없음")
    if user_id is not None and run.user_id != user_id:
        raise BacktestRunNotFoundError(f"BacktestRun id={run_id} 없음")
    return run


def _summary_dict(result: BacktestResult) -> dict:
    return {
        "initial_cash": result.initial_cash,
        "final_equity": result.final_equity,
        "total_return_pct": result.total_return_pct,
        "annual_return_pct": result.annual_return_pct,
        "mdd_pct": result.mdd_pct,
        "trade_count": result.trade_count,
        "open_position_count": result.open_position_count,
        "win_rate": result.win_rate,
        "avg_holding_days": result.avg_holding_days,
        "avg_profit_pct": result.avg_profit_pct,
        "avg_loss_pct": result.avg_loss_pct,
        "profit_factor": result.profit_factor,
    }


def _persist_summary(session: Session, run: BacktestRun, metrics: dict) -> BacktestResult:
    pf = metrics["profit_factor"]
    # math.inf → None (DB Float에 inf 저장 회피)
    if pf is not None and not _is_finite(pf):
        pf = None

    result = BacktestResult(
        run_id=run.id,
        initial_cash=metrics["initial_cash"],
        final_equity=metrics["final_equity"],
        total_return_pct=metrics["total_return_pct"],
        annual_return_pct=metrics["annual_return_pct"],
        mdd_pct=metrics["mdd_pct"],
        trade_count=metrics["trade_count"],
        open_position_count=metrics["open_position_count"],
        win_rate=metrics["win_rate"],
        avg_holding_days=metrics["avg_holding_days"],
        avg_profit_pct=metrics["avg_profit_pct"],
        avg_loss_pct=metrics["avg_loss_pct"],
        profit_factor=pf,
    )
    session.add(result)
    session.flush()
    return result


def _is_finite(value: float) -> bool:
    import math

    return math.isfinite(value)


def _persist_trade_groups_and_executions(
    session: Session,
    run: BacktestRun,
    trade_executions: list[dict],
) -> None:
    """trade_logs를 trade_group으로 그룹화하여 영속화.

    in-memory trade_group_id를 DB pk로 매핑하기 위해 각 그룹의 BUY를 먼저 insert/flush하여
    PK를 발급받는다.
    """
    grouped: dict[int, list[dict]] = defaultdict(list)
    for ex in trade_executions:
        tg_id = ex.get("trade_group_id")
        if tg_id is None:
            continue
        grouped[tg_id].append(ex)

    tg_pk_map: dict[int, int] = {}

    for in_mem_tg_id, executions in grouped.items():
        buys = [e for e in executions if e["execution_type"] == "BUY"]
        sells = [e for e in executions if e["execution_type"] in ("SELL", "PARTIAL_SELL")]
        if not buys:
            continue
        buy = buys[0]

        sold_qty = sum(s["quantity"] for s in sells)
        fully_closed = sold_qty >= buy["quantity"]
        last_sell_date = max((s["date"] for s in sells), default=None)
        total_profit = sum(s.get("realized_profit", 0) or 0 for s in sells)
        invested = buy["price"] * buy["quantity"]
        total_profit_rate = (total_profit / invested * 100) if invested else 0.0

        tg = TradeGroup(
            run_id=run.id,
            symbol=buy["symbol"],
            name=buy.get("name", ""),
            entry_date=buy["date"],
            entry_price=buy["price"],
            entry_quantity=buy["quantity"],
            remaining_quantity=buy["quantity"] - sold_qty,
            fully_closed_at=(
                datetime.combine(last_sell_date, datetime.min.time(), tzinfo=UTC)
                if fully_closed and last_sell_date is not None
                else None
            ),
            final_profit=total_profit if fully_closed else None,
            final_profit_rate=total_profit_rate if fully_closed else None,
            created_at=_utcnow(),
        )
        session.add(tg)
        session.flush()
        tg_pk_map[in_mem_tg_id] = tg.id

    # executions insert — ExecutionResult dataclass 분해 결과를 그대로 매핑.
    # Portfolio.trade_logs에 이미 fee/tax/gross_amount/net_amount가 채워져 있다.
    # (013 step에서 ExecutionResult 도입 + portfolio.py가 dict 키로 펼쳐 기록)
    # 13.6 세율 시계열 + 13.5 호가 단위 적용 결과가 그대로 영속화된다.
    for in_mem_tg_id, executions in grouped.items():
        if in_mem_tg_id not in tg_pk_map:
            continue
        db_tg_id = tg_pk_map[in_mem_tg_id]
        for ex in executions:
            kind = ex["execution_type"]
            execution_type = TradeExecutionType(kind)

            # net_amount: BUY는 cost(=gross+fee), SELL은 proceeds(=gross-fee-tax).
            # ExecutionResult 도입 후 trade_logs에 net_amount 키가 직접 들어옴 —
            # 호환을 위해 cost/proceeds도 fallback으로 둔다.
            net = ex.get("net_amount")
            if net is None:
                net = ex.get("cost") if kind == "BUY" else ex.get("proceeds")
            if net is None:
                net = ex["price"] * ex["quantity"]

            # gross_amount는 ExecutionResult에서 price*quantity (체결가 기준).
            # fee/tax는 BUY=tax 0 강제, SELL=세율 시계열 13.6 결과.
            gross = ex.get("gross_amount", ex["price"] * ex["quantity"])
            fee = ex.get("fee", 0.0)
            tax = ex.get("tax", 0.0)

            session.add(
                TradeExecution(
                    trade_group_id=db_tg_id,
                    run_id=run.id,
                    execution_date=ex["date"],
                    execution_type=execution_type,
                    price=ex["price"],
                    quantity=ex["quantity"],
                    gross_amount=gross,
                    fee=fee,
                    tax=tax,
                    net_amount=net,
                    realized_profit=ex.get("realized_profit"),
                    realized_profit_rate=ex.get("realized_profit_rate"),
                    exit_reason=ex.get("reason") if kind != "BUY" else None,
                    created_at=_utcnow(),
                )
            )

    session.flush()


def _persist_daily_equity(
    session: Session,
    run: BacktestRun,
    daily_equities: list,
) -> None:
    """DailyEquity dataclass list → DB DailyEquity 행.

    daily_return / cumulative_return을 시퀀스 순회로 계산해 영속화한다 (M5).

    단위는 % (퍼센트). drawdown / mdd_pct가 이미 % 단위로 저장되므로
    동일 컬럼 그룹의 일관성을 위해 백분율을 사용한다 (07번 9절 + 09번 6절).

    공식 (07번 9절 + CLAUDE.md look-ahead bias 무관 — 종가 기준 사후 집계):
        daily_return[i] = (total_equity[i] - prev_equity) / prev_equity * 100
            * i=0 : prev_equity = run.initial_cash
            * i>0 : prev_equity = total_equity[i-1]
        cumulative_return[i] = (total_equity[i] - initial_cash) / initial_cash * 100

    일관성: ∏(1 + daily_return/100) - 1 ≈ cumulative_return/100.
    initial_cash가 0이면 비율 계산 불가 → 0 반환 (DB NOT NULL 만족).
    """
    initial_cash = float(run.initial_cash) if run.initial_cash else 0.0

    rows: list[DailyEquity] = []
    prev_equity = initial_cash
    for eq in daily_equities:
        daily_ret = (
            (eq.total_equity - prev_equity) / prev_equity * 100
            if prev_equity > 0
            else 0.0
        )
        cum_ret = (
            (eq.total_equity - initial_cash) / initial_cash * 100
            if initial_cash > 0
            else 0.0
        )

        rows.append(
            DailyEquity(
                run_id=run.id,
                date=eq.date,
                cash=eq.cash,
                stock_value=eq.stock_value,
                total_equity=eq.total_equity,
                daily_return=daily_ret,
                cumulative_return=cum_ret,
                drawdown=eq.drawdown,
                positions_count=eq.positions_count,
                created_at=_utcnow(),
            )
        )
        prev_equity = eq.total_equity

    session.add_all(rows)
    session.flush()


def _persist_cash_events(session: Session, run: BacktestRun, events: list[dict]) -> None:
    """CashManager 이벤트 영속화 (07번 10절 + 014 비용 분해 매핑).

    CashManager가 ExecutionModel을 거쳐 강제 매도하면 cash_event dict에
    exec_price/raw_price/gross_amount/fee/tax/net_amount가 채워져 들어온다 —
    그대로 매핑한다 (013 step 결과). dev/legacy 경로(ExecutionModel 미주입)에서는
    해당 키들이 없을 수 있으므로 .get()으로 None 허용.
    sell_amount는 호환을 위해 net_amount과 동일 값 유지.
    """
    rows = [
        CashEvent(
            run_id=run.id,
            date=ev["date"],
            event_type=ev.get("event_type", "cash_shortage"),
            cash_before=ev.get("cash_before", 0.0),
            required_cash=ev.get("required_cash"),
            cash_after=ev.get("cash_after", 0.0),
            action=ev.get("action"),
            symbol=ev.get("symbol"),
            sell_quantity=ev.get("sell_quantity"),
            sell_amount=ev.get("sell_amount"),
            # 014 신규 분해 컬럼 — ExecutionModel 분해 결과
            exec_price=ev.get("exec_price"),
            raw_price=ev.get("raw_price"),
            gross_amount=ev.get("gross_amount"),
            fee=ev.get("fee"),
            tax=ev.get("tax"),
            net_amount=ev.get("net_amount"),
            reason=ev.get("reason"),
            created_at=_utcnow(),
        )
        for ev in events
    ]
    if rows:
        session.add_all(rows)
        session.flush()
