"""SQLAlchemy 모델 패키지.

이 모듈을 import하면 모든 모델이 Base.metadata에 등록된다.
새 모델 추가 시 아래 import 목록에 추가할 것 (init_db / 마이그레이션 인식용).
"""

from app.models.backtest import BacktestResult, BacktestRun
from app.models.cash_event import CashEvent
from app.models.daily_equity import DailyEquity
from app.models.daily_price import DailyPrice
from app.models.enums import BacktestStatus, TradeExecutionType
from app.models.strategy import Strategy, StrategyVersion
from app.models.symbol import Symbol
from app.models.trade import TradeExecution, TradeGroup
from app.models.trading_calendar import TradingCalendar
from app.models.user import User

__all__ = [
    "BacktestResult",
    "BacktestRun",
    "BacktestStatus",
    "CashEvent",
    "DailyEquity",
    "DailyPrice",
    "Strategy",
    "StrategyVersion",
    "Symbol",
    "TradeExecution",
    "TradeExecutionType",
    "TradeGroup",
    "TradingCalendar",
    "User",
]
