"""data_pipeline.collectors — 외부 데이터 소스에서 raw 수집 (14번 §5).

본 패키지는 BaseCollector 추상 베이스 + 구체 collector(PykrxCollector) +
재시도/검증 헬퍼를 제공한다.

타 모듈 사용법:
    from app.data_pipeline.collectors import (
        BaseCollector,
        PykrxCollector,
        RawSymbolsData,
        RawDailyPricesData,
        RawCalendarData,
        RetryableCollectorError,
        FatalCollectorError,
        retry_call,
        retry_on_retryable,
        validate_symbols_data,
        validate_daily_prices_data,
        validate_calendar_data,
    )
"""

from app.data_pipeline.collectors.base import (
    BaseCollector,
    RawCalendarData,
    RawCalendarRow,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawData,
    RawSymbolRow,
    RawSymbolsData,
)
from app.data_pipeline.collectors.pykrx import (
    SOURCE_NAME,
    PykrxCollector,
)
from app.data_pipeline.collectors.retry import (
    DEFAULT_BACKOFF_SECONDS,
    FatalCollectorError,
    RetryableCollectorError,
    retry_call,
    retry_on_retryable,
)
from app.data_pipeline.collectors.validators import (
    validate_calendar_data,
    validate_daily_price_row,
    validate_daily_prices_data,
    validate_symbol_row,
    validate_symbols_data,
)

__all__ = [
    # base
    "BaseCollector",
    "RawCalendarData",
    "RawCalendarRow",
    "RawData",
    "RawDailyPriceRow",
    "RawDailyPricesData",
    "RawSymbolRow",
    "RawSymbolsData",
    # pykrx collector
    "PykrxCollector",
    "SOURCE_NAME",
    # retry / 다중상속 구체 예외
    "DEFAULT_BACKOFF_SECONDS",
    "FatalCollectorError",
    "RetryableCollectorError",
    "retry_call",
    "retry_on_retryable",
    # validators
    "validate_calendar_data",
    "validate_daily_price_row",
    "validate_daily_prices_data",
    "validate_symbol_row",
    "validate_symbols_data",
]
