"""PykrxCollector + validators 테스트 (Phase 11 step 025).

검증 항목:
    A) 외부 fetch 격리 — _fetch_* 메서드를 mock으로 교체해 외부 호출 0건
    B) collect_symbols / collect_daily_prices / collect_trading_calendar 정상 흐름
    C) 출력 정렬 결정론 (BaseCollector 헬퍼 활용)
    D) 14번 §7 검증 정책:
        - HARD_FAIL → DataValidationError raise
        - SOFT_FAIL → ValidationIssue 누적, 통과
    E) 결손 봉 미생성 (14.10 forward-fill 금지)
    F) 입력 검증 (start_date > end_date / 잘못된 market) → FatalCollectorError
    G) lazy import — pykrx 미설치 시 FatalCollectorError
    H) retry 적용 — RetryableCollectorError 발생 시 collector 진입점에서 재시도

외부 fetch / DB / 실 sleep 0건.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.data_pipeline.collectors.base import (
    RawCalendarData,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawSymbolRow,
    RawSymbolsData,
)
from app.data_pipeline.collectors.pykrx import (
    SOURCE_NAME,
    PykrxCollector,
    _format_date,
    _parse_date,
)
from app.data_pipeline.collectors.retry import (
    FatalCollectorError,
    RetryableCollectorError,
)
from app.data_pipeline.collectors.validators import (
    validate_calendar_data,
    validate_daily_price_row,
    validate_daily_prices_data,
    validate_symbol_row,
    validate_symbols_data,
)
from app.data_pipeline.exceptions import DataValidationError
from app.data_pipeline.processors.base import ValidationResult

# ---------------------------------------------------------------------------
# 픽스처 — 합성 pykrx-like DataFrame
# ---------------------------------------------------------------------------


def _make_ohlcv_df(
    dates: Iterable[date],
    *,
    open_: float = 100,
    high: float = 110,
    low: float = 95,
    close: float = 105,
    volume: float = 1000,
) -> pd.DataFrame:
    """pykrx의 get_market_ohlcv_by_date 반환 모양으로 합성 DataFrame 생성.

    pykrx는 컬럼명이 한국어 (시가/고가/저가/종가/거래량/거래대금/등락률).
    index는 'YYYYMMDD' 문자열 또는 datetime.
    """
    return pd.DataFrame(
        {
            "시가": [open_] * len(list(dates)),
            "고가": [high] * len(list(dates)),
            "저가": [low] * len(list(dates)),
            "종가": [close] * len(list(dates)),
            "거래량": [volume] * len(list(dates)),
            "거래대금": [close * volume] * len(list(dates)),
            "등락률": [0.0] * len(list(dates)),
        },
        index=[d.strftime("%Y%m%d") for d in dates],
    )


def _make_market_cap_df(
    dates: Iterable[date],
    *,
    cap: float = 1_000_000_000,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "시가총액": [cap] * len(list(dates)),
            "거래량": [0.0] * len(list(dates)),
            "거래대금": [0.0] * len(list(dates)),
            "상장주식수": [10_000_000.0] * len(list(dates)),
        },
        index=[d.strftime("%Y%m%d") for d in dates],
    )


@pytest.fixture
def collector_no_sleep() -> PykrxCollector:
    """sleep을 mock으로 교체한 collector — 모든 retry가 즉시."""
    return PykrxCollector(backoff=(), sleep_fn=lambda _s: None)


# ---------------------------------------------------------------------------
# A) 헬퍼 함수
# ---------------------------------------------------------------------------


def test_format_date_yyyymmdd() -> None:
    assert _format_date(date(2024, 1, 2)) == "20240102"
    assert _format_date(date(2024, 12, 31)) == "20241231"


def test_parse_date_string_and_date() -> None:
    assert _parse_date("20240102") == date(2024, 1, 2)
    assert _parse_date(date(2024, 1, 2)) == date(2024, 1, 2)


# ---------------------------------------------------------------------------
# B) collect_symbols — mock 기반
# ---------------------------------------------------------------------------


def test_collect_symbols_basic_flow(collector_no_sleep: PykrxCollector) -> None:
    """mock된 ticker_list/ticker_name으로 RawSymbolsData 구성."""
    collector_no_sleep._fetch_ticker_list = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            ["005930", "000020"],  # KOSPI
            ["035720"],  # KOSDAQ
        ]
    )
    collector_no_sleep._fetch_ticker_name = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda t: {"005930": "삼성전자", "000020": "동화약품", "035720": "카카오"}[t]
    )

    result = collector_no_sleep.collect_symbols(date(2024, 1, 2))

    assert isinstance(result, RawSymbolsData)
    assert result.source == SOURCE_NAME
    assert result.as_of_date == date(2024, 1, 2)
    # symbol ASC 정렬 확인 (000020, 005930, 035720)
    assert [r.symbol for r in result.rows] == ["000020", "005930", "035720"]
    # market 매핑 확인
    market_map = {r.symbol: r.market for r in result.rows}
    assert market_map["005930"] == "KOSPI"
    assert market_map["000020"] == "KOSPI"
    assert market_map["035720"] == "KOSDAQ"


def test_collect_symbols_validates_symbol_format(
    collector_no_sleep: PykrxCollector,
) -> None:
    """잘못된 형식의 ticker가 포함되면 HARD_FAIL → DataValidationError."""
    collector_no_sleep._fetch_ticker_list = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            ["005930", "BAD"],  # 'BAD'는 6자리 숫자 아님
            [],
        ]
    )
    collector_no_sleep._fetch_ticker_name = MagicMock(  # type: ignore[method-assign]
        return_value="이름"
    )

    with pytest.raises(DataValidationError, match="SYMBOL_FORMAT_INVALID"):
        collector_no_sleep.collect_symbols(date(2024, 1, 2))


def test_collect_symbols_validation_off(collector_no_sleep: PykrxCollector) -> None:
    """validate=False면 hard_fail이어도 raise하지 않고 데이터 반환."""
    collector_no_sleep._validate = False
    collector_no_sleep._fetch_ticker_list = MagicMock(  # type: ignore[method-assign]
        side_effect=[["005930", "BAD"], []]
    )
    collector_no_sleep._fetch_ticker_name = MagicMock(  # type: ignore[method-assign]
        return_value="이름"
    )

    result = collector_no_sleep.collect_symbols(date(2024, 1, 2))
    assert len(result.rows) == 2  # BAD도 포함되어 반환


# ---------------------------------------------------------------------------
# C) collect_daily_prices — mock 기반
# ---------------------------------------------------------------------------


def test_collect_daily_prices_basic_flow(collector_no_sleep: PykrxCollector) -> None:
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    df_raw = _make_ohlcv_df(dates, open_=100, high=110, low=95, close=105)
    df_adj = _make_ohlcv_df(dates, open_=100, high=110, low=95, close=105)
    df_cap = _make_market_cap_df(dates, cap=2_000_000_000)

    collector_no_sleep._fetch_ohlcv = MagicMock(  # type: ignore[method-assign]
        side_effect=[df_raw, df_adj]
    )
    collector_no_sleep._fetch_market_cap = MagicMock(return_value=df_cap)  # type: ignore[method-assign]

    result = collector_no_sleep.collect_daily_prices(
        ["005930"], date(2024, 1, 1), date(2024, 1, 31)
    )

    assert isinstance(result, RawDailyPricesData)
    assert result.source == SOURCE_NAME
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "005930"
    assert result.rows[0].date == date(2024, 1, 2)
    assert result.rows[0].close == 105.0
    assert result.rows[0].adj_close == 105.0
    assert result.rows[0].market_cap == 2_000_000_000.0


def test_collect_daily_prices_sorted_by_symbol_then_date(
    collector_no_sleep: PykrxCollector,
) -> None:
    """여러 종목 결과가 (symbol ASC, date ASC) 정렬."""
    dates = [date(2024, 1, 2), date(2024, 1, 3)]

    def fake_ohlcv(start: str, end: str, sym: str, adjusted: bool) -> pd.DataFrame:
        return _make_ohlcv_df(dates, close=100 if sym == "005930" else 200)

    def fake_cap(start: str, end: str, sym: str) -> pd.DataFrame:
        return _make_market_cap_df(dates)

    collector_no_sleep._fetch_ohlcv = MagicMock(side_effect=fake_ohlcv)  # type: ignore[method-assign]
    collector_no_sleep._fetch_market_cap = MagicMock(side_effect=fake_cap)  # type: ignore[method-assign]

    # 입력 순서를 일부러 역순 (035720 먼저)
    result = collector_no_sleep.collect_daily_prices(
        ["035720", "005930"], date(2024, 1, 1), date(2024, 1, 31)
    )

    # 결정론: (symbol ASC, date ASC)
    keys = [(r.symbol, r.date) for r in result.rows]
    assert keys == [
        ("005930", date(2024, 1, 2)),
        ("005930", date(2024, 1, 3)),
        ("035720", date(2024, 1, 2)),
        ("035720", date(2024, 1, 3)),
    ]


def test_collect_daily_prices_raises_on_hard_fail_close(
    collector_no_sleep: PykrxCollector,
) -> None:
    """close=0인 row가 포함되면 HARD_FAIL → DataValidationError."""
    dates = [date(2024, 1, 2)]
    df_raw = _make_ohlcv_df(dates, close=0)  # HARD: close <= 0
    df_adj = _make_ohlcv_df(dates, close=100)

    collector_no_sleep._fetch_ohlcv = MagicMock(side_effect=[df_raw, df_adj])  # type: ignore[method-assign]
    collector_no_sleep._fetch_market_cap = MagicMock(  # type: ignore[method-assign]
        return_value=_make_market_cap_df(dates)
    )

    with pytest.raises(DataValidationError, match="PRICE_CLOSE_NULL_OR_NONPOSITIVE"):
        collector_no_sleep.collect_daily_prices(
            ["005930"], date(2024, 1, 1), date(2024, 1, 31)
        )


def test_collect_daily_prices_soft_fail_market_cap_missing(
    collector_no_sleep: PykrxCollector,
) -> None:
    """시가총액 결손은 SOFT_FAIL — collect는 통과, validation 결과로만 노출."""
    dates = [date(2024, 1, 2)]
    df_raw = _make_ohlcv_df(dates, close=100)
    df_adj = _make_ohlcv_df(dates, close=100)

    collector_no_sleep._fetch_ohlcv = MagicMock(side_effect=[df_raw, df_adj])  # type: ignore[method-assign]
    # market_cap 조회 실패 시 _fetch_market_cap이 FatalCollectorError 던지면 collect는 SOFT 경고로 처리
    collector_no_sleep._fetch_market_cap = MagicMock(  # type: ignore[method-assign]
        side_effect=FatalCollectorError("cap unavailable")
    )

    # collect_daily_prices가 hard 검증을 통과해야 함 (cap=None은 SOFT)
    result = collector_no_sleep.collect_daily_prices(
        ["005930"], date(2024, 1, 1), date(2024, 1, 31)
    )
    assert len(result.rows) == 1
    assert result.rows[0].market_cap is None
    # 경고에 시가총액 조회 실패 메시지 누적
    assert any("시가총액" in w for w in result.warnings)

    # 별도 검증 호출 시 SOFT_FAIL 누적 확인
    vr = validate_daily_prices_data(result, raise_on_hard_fail=False)
    assert vr.passed is True
    codes = {i.code for i in vr.issues}
    assert "MARKET_CAP_MISSING" in codes


def test_collect_daily_prices_drops_empty_raw_rows(
    collector_no_sleep: PykrxCollector,
) -> None:
    """raw OHLCV가 빈 DataFrame이면 row 0개 + 경고만 (14.10 결손 봉 미생성)."""
    empty_df = pd.DataFrame(
        {"시가": [], "고가": [], "저가": [], "종가": [], "거래량": [],
         "거래대금": [], "등락률": []}
    )

    collector_no_sleep._fetch_ohlcv = MagicMock(side_effect=[empty_df, empty_df])  # type: ignore[method-assign]
    collector_no_sleep._fetch_market_cap = MagicMock(return_value=None)  # type: ignore[method-assign]
    # 빈 결과는 검증 자체에서 hard가 아님 (rows가 0건이면 validate_daily_prices_data는 통과)
    result = collector_no_sleep.collect_daily_prices(
        ["005930"], date(2024, 1, 1), date(2024, 1, 31)
    )
    assert result.rows == ()
    assert any("OHLCV(raw) 결과 없음" in w for w in result.warnings)


def test_collect_daily_prices_invalid_date_range_raises_fatal(
    collector_no_sleep: PykrxCollector,
) -> None:
    with pytest.raises(FatalCollectorError, match="start_date > end_date"):
        collector_no_sleep.collect_daily_prices(
            ["005930"], date(2024, 2, 1), date(2024, 1, 1)
        )


# ---------------------------------------------------------------------------
# D) collect_trading_calendar — mock 기반
# ---------------------------------------------------------------------------


def test_collect_trading_calendar_basic_flow(
    collector_no_sleep: PykrxCollector,
) -> None:
    business_days = ["20240102", "20240103", "20240104"]
    collector_no_sleep._fetch_business_days = MagicMock(return_value=business_days)  # type: ignore[method-assign]

    result = collector_no_sleep.collect_trading_calendar(
        date(2024, 1, 1), date(2024, 1, 31), "KOSPI"
    )

    assert isinstance(result, RawCalendarData)
    assert result.market == "KOSPI"
    assert result.source == SOURCE_NAME
    assert len(result.rows) == 3
    assert all(r.is_trading_day for r in result.rows)
    # 정렬 확인
    assert [r.date for r in result.rows] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
    ]


def test_collect_trading_calendar_invalid_market_raises_fatal(
    collector_no_sleep: PykrxCollector,
) -> None:
    with pytest.raises(FatalCollectorError, match="지원하지 않는 시장"):
        collector_no_sleep.collect_trading_calendar(
            date(2024, 1, 1), date(2024, 1, 31), "NASDAQ"
        )


def test_collect_trading_calendar_empty_raises_hard_fail(
    collector_no_sleep: PykrxCollector,
) -> None:
    """거래일 캘린더가 비어 있으면 14번 §7.2에 따라 HARD_FAIL."""
    collector_no_sleep._fetch_business_days = MagicMock(return_value=[])  # type: ignore[method-assign]

    with pytest.raises(DataValidationError, match="CALENDAR_EMPTY"):
        collector_no_sleep.collect_trading_calendar(
            date(2024, 1, 1), date(2024, 1, 31), "KOSPI"
        )


# ---------------------------------------------------------------------------
# E) retry 적용 — RetryableCollectorError 발생 시 재시도
# ---------------------------------------------------------------------------


def test_collect_symbols_retries_on_retryable_error() -> None:
    """첫 호출 RetryableCollectorError, 두 번째 성공 — 결과는 두 번째 호출 기준."""
    sleeps: list[float] = []
    collector = PykrxCollector(backoff=(0.1,), sleep_fn=sleeps.append)
    collector._fetch_ticker_list = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            RetryableCollectorError("503"),  # 첫 호출 실패
            ["005930"],  # 재시도 성공 (KOSPI)
            [],  # KOSDAQ 호출
        ]
    )
    collector._fetch_ticker_name = MagicMock(return_value="삼성전자")  # type: ignore[method-assign]

    result = collector.collect_symbols(date(2024, 1, 2))

    assert [r.symbol for r in result.rows] == ["005930"]
    # sleep은 KOSPI 재시도 1회만
    assert sleeps == [0.1]


def test_collect_symbols_does_not_retry_on_fatal() -> None:
    """FatalCollectorError는 재시도 없이 즉시 raise."""
    sleeps: list[float] = []
    collector = PykrxCollector(backoff=(0.1, 0.2), sleep_fn=sleeps.append)
    collector._fetch_ticker_list = MagicMock(  # type: ignore[method-assign]
        side_effect=FatalCollectorError("auth")
    )
    collector._fetch_ticker_name = MagicMock(return_value="x")  # type: ignore[method-assign]

    with pytest.raises(FatalCollectorError):
        collector.collect_symbols(date(2024, 1, 2))

    assert sleeps == []  # 재시도 없음


# ---------------------------------------------------------------------------
# F) lazy import — pykrx 미설치 시 FatalCollectorError
# ---------------------------------------------------------------------------


def test_import_stock_raises_fatal_when_pykrx_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pykrx 미설치 환경에서 _import_stock() 호출 시 FatalCollectorError."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "pykrx" or name.startswith("pykrx."):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(FatalCollectorError, match="pykrx 라이브러리가 설치되지 않았"):
        PykrxCollector._import_stock()


# ---------------------------------------------------------------------------
# G) 생성자 검증
# ---------------------------------------------------------------------------


def test_pykrx_collector_default_name() -> None:
    c = PykrxCollector()
    assert c.name == SOURCE_NAME == "pykrx"


def test_pykrx_collector_invalid_market_raises_fatal() -> None:
    with pytest.raises(FatalCollectorError, match="지원하지 않는 시장"):
        PykrxCollector(markets=("NASDAQ",))


# ---------------------------------------------------------------------------
# H) validators 단위 테스트 — 14번 §7.1 / §7.2 매핑
# ---------------------------------------------------------------------------


def test_validate_symbol_row_valid() -> None:
    row = RawSymbolRow(
        symbol="005930", name="삼성전자", market="KOSPI",
        listing_date=date(1975, 6, 11),
    )
    assert validate_symbol_row(row) == []


def test_validate_symbol_row_format_violation_is_hard() -> None:
    row = RawSymbolRow(
        symbol="ABCDEF", name="x", market="KOSPI",
        listing_date=date(2024, 1, 1),
    )
    issues = validate_symbol_row(row)
    assert any(
        i.code == "SYMBOL_FORMAT_INVALID" and i.severity == "hard_fail"
        for i in issues
    )


def test_validate_symbol_row_invalid_market_is_hard() -> None:
    row = RawSymbolRow(
        symbol="005930", name="삼성전자", market="NASDAQ",
        listing_date=date(2024, 1, 1),
    )
    issues = validate_symbol_row(row)
    assert any(
        i.code == "SYMBOL_MARKET_INVALID" and i.severity == "hard_fail"
        for i in issues
    )


def test_validate_symbol_row_delisted_before_listed_is_hard() -> None:
    row = RawSymbolRow(
        symbol="005930", name="x", market="KOSPI",
        listing_date=date(2024, 1, 10),
        delisting_date=date(2024, 1, 1),
    )
    issues = validate_symbol_row(row)
    assert any(i.code == "SYMBOL_DELISTED_BEFORE_LISTED" for i in issues)


def test_validate_daily_price_row_valid() -> None:
    row = RawDailyPriceRow(
        symbol="005930", date=date(2024, 1, 2),
        open=100, high=110, low=95, close=105, volume=1000,
        adj_open=100, adj_high=110, adj_low=95, adj_close=105, adj_volume=1000,
        market_cap=1_000_000_000,
    )
    assert validate_daily_price_row(row) == []


def test_validate_daily_price_row_close_zero_is_hard() -> None:
    row = RawDailyPriceRow(
        symbol="005930", date=date(2024, 1, 2),
        open=100, high=110, low=95, close=0, volume=1000,
        adj_open=100, adj_high=110, adj_low=95, adj_close=105, adj_volume=1000,
    )
    issues = validate_daily_price_row(row)
    assert any(
        i.code == "PRICE_CLOSE_NULL_OR_NONPOSITIVE" and i.severity == "hard_fail"
        for i in issues
    )


def test_validate_daily_price_row_high_lt_low_is_hard() -> None:
    row = RawDailyPriceRow(
        symbol="005930", date=date(2024, 1, 2),
        open=100, high=80, low=95, close=85, volume=1000,
        adj_open=100, adj_high=80, adj_low=95, adj_close=85, adj_volume=1000,
    )
    issues = validate_daily_price_row(row)
    assert any(
        i.code == "OHLC_INCONSISTENT_HIGH_LT_LOW" and i.severity == "hard_fail"
        for i in issues
    )


def test_validate_daily_price_row_market_cap_missing_is_soft() -> None:
    row = RawDailyPriceRow(
        symbol="005930", date=date(2024, 1, 2),
        open=100, high=110, low=95, close=105, volume=1000,
        adj_open=100, adj_high=110, adj_low=95, adj_close=105, adj_volume=1000,
        market_cap=None,
    )
    issues = validate_daily_price_row(row)
    assert any(
        i.code == "MARKET_CAP_MISSING" and i.severity == "soft_fail" for i in issues
    )
    # hard 없음
    assert not any(i.severity == "hard_fail" for i in issues)


def test_validate_daily_price_row_volume_zero_is_soft() -> None:
    row = RawDailyPriceRow(
        symbol="005930", date=date(2024, 1, 2),
        open=100, high=110, low=95, close=105, volume=0,
        adj_open=100, adj_high=110, adj_low=95, adj_close=105, adj_volume=0,
        market_cap=1_000_000,
    )
    issues = validate_daily_price_row(row)
    assert any(i.code == "VOLUME_ZERO" and i.severity == "soft_fail" for i in issues)


def test_validate_daily_price_row_high_eq_low_is_soft() -> None:
    """한가 — 정상 (SOFT)."""
    row = RawDailyPriceRow(
        symbol="005930", date=date(2024, 1, 2),
        open=100, high=100, low=100, close=100, volume=1,
        adj_open=100, adj_high=100, adj_low=100, adj_close=100, adj_volume=1,
        market_cap=1_000_000,
    )
    issues = validate_daily_price_row(row)
    assert any(i.code == "HIGH_EQ_LOW" and i.severity == "soft_fail" for i in issues)


def test_validate_daily_prices_data_aggregates_and_sorts() -> None:
    rows = (
        RawDailyPriceRow(
            symbol="005930", date=date(2024, 1, 2),
            open=100, high=110, low=95, close=105, volume=1000,
            adj_open=100, adj_high=110, adj_low=95, adj_close=105, adj_volume=1000,
            market_cap=None,  # SOFT
        ),
        RawDailyPriceRow(
            symbol="005930", date=date(2024, 1, 3),
            open=100, high=110, low=95, close=0, volume=1000,  # HARD: close=0
            adj_open=100, adj_high=110, adj_low=95, adj_close=105, adj_volume=1000,
            market_cap=1_000_000,
        ),
    )
    data = RawDailyPricesData(
        rows=rows, start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        source="test",
    )
    vr = validate_daily_prices_data(data, raise_on_hard_fail=False)
    assert isinstance(vr, ValidationResult)
    assert vr.passed is False
    assert vr.hard_fail_count >= 1
    assert vr.soft_fail_count >= 1
    # issues가 (code ASC, severity ASC) 정렬됐는지 확인
    sorted_codes = sorted([(i.code, i.severity) for i in vr.issues])
    assert [(i.code, i.severity) for i in vr.issues] == sorted_codes


def test_validate_daily_prices_data_raises_on_hard() -> None:
    rows = (
        RawDailyPriceRow(
            symbol="005930", date=date(2024, 1, 2),
            open=100, high=110, low=95, close=-1, volume=1000,
            adj_open=100, adj_high=110, adj_low=95, adj_close=105, adj_volume=1000,
        ),
    )
    data = RawDailyPricesData(
        rows=rows, start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        source="test",
    )
    with pytest.raises(DataValidationError):
        validate_daily_prices_data(data, raise_on_hard_fail=True)


def test_validate_symbols_data_passes_on_clean_input() -> None:
    rows = (
        RawSymbolRow(
            symbol="000020", name="동화약품", market="KOSPI",
            listing_date=date(1976, 3, 1),
        ),
        RawSymbolRow(
            symbol="005930", name="삼성전자", market="KOSPI",
            listing_date=date(1975, 6, 11),
        ),
    )
    data = RawSymbolsData(rows=rows, as_of_date=date(2024, 1, 1), source="test")
    vr = validate_symbols_data(data)
    assert vr.passed is True
    assert vr.issues == ()


def test_validate_calendar_data_empty_is_hard_fail() -> None:
    data = RawCalendarData(
        rows=(),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        market="KOSPI",
        source="test",
    )
    vr = validate_calendar_data(data)
    assert vr.passed is False
    assert any(i.code == "CALENDAR_EMPTY" for i in vr.issues)


# ---------------------------------------------------------------------------
# I) 결정론 — 같은 입력 같은 출력 반복 검증
# ---------------------------------------------------------------------------


def test_collect_daily_prices_is_deterministic_across_calls() -> None:
    """동일 mock 데이터로 두 번 호출 시 결과가 정확히 같음 (필드/순서)."""
    dates = [date(2024, 1, 2), date(2024, 1, 3)]

    def make_collector() -> PykrxCollector:
        c = PykrxCollector(backoff=(), sleep_fn=lambda _s: None)
        c._fetch_ohlcv = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                _make_ohlcv_df(dates),
                _make_ohlcv_df(dates),
                _make_ohlcv_df(dates),
                _make_ohlcv_df(dates),
            ]
        )
        c._fetch_market_cap = MagicMock(  # type: ignore[method-assign]
            return_value=_make_market_cap_df(dates)
        )
        return c

    r1 = make_collector().collect_daily_prices(
        ["005930", "035720"], date(2024, 1, 1), date(2024, 1, 31)
    )
    r2 = make_collector().collect_daily_prices(
        ["005930", "035720"], date(2024, 1, 1), date(2024, 1, 31)
    )
    # tuple 비교 — 순서 + 필드 모두 같아야 함
    assert r1.rows == r2.rows
    assert r1.start_date == r2.start_date
    assert r1.end_date == r2.end_date
