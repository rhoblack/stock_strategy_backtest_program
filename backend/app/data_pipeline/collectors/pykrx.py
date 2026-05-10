"""PykrxCollector — pykrx 라이브러리를 통한 KRX 시장데이터 수집 (14번 §4.1 / §6).

본 모듈은 024 `BaseCollector` ABC를 구현해 실제 외부 데이터 소스(pykrx)에서
종목 마스터 / 일봉 / 거래일 캘린더를 수집한다.

설계 결정 (인계 정보 — 026 BaseProcessor가 활용):

    1. **외부 fetch 격리** (테스트 용이성)
        - pykrx 호출은 모두 `_fetch_*` private 메서드로 캡슐화
        - 단위 테스트는 `_fetch_*`를 mock으로 교체해 외부 호출 없이 검증
        - 직접 pykrx 호출하는 통합 테스트는 `@pytest.mark.network` 마커로 분리
            (pyproject.toml markers 등록 필요 — 본 step에서 1줄 추가)

    2. **재시도 적용** (14번 §6.3)
        - `_fetch_*` 메서드 자체에는 데코레이터를 직접 붙이지 않음
        - 대신 `collect_*` 진입점에서 `retry_call(self._fetch_xxx, ...)`로 호출
        - 이유:
            (a) 데코레이터를 메서드에 붙이면 mock 패치가 까다로워짐 (decorated wrapper를 패치해야 함)
            (b) 호출자가 retry 정책을 동적으로 선택하기 쉬움 (테스트는 backoff=()로 무재시도)
            (c) 026 이후 별도 retry 정책이 필요한 collector도 같은 패턴 재사용

    3. **검증 적용** (14번 §7)
        - `collect_*` 진입점에서 `validate_xxx_data(result, raise_on_hard_fail=...)` 호출
        - 기본은 `raise_on_hard_fail=True` — collector 출력은 다음 단계로 흐르기 전 hard 차단
        - 호출자가 raw 데이터를 받아 별도 검증하고 싶으면 `validate=False`로 끄고
          외부에서 `validate_xxx_data(result)` 직접 호출 가능

    4. **결정론** (CLAUDE.md #8)
        - 출력은 BaseCollector 헬퍼(`_to_sorted_*_tuple`)로 정렬 강제
        - pykrx 응답 dict 순회 의존 금지 → 항상 정렬 키 기반

    5. **lazy import** (의존성 격리)
        - `import pykrx`는 `_fetch_*` 메서드 내부에서만 수행
        - 본 모듈 import만으로는 pykrx 미설치여도 무관 (테스트 환경 친화)
        - 운용 환경에서는 `pip install pykrx` 별도 필요

    6. **026 인계**:
        - `RawDailyPricesData`(adj_* 컬럼이 이미 채워져 있음)를 받아 026 `AdjustedPriceProcessor`가
          corporate_actions 기반으로 adj_* 재계산을 수행할 예정.
        - 본 collector는 pykrx의 `adjusted=False/True` 옵션으로 1차 adj_*를 채우지만,
          정밀한 재계산은 026이 담당. 본 collector의 adj_*는 폴백/초기 추정값.

본 모듈은 외부 fetch가 발생할 수 있으나(`_fetch_*` 호출 시), 메서드 단위로 mock 가능.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import TYPE_CHECKING, Any

from app.data_pipeline.collectors.base import (
    BaseCollector,
    RawCalendarData,
    RawCalendarRow,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawSymbolRow,
    RawSymbolsData,
)
from app.data_pipeline.collectors.retry import (
    DEFAULT_BACKOFF_SECONDS,
    FatalCollectorError,
    retry_call,
)
from app.data_pipeline.collectors.validators import (
    validate_calendar_data,
    validate_daily_prices_data,
    validate_symbols_data,
)
from app.data_pipeline.processors.base import ValidationResult

if TYPE_CHECKING:
    from collections.abc import Iterable

# pykrx의 날짜 포맷 (KRX 표준)
_PYKRX_DATE_FMT = "%Y%m%d"

# 본 collector가 출력 source 필드에 사용할 식별자
SOURCE_NAME = "pykrx"

# pykrx에서 받아오는 시장 식별자 매핑 (KOSPI/KOSDAQ/KONEX는 그대로, ALL은 합집합)
_VALID_MARKETS: tuple[str, ...] = ("KOSPI", "KOSDAQ", "KONEX")


def _format_date(d: date_type) -> str:
    """`date` → "YYYYMMDD" 문자열 (pykrx 입력 포맷)."""
    return d.strftime(_PYKRX_DATE_FMT)


def _parse_date(s: str | date_type) -> date_type:
    """pykrx index가 문자열 또는 datetime/date인 경우 모두 지원."""
    if isinstance(s, date_type):
        return s
    # pandas Timestamp / datetime은 isinstance(date_type)으로 잡힘 (datetime이 date의 subclass)
    return date_type(int(s[0:4]), int(s[4:6]), int(s[6:8]))


class PykrxCollector(BaseCollector):
    """pykrx 라이브러리를 사용한 KRX 시장데이터 collector (14번 §4.1).

    구현 메서드 (BaseCollector ABC):
        - `collect_symbols(as_of_date) -> RawSymbolsData`
        - `collect_daily_prices(symbols, start_date, end_date) -> RawDailyPricesData`
        - `collect_trading_calendar(start_date, end_date, market) -> RawCalendarData`

    Args:
        name: collector 식별자 (기본 "pykrx").
        backoff: 14번 §6.3 재시도 시퀀스. 기본 `(1.0, 5.0, 30.0)`.
        sleep_fn: 재시도 시 사용할 sleep 함수 (테스트 mock용).
        validate: True면 collect_* 진입점에서 자동 검증 수행. 기본 True.
        markets: collect_symbols에서 합집합으로 수집할 시장 리스트. 기본 ("KOSPI", "KOSDAQ").

    사용 예:

        collector = PykrxCollector()
        symbols = collector.collect_symbols(date(2024, 1, 2))
        prices = collector.collect_daily_prices(["005930"], date(2024, 1, 1), date(2024, 1, 31))

    테스트 예 (외부 호출 없음):

        collector = PykrxCollector(backoff=())
        collector._fetch_ohlcv = MagicMock(return_value=fake_df)
        collector._fetch_market_cap = MagicMock(return_value=fake_cap_df)
        result = collector.collect_daily_prices(...)
    """

    def __init__(
        self,
        name: str = SOURCE_NAME,
        *,
        backoff: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
        sleep_fn: Any = None,
        validate: bool = True,
        markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    ) -> None:
        super().__init__(name)
        self._backoff = backoff
        # sleep_fn=None이면 retry_call 기본(time.sleep) 사용
        self._sleep_fn = sleep_fn
        self._validate = validate
        # 시장 검증
        for m in markets:
            if m not in _VALID_MARKETS:
                raise FatalCollectorError(
                    f"지원하지 않는 시장: {m!r} (KOSPI/KOSDAQ/KONEX 중 선택)"
                )
        self._markets = markets

    # ------------------------------------------------------------------
    # BaseCollector 구현
    # ------------------------------------------------------------------

    def collect_symbols(self, as_of_date: date_type) -> RawSymbolsData:
        """종목 마스터 수집 (14번 §3.1).

        14.9 look-ahead 차단: as_of_date 시점에 살아 있는 종목 + 그 이전 폐지 종목.
        본 step에서는 폐지 종목 합산은 미지원 (pykrx의 폐지 종목 API는 보조 — 027 이후 보강 가능).

        Args:
            as_of_date: 기준 일자.

        Returns:
            RawSymbolsData — (symbol ASC) 정렬.
        """
        rows: list[RawSymbolRow] = []
        warnings: list[str] = []
        as_of_str = _format_date(as_of_date)

        # 1) 시장별 ticker 목록 수집
        for market in self._markets:
            tickers = self._retry(self._fetch_ticker_list, as_of_str, market)
            for ticker in tickers:
                # 2) 종목명
                try:
                    name = self._retry(self._fetch_ticker_name, ticker)
                except FatalCollectorError as exc:  # 일부 종목 메타 누락은 SOFT
                    warnings.append(f"종목명 조회 실패: {ticker} ({exc})")
                    name = ""
                rows.append(
                    RawSymbolRow(
                        symbol=str(ticker),
                        name=str(name or ""),
                        market=market,
                        # listing_date는 pykrx 단일 호출로 얻기 어려움 → 별도 처리 필요.
                        # 본 step에서는 as_of_date를 listing_date 폴백으로 사용하되 SOFT 경고 누적.
                        # 정밀한 listing_date는 027 이후 BaseSymbolMaster 처리에서 보강.
                        listing_date=as_of_date,
                        # delisting_date 등 플래그는 본 collector 미지원 (027 이후)
                    )
                )

        result = RawSymbolsData(
            rows=BaseCollector._to_sorted_symbol_tuple(rows),
            as_of_date=as_of_date,
            source=self.name,
            warnings=tuple(warnings),
        )
        if self._validate:
            self._validate_or_raise(validate_symbols_data, result)
        return result

    def collect_daily_prices(
        self,
        symbols: tuple[str, ...] | list[str],
        start_date: date_type,
        end_date: date_type,
    ) -> RawDailyPricesData:
        """일봉 수집 (14번 §3.2 / §6.1).

        결손 봉(공휴일, 거래정지 등)은 row를 만들지 않는다 (14.10 forward-fill 금지).

        Args:
            symbols: 6자리 KRX 코드 리스트.
            start_date / end_date: 포함 범위.

        Returns:
            RawDailyPricesData — (symbol ASC, date ASC) 정렬.
        """
        if start_date > end_date:
            raise FatalCollectorError(
                f"start_date > end_date: {start_date.isoformat()} > {end_date.isoformat()}"
            )

        rows: list[RawDailyPriceRow] = []
        warnings: list[str] = []
        start_str = _format_date(start_date)
        end_str = _format_date(end_date)

        for symbol in symbols:
            # 1) OHLCV (수정 안 한 raw)
            df_raw = self._retry(
                self._fetch_ohlcv, start_str, end_str, str(symbol), False
            )
            # 2) OHLCV 수정주가 버전 (pykrx adjusted=True)
            df_adj = self._retry(
                self._fetch_ohlcv, start_str, end_str, str(symbol), True
            )
            # 3) 시가총액 시계열 (선택 — 결손은 SOFT)
            try:
                df_cap = self._retry(self._fetch_market_cap, start_str, end_str, str(symbol))
            except FatalCollectorError as exc:
                warnings.append(f"시가총액 조회 실패: {symbol} ({exc})")
                df_cap = None

            rows.extend(
                self._merge_price_frames(
                    symbol=str(symbol),
                    df_raw=df_raw,
                    df_adj=df_adj,
                    df_cap=df_cap,
                    warnings=warnings,
                )
            )

        result = RawDailyPricesData(
            rows=BaseCollector._to_sorted_price_tuple(rows),
            start_date=start_date,
            end_date=end_date,
            source=self.name,
            warnings=tuple(warnings),
        )
        if self._validate:
            self._validate_or_raise(validate_daily_prices_data, result)
        return result

    def collect_trading_calendar(
        self,
        start_date: date_type,
        end_date: date_type,
        market: str,
    ) -> RawCalendarData:
        """거래일 캘린더 수집 (14번 §3.3 / §14).

        Args:
            start_date / end_date: 포함 범위.
            market: KOSPI / KOSDAQ / KONEX.

        Returns:
            RawCalendarData — (market ASC, date ASC) 정렬.
        """
        if market not in _VALID_MARKETS:
            raise FatalCollectorError(
                f"지원하지 않는 시장: {market!r} (KOSPI/KOSDAQ/KONEX)"
            )
        if start_date > end_date:
            raise FatalCollectorError(
                f"start_date > end_date: {start_date.isoformat()} > {end_date.isoformat()}"
            )

        start_str = _format_date(start_date)
        end_str = _format_date(end_date)
        # pykrx가 반환하는 영업일 리스트
        business_days = self._retry(self._fetch_business_days, start_str, end_str, market)

        rows: list[RawCalendarRow] = []
        for d in business_days:
            parsed = _parse_date(d) if not isinstance(d, date_type) else d
            rows.append(
                RawCalendarRow(
                    date=parsed,
                    market=market,
                    is_trading_day=True,
                    holiday_name=None,
                )
            )

        result = RawCalendarData(
            rows=BaseCollector._to_sorted_calendar_tuple(rows),
            start_date=start_date,
            end_date=end_date,
            market=market,
            source=self.name,
            warnings=(),
        )
        if self._validate:
            self._validate_or_raise(validate_calendar_data, result)
        return result

    # ------------------------------------------------------------------
    # 내부 helper — retry / validate
    # ------------------------------------------------------------------

    def _retry(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """`retry_call` wrapper — 본 인스턴스의 backoff/sleep_fn으로 실행."""
        if self._sleep_fn is not None:
            return retry_call(
                fn, *args, backoff=self._backoff, sleep_fn=self._sleep_fn, **kwargs
            )
        return retry_call(fn, *args, backoff=self._backoff, **kwargs)

    @staticmethod
    def _validate_or_raise(
        validator: Any,
        data: Any,
    ) -> ValidationResult:
        """검증 함수를 raise_on_hard_fail=True로 호출."""
        return validator(data, raise_on_hard_fail=True)

    # ------------------------------------------------------------------
    # 외부 fetch — pykrx 호출 (테스트에서 mock)
    #
    # 이 메서드들은 모두 lazy import + pykrx 호출만 수행.
    # 외부 5xx/네트워크 오류는 Exception → RetryableCollectorError로 감싸야 함.
    # 현재 본 step에서는 pykrx import 자체가 실패하면 FatalCollectorError로 감싸고,
    # 일반 Exception은 RetryableCollectorError로 분류 (pykrx의 예외 타입이 광범위하므로 보수적).
    # ------------------------------------------------------------------

    def _fetch_ticker_list(self, as_of_str: str, market: str) -> Iterable[str]:
        """pykrx.stock.get_market_ticker_list 래퍼."""
        stock = self._import_stock()
        try:
            return stock.get_market_ticker_list(as_of_str, market=market)
        except Exception as exc:
            raise self._classify_exception(exc, "get_market_ticker_list") from exc

    def _fetch_ticker_name(self, ticker: str) -> str:
        """pykrx.stock.get_market_ticker_name 래퍼."""
        stock = self._import_stock()
        try:
            return stock.get_market_ticker_name(ticker)
        except Exception as exc:
            raise self._classify_exception(exc, "get_market_ticker_name") from exc

    def _fetch_ohlcv(
        self,
        start_str: str,
        end_str: str,
        symbol: str,
        adjusted: bool,
    ) -> Any:
        """pykrx.stock.get_market_ohlcv_by_date 래퍼.

        Args:
            adjusted: True면 수정주가, False면 원시 가격.
        """
        stock = self._import_stock()
        try:
            return stock.get_market_ohlcv_by_date(
                start_str, end_str, symbol, adjusted=adjusted
            )
        except Exception as exc:
            raise self._classify_exception(exc, "get_market_ohlcv_by_date") from exc

    def _fetch_market_cap(
        self,
        start_str: str,
        end_str: str,
        symbol: str,
    ) -> Any:
        """pykrx.stock.get_market_cap_by_date 래퍼."""
        stock = self._import_stock()
        try:
            return stock.get_market_cap_by_date(start_str, end_str, symbol)
        except Exception as exc:
            raise self._classify_exception(exc, "get_market_cap_by_date") from exc

    def _fetch_business_days(
        self,
        start_str: str,
        end_str: str,
        market: str,
    ) -> Iterable[date_type | str]:
        """pykrx.stock.get_previous_business_days 또는 동등 함수 래퍼.

        pykrx는 (year=..., month=...) 형태도 지원하지만 본 step에서는 범위 기반.
        get_previous_business_days(fromdate, todate)가 표준 시그니처.
        """
        stock = self._import_stock()
        try:
            # pykrx 0.x 표준: (fromdate, todate)
            return stock.get_previous_business_days(fromdate=start_str, todate=end_str)
        except Exception as exc:
            raise self._classify_exception(exc, "get_previous_business_days") from exc

    @staticmethod
    def _import_stock() -> Any:
        """pykrx.stock 모듈을 lazy import.

        ImportError는 FatalCollectorError로 감싼다 (재시도 무의미).
        """
        try:
            from pykrx import stock  # noqa: PLC0415  # lazy import 의도
        except ImportError as exc:
            raise FatalCollectorError(
                "pykrx 라이브러리가 설치되지 않았습니다. "
                "운용 환경에서는 `pip install pykrx`로 설치하세요."
            ) from exc
        return stock

    @staticmethod
    def _classify_exception(exc: Exception, op_name: str) -> Exception:
        """pykrx 호출 중 발생한 일반 예외를 retry/fatal로 분류.

        pykrx는 예외 타입이 광범위(requests.exceptions.*, KeyError, ValueError 등)하므로
        본 step에서는 보수적으로 모두 RetryableCollectorError로 분류한다.
        구체 분류는 운용 데이터 수집 후 028 이후 정교화.
        """
        # lazy import — retry/fatal 구체 예외
        from app.data_pipeline.collectors.retry import RetryableCollectorError  # noqa: PLC0415

        return RetryableCollectorError(
            f"pykrx.{op_name} 실패: {type(exc).__name__}: {exc}"
        )

    # ------------------------------------------------------------------
    # OHLCV merge 로직 (raw + adjusted + market_cap)
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_price_frames(
        symbol: str,
        df_raw: Any,
        df_adj: Any,
        df_cap: Any,
        warnings: list[str],
    ) -> list[RawDailyPriceRow]:
        """pykrx OHLCV 두 종(원시/수정) + 시가총액을 RawDailyPriceRow 리스트로 병합.

        pykrx 반환 DataFrame 컬럼 (한국어):
            - 시가, 고가, 저가, 종가, 거래량, 거래대금, 등락률
        시가총액 DataFrame 컬럼:
            - 시가총액, 거래량, 거래대금, 상장주식수

        결손 봉(공휴일/거래정지)은 row 미생성 (14.10 forward-fill 금지).
        """
        if df_raw is None or len(df_raw) == 0:
            warnings.append(f"OHLCV(raw) 결과 없음: {symbol}")
            return []
        if df_adj is None or len(df_adj) == 0:
            # adjusted 결과가 없으면 raw로 동일 사용 (폴백)
            df_adj = df_raw
            warnings.append(f"OHLCV(adjusted) 결과 없음, raw로 폴백: {symbol}")

        rows: list[RawDailyPriceRow] = []
        # df_raw의 index를 기준으로 순회 (모든 행은 거래일)
        for idx in df_raw.index:
            try:
                raw_row = df_raw.loc[idx]
                # adj_row는 동일 index가 없을 수 있음 (드물지만 안전망)
                adj_row = df_adj.loc[idx] if idx in df_adj.index else raw_row
                cap_value: float | None = None
                if df_cap is not None and idx in df_cap.index:
                    cap_value = float(df_cap.loc[idx]["시가총액"])

                date_val = _parse_date(idx) if not isinstance(idx, date_type) else idx

                rows.append(
                    RawDailyPriceRow(
                        symbol=symbol,
                        date=date_val,
                        open=float(raw_row["시가"]),
                        high=float(raw_row["고가"]),
                        low=float(raw_row["저가"]),
                        close=float(raw_row["종가"]),
                        volume=float(raw_row["거래량"]),
                        adj_open=float(adj_row["시가"]),
                        adj_high=float(adj_row["고가"]),
                        adj_low=float(adj_row["저가"]),
                        adj_close=float(adj_row["종가"]),
                        adj_volume=float(adj_row["거래량"]),
                        market_cap=cap_value,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:  # 개별 row 파싱 실패는 SOFT
                warnings.append(
                    f"row 파싱 실패: symbol={symbol} idx={idx} ({type(exc).__name__}: {exc})"
                )
                continue

        return rows


__all__ = [
    "PykrxCollector",
    "SOURCE_NAME",
]
