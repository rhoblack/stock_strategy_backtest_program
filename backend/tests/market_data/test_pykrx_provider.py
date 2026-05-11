"""PykrxProvider 검증.

정책 매핑:
    - 13.7  (수정주가): get_price_df 반환 df에 adj_open/adj_high/adj_low/adj_close/adj_volume 포함
    - 14.10 (결손 정책): 결손 봉 forward-fill 금지 — pykrx 결과 없으면 빈 DataFrame
    - 14.9  (look-ahead 차단): get_price_df의 start/end 인수로 범위 제한
    - CLAUDE.md #8 (결정론): 반환 DataFrame은 date ASC 정렬
    - 06번 §5 (Provider 인터페이스): PykrxProvider / LocalCsvProvider 호환성

외부 fetch: 0건. 모든 pykrx 호출은 unittest.mock.patch로 대체.
"""

from __future__ import annotations

import sys
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.market_data.local_csv import LocalCsvProvider
from app.market_data.provider import BaseProvider, IngestResult
from app.market_data.pykrx_provider import (
    PYKRX_PROVIDER_COLUMNS,
    PykrxImportError,
    PykrxProvider,
)

# ---------------------------------------------------------------------------
# 합성 pykrx 응답 빌더
# ---------------------------------------------------------------------------


def _make_ohlcv_df(
    dates: list[str],
    *,
    open_: float = 10000.0,
    high: float = 11000.0,
    low: float = 9500.0,
    close: float = 10500.0,
    volume: float = 50000.0,
) -> pd.DataFrame:
    """pykrx 스타일 한국어 컬럼 DataFrame 생성."""
    return pd.DataFrame(
        {
            "시가": [open_] * len(dates),
            "고가": [high] * len(dates),
            "저가": [low] * len(dates),
            "종가": [close] * len(dates),
            "거래량": [volume] * len(dates),
            "거래대금": [close * volume] * len(dates),
            "등락률": [0.0] * len(dates),
        },
        index=dates,
    )


