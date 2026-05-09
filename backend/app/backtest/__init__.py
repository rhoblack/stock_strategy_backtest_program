"""백테스트 도메인 — 체결 모델, 백테스트 엔진, 결과 지표."""

from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel, TaxRateEntry
from app.backtest.metrics import calculate_metrics
from app.backtest.result import BacktestResult, DailyEquity
from app.backtest.tick import round_to_tick, tick_size_for

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "DailyEquity",
    "ExecutionModel",
    "TaxRateEntry",
    "calculate_metrics",
    "round_to_tick",
    "tick_size_for",
]
