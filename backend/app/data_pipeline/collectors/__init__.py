"""data_pipeline.collectors — 외부 데이터 소스에서 raw 수집 (14번 §5).

본 패키지는 BaseCollector 추상 베이스만 제공한다.
실제 PykrxCollector / FinanceDataReaderCollector는 025~ 후속 step.

타 모듈 사용법:
    from app.data_pipeline.collectors import (
        BaseCollector,
        RawSymbolsData,
        RawDailyPricesData,
        RawCalendarData,
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

__all__ = [
    "BaseCollector",
    "RawCalendarData",
    "RawCalendarRow",
    "RawData",
    "RawDailyPriceRow",
    "RawDailyPricesData",
    "RawSymbolRow",
    "RawSymbolsData",
]