def _make_cap_df(
    dates: list[str],
    *,
    cap: float = 1_000_000_000_000.0,
) -> pd.DataFrame:
    """pykrx 시가총액 스타일 DataFrame 생성."""
    return pd.DataFrame(
        {
            "시가총액": [cap] * len(dates),
            "거래량": [50000] * len(dates),
            "거래대금": [500_000_000.0] * len(dates),
            "상장주식수": [10_000_000] * len(dates),
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# 공통 fixture: PykrxCollector._fetch_* mock
# ---------------------------------------------------------------------------


SAMPLE_DATES = ["20240102", "20240103", "20240104"]
SAMPLE_SYMBOL = "005930"


def _patch_collector_fetches(
    mock_ohlcv_raw: pd.DataFrame | None = None,
    mock_ohlcv_adj: pd.DataFrame | None = None,
    mock_cap: pd.DataFrame | None = None,
    ticker_list: list[str] | None = None,
    business_days: list[str] | None = None,
) -> dict[str, Any]:
    """PykrxCollector의 _fetch_* 메서드를 mock으로 교체하는 patch 딕셔너리 반환."""
    ohlcv_raw = mock_ohlcv_raw if mock_ohlcv_raw is not None else _make_ohlcv_df(SAMPLE_DATES)
    ohlcv_adj = mock_ohlcv_adj if mock_ohlcv_adj is not None else _make_ohlcv_df(
        SAMPLE_DATES, close=10800.0
    )
    cap = mock_cap if mock_cap is not None else _make_cap_df(SAMPLE_DATES)

    return {
        "_fetch_ohlcv": MagicMock(side_effect=lambda s, e, sym, adj: ohlcv_adj if adj else ohlcv_raw),
        "_fetch_market_cap": MagicMock(return_value=cap),
        "_fetch_ticker_list": MagicMock(return_value=ticker_list or [SAMPLE_SYMBOL]),
        "_fetch_ticker_name": MagicMock(return_value="삼성전자"),
        "_fetch_business_days": MagicMock(return_value=business_days or SAMPLE_DATES),
    }


# ---------------------------------------------------------------------------
# test_get_price_df_returns_correct_columns (13.7 수정주가)
# ---------------------------------------------------------------------------


def test_get_price_df_returns_correct_columns():
    """13.7 수정주가: adj_open/adj_high/adj_low/adj_close/adj_volume 컬럼 포함."""
    provider = PykrxProvider(backoff=(), validate=False)
    mocks = _patch_collector_fetches()

    with (
        patch.multiple("app.data_pipeline.collectors.pykrx.PykrxCollector", **mocks),
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
    ):
        df = provider.get_price_df(
            SAMPLE_SYMBOL,
            date(2024, 1, 2),
            date(2024, 1, 4),
        )

    assert not df.empty, "거래일 데이터가 있어야 함"

    # 13.7: adj_* 컬럼 전체 존재
    for col in ("adj_open", "adj_high", "adj_low", "adj_close", "adj_volume"):
        assert col in df.columns, f"누락 컬럼: {col}"

    # 원 가격 컬럼도 존재
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df.columns, f"누락 컬럼: {col}"

    # PYKRX_PROVIDER_COLUMNS 순서 정확히 일치
    assert list(df.columns) == list(PYKRX_PROVIDER_COLUMNS)


# ---------------------------------------------------------------------------
# test_get_price_df_date_range_filter (14.9 look-ahead 차단)
# ---------------------------------------------------------------------------


def test_get_price_df_date_range_filter():
    """start/end 날짜 범위 필터링 — PykrxCollector에 정확한 날짜 전달 확인."""
    provider = PykrxProvider(backoff=(), validate=False)
    mocks = _patch_collector_fetches(
        mock_ohlcv_raw=_make_ohlcv_df(["20240102"]),
        mock_ohlcv_adj=_make_ohlcv_df(["20240102"], close=10800.0),
        mock_cap=_make_cap_df(["20240102"]),
    )

    with (
        patch.multiple("app.data_pipeline.collectors.pykrx.PykrxCollector", **mocks),
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
    ):
        df = provider.get_price_df(
            SAMPLE_SYMBOL,
            date(2024, 1, 2),
            date(2024, 1, 2),
        )

    assert len(df) == 1
    assert df.iloc[0]["date"] == date(2024, 1, 2)


def test_get_price_df_start_gt_end_raises():
    """start > end이면 ValueError 발생 (14.9 look-ahead 차단)."""
    provider = PykrxProvider(backoff=(), validate=False)

    with (
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
        pytest.raises(ValueError, match="start > end"),
    ):
        provider.get_price_df(
            SAMPLE_SYMBOL,
            date(2024, 1, 10),
            date(2024, 1, 5),
        )


def test_get_price_df_empty_when_no_data():
    """pykrx 결과 없으면 빈 DataFrame 반환 — forward-fill 금지 (14.10)."""
    provider = PykrxProvider(backoff=(), validate=False)
    mocks = _patch_collector_fetches(
        mock_ohlcv_raw=pd.DataFrame(),  # 빈 DataFrame
        mock_ohlcv_adj=pd.DataFrame(),
        mock_cap=None,
    )

    with (
        patch.multiple("app.data_pipeline.collectors.pykrx.PykrxCollector", **mocks),
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
    ):
        df = provider.get_price_df(
            SAMPLE_SYMBOL,
            date(2024, 1, 2),
            date(2024, 1, 4),
        )

    assert df.empty
    # 빈 DataFrame도 컬럼 명세는 유지
    assert list(df.columns) == list(PYKRX_PROVIDER_COLUMNS)


# ---------------------------------------------------------------------------
# test_get_price_df_date_asc_order (CLAUDE.md #8 결정론)
# ---------------------------------------------------------------------------


def test_get_price_df_date_asc_order():
    """CLAUDE.md #8 결정론: 반환 DataFrame은 date ASC 정렬."""
    # pykrx가 역순으로 반환하는 케이스 시뮬레이션
    reversed_dates = ["20240104", "20240103", "20240102"]
    provider = PykrxProvider(backoff=(), validate=False)
    mocks = _patch_collector_fetches(
        mock_ohlcv_raw=_make_ohlcv_df(reversed_dates),
        mock_ohlcv_adj=_make_ohlcv_df(reversed_dates, close=10800.0),
        mock_cap=_make_cap_df(reversed_dates),
    )

    with (
        patch.multiple("app.data_pipeline.collectors.pykrx.PykrxCollector", **mocks),
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
    ):
        df = provider.get_price_df(
            SAMPLE_SYMBOL,
            date(2024, 1, 2),
            date(2024, 1, 4),
        )

    dates = list(df["date"])
    assert dates == sorted(dates), "date ASC 정렬이어야 함"


# ---------------------------------------------------------------------------
# test_get_symbols_returns_list (06번 §4)
# ---------------------------------------------------------------------------


def test_get_symbols_returns_list():
    """get_symbols: 비어있지 않은 정렬된 종목 코드 리스트 반환."""
    provider = PykrxProvider(backoff=(), validate=False)
    mocks = _patch_collector_fetches(
        ticker_list=["005930", "000660", "035720"],
    )

    with (
        patch.multiple("app.data_pipeline.collectors.pykrx.PykrxCollector", **mocks),
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
    ):
        symbols = provider.get_symbols(market="KOSPI")

    assert isinstance(symbols, list)
    assert len(symbols) > 0
    # 결정론: symbol ASC 정렬
    assert symbols == sorted(symbols)
    assert "005930" in symbols


# ---------------------------------------------------------------------------
# test_get_trading_calendar (06번 §4)
# ---------------------------------------------------------------------------


def test_get_trading_calendar_returns_sorted_dates():
    """get_trading_calendar: 거래일 list[date] 반환, date ASC 정렬."""
    provider = PykrxProvider(backoff=(), validate=False)
    mocks = _patch_collector_fetches(
        business_days=["20240104", "20240103", "20240102"],  # 역순 입력
    )

    with (
        patch.multiple("app.data_pipeline.collectors.pykrx.PykrxCollector", **mocks),
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
    ):
        cal = provider.get_trading_calendar(date(2024, 1, 2), date(2024, 1, 4))

    assert cal == sorted(cal), "date ASC 정렬이어야 함"
    assert all(isinstance(d, date) for d in cal)
    assert date(2024, 1, 2) in cal
    assert date(2024, 1, 3) in cal
    assert date(2024, 1, 4) in cal


# ---------------------------------------------------------------------------
# test_lazy_import_error (pykrx 미설치 시 명확한 에러)
# ---------------------------------------------------------------------------


def _import_raise_for_pykrx(name: str, *args: Any, **kwargs: Any) -> Any:
    """pykrx만 ImportError, 나머지는 정상 import."""
    if name == "pykrx":
        raise ImportError("No module named 'pykrx'")
    return __import__(name, *args, **kwargs)


def test_lazy_import_error_on_get_price_df():
    """pykrx 미설치 시 PykrxImportError (명확한 메시지) 발생."""
    provider = PykrxProvider(backoff=(), validate=False)

    # sys.modules에서 pykrx를 제거해 ImportError 시뮬레이션
    original = sys.modules.pop("pykrx", None)
    try:
        with (
            patch("builtins.__import__", side_effect=_import_raise_for_pykrx),
            pytest.raises(PykrxImportError, match="pip install pykrx"),
        ):
            provider.get_price_df(SAMPLE_SYMBOL, date(2024, 1, 2), date(2024, 1, 4))
    finally:
        if original is not None:
            sys.modules["pykrx"] = original


def test_lazy_import_error_on_get_symbols():
    """get_symbols에서도 pykrx 미설치 시 PykrxImportError."""
    # _ensure_pykrx_available을 직접 호출해 검증
    # (get_symbols 첫 줄에서 _ensure_pykrx_available을 호출하므로)
    with (
        patch("builtins.__import__", side_effect=_import_raise_for_pykrx),
        pytest.raises(PykrxImportError, match="pip install pykrx"),
    ):
        PykrxProvider._ensure_pykrx_available()


# ---------------------------------------------------------------------------
# test_interface_compatible_with_local_csv (06번 §5 Provider 호환성)
# ---------------------------------------------------------------------------


def test_both_providers_inherit_base_provider():
    """PykrxProvider와 LocalCsvProvider 모두 BaseProvider 서브클래스인지 확인 (06번 §5)."""
    assert issubclass(PykrxProvider, BaseProvider)
    assert issubclass(LocalCsvProvider, BaseProvider)


def test_both_providers_have_ingest_into():
    """두 Provider 모두 ingest_into 메서드를 가짐 (BaseProvider 인터페이스 호환)."""
    assert callable(getattr(PykrxProvider, "ingest_into", None))
    assert callable(getattr(LocalCsvProvider, "ingest_into", None))


def test_pykrx_provider_ingest_into_returns_ingest_result():
    """ingest_into 반환값이 IngestResult 타입인지 확인."""
    provider = PykrxProvider(backoff=(), validate=False)
    mocks = _patch_collector_fetches()

    with (
        patch.multiple("app.data_pipeline.collectors.pykrx.PykrxCollector", **mocks),
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
        patch("app.market_data.pykrx_provider.repositories") as mock_repo,
    ):
        mock_repo.upsert_symbol.return_value = MagicMock()
        mock_repo.bulk_upsert_daily_prices.return_value = 3
        mock_repo.upsert_trading_day.return_value = MagicMock()
        mock_session = MagicMock()
        result = provider.ingest_into(
            mock_session,
            symbols=[SAMPLE_SYMBOL],
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 4),
        )

    assert isinstance(result, IngestResult)
    assert result.symbols_upserted >= 0
    assert result.daily_prices_upserted >= 0
    assert result.trading_days_upserted >= 0


# ---------------------------------------------------------------------------
# test_get_price_df_adj_close_differs_from_close (13.7 수정주가 실제 분리)
# ---------------------------------------------------------------------------


def test_get_price_df_adj_close_differs_from_close():
    """13.7: adj_close와 close가 다른 값을 가질 수 있음 — 수정주가 컬럼 독립성."""
    raw_close = 10000.0
    adj_close = 9500.0  # 분할/배당 적용 후 값

    provider = PykrxProvider(backoff=(), validate=False)
    mocks = _patch_collector_fetches(
        mock_ohlcv_raw=_make_ohlcv_df(["20240102"], close=raw_close),
        mock_ohlcv_adj=_make_ohlcv_df(["20240102"], close=adj_close),
        mock_cap=_make_cap_df(["20240102"]),
    )

    with (
        patch.multiple("app.data_pipeline.collectors.pykrx.PykrxCollector", **mocks),
        patch.object(PykrxProvider, "_ensure_pykrx_available"),
    ):
        df = provider.get_price_df(
            SAMPLE_SYMBOL,
            date(2024, 1, 2),
            date(2024, 1, 2),
        )

    assert len(df) == 1
    assert df.iloc[0]["close"] == raw_close, "원 종가가 close에 보존되어야 함"
    assert df.iloc[0]["adj_close"] == adj_close, "수정 종가가 adj_close에 반영되어야 함"
    assert df.iloc[0]["close"] != df.iloc[0]["adj_close"], "두 값이 달라야 함"


# ---------------------------------------------------------------------------
# test_pykrx_provider_columns_constant (컬럼 명세 안정성)
# ---------------------------------------------------------------------------


def test_pykrx_provider_columns_constant():
    """PYKRX_PROVIDER_COLUMNS에 필수 컬럼이 모두 포함되어 있는지 확인."""
    required = {
        "date",
        "open", "high", "low", "close", "volume",
        "adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
        "market_cap",
    }
    assert required.issubset(set(PYKRX_PROVIDER_COLUMNS))
