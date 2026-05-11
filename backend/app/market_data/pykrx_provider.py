"""PykrxProvider — pykrx 라이브러리를 이용한 KRX 시장데이터 Provider (06번 §5 / 14번 §4).

역할:
    LocalCsvProvider 대신 실제 KRX API(pykrx)를 통해 데이터를 공급한다.

두 가지 사용 방식:

    A. ingest_into(session, ...) — BaseProvider 패턴 (ETL 파이프라인용)
       내부에서 PykrxCollector.collect_* + repositories.* 를 호출해 DB에 적재.
       BacktestEngine은 이후 PriceLoader(session).load(...)로 조회.

    B. get_price_df / get_symbols / get_trading_calendar — DataFrame 직접 반환 패턴
       DB 없이 백테스트 테스트/탐색 용도로 DataFrame을 즉시 받고 싶을 때.
       LocalCsvProvider와 인터페이스가 호환되지 않으므로 유의 (LocalCsvProvider는
       ingest_into만 제공; 이 메서드들은 PykrxProvider 전용).

설계 결정:
    - pykrx import는 lazy — 본 모듈 import만으로는 pykrx 미설치여도 정상 동작.
      실제 pykrx 호출 시점에 ImportError → PykrxImportError(명확한 메시지) 발생.
    - 내부 로직은 PykrxCollector에 위임 — 중복 구현 금지.
    - 수정주가 정책 (13.7): get_price_df 반환 df에 adj_open/adj_high/adj_low/adj_close/adj_volume 포함.
    - 결손 봉 (14.10): PykrxCollector가 공휴일/거래정지 봉 row를 만들지 않으므로 forward-fill 금지 유지.
    - 결정론 (CLAUDE.md #8): 날짜/종목 정렬은 PykrxCollector 위임 + get_price_df 내부 재정렬.

정책 매핑:
    - 06번 §5: Provider 종류 목록 (PykrxProvider 포함)
    - 06번 §4: MarketDataProvider 인터페이스 (get_symbols / get_daily_prices / ...)
    - 14번 §4.1 / §6: 수집 흐름 / 재시도
    - 13.7: adj_open/adj_high/adj_low/adj_close + close 둘 다 필수
    - 14.10: 결손 봉 forward-fill 금지
    - 13.15 / 14.9: look-ahead 차단 — get_price_df의 start/end 인수로 미래 데이터 배제
    - CLAUDE.md #8: 결정론
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date as date_type
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.data_pipeline.collectors.pykrx import PykrxCollector
from app.market_data import repositories
from app.market_data.provider import BaseProvider, IngestResult

logger = logging.getLogger(__name__)

# get_price_df 반환 DataFrame 컬럼 명세 (외부에 노출).
# BacktestEngine / condition-author가 의존하는 컬럼 목록.
PYKRX_PROVIDER_COLUMNS: tuple[str, ...] = (
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_open",
    "adj_high",
    "adj_low",
    "adj_close",
    "adj_volume",
    "market_cap",
)


class PykrxImportError(RuntimeError):
    """pykrx 라이브러리가 설치되지 않았을 때 발생하는 명확한 예외.

    retry 불가 — 환경 설정 문제이므로 RuntimeError 상속.
    """


class PykrxProvider(BaseProvider):
    """pykrx 라이브러리를 이용해 실시간/과거 시세를 가져오는 Provider.

    PykrxCollector와 달리 본 클래스는 두 레이어를 연결한다:
        1. ingest_into: PykrxCollector → processors → repositories (DB 적재)
        2. get_price_df / get_symbols / get_trading_calendar: DB 없이 DataFrame 직접 반환

    Args:
        name: provider 식별자 (기본 "pykrx").
        backoff: 재시도 시퀀스 (14번 §6.3). 기본 (1.0, 5.0, 30.0).
        sleep_fn: 재시도 sleep 함수 (테스트 mock용).
        validate: PykrxCollector의 자동 검증 여부. 기본 True.
        markets: collect_symbols 대상 시장. 기본 ("KOSPI", "KOSDAQ").

    사용 예 A (DB 적재):
        provider = PykrxProvider()
        result = provider.ingest_into(
            session,
            symbols=["005930"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        session.commit()

    사용 예 B (DataFrame 직접):
        provider = PykrxProvider()
        df = provider.get_price_df("005930", date(2024, 1, 1), date(2024, 1, 31))
        # df 컬럼: PYKRX_PROVIDER_COLUMNS
    """

    def __init__(
        self,
        name: str = "pykrx",
        *,
        backoff: tuple[float, ...] = (1.0, 5.0, 30.0),
        sleep_fn: Any = None,
        validate: bool = True,
        markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    ) -> None:
        super().__init__(name=name)
        self._backoff = backoff
        self._sleep_fn = sleep_fn
        self._validate = validate
        self._markets = markets
        # PykrxCollector 인스턴스 (lazy 생성 — 실제 필요 시점에)
        self._collector: PykrxCollector | None = None

    # ------------------------------------------------------------------
    # BaseProvider 구현
    # ------------------------------------------------------------------

    def ingest_into(
        self,
        session: Session,
        *,
        symbols: Sequence[str] | None = None,
        start_date: date_type | None = None,
        end_date: date_type | None = None,
    ) -> IngestResult:
        """pykrx fetch → DB 적재 단일 진입점.

        Args:
            session: SQLAlchemy Session. commit은 호출자 책임.
            symbols: None이면 collect_symbols(today) 결과로 전체 종목 수집.
            start_date / end_date: None이면 PykrxCollector 기본 범위 (today 하루).

        Returns:
            IngestResult — symbols / daily_prices / trading_days 적재 row 수 + 경고.

        Raises:
            PykrxImportError: pykrx 미설치.
            ValueError / FatalCollectorError: 입력 검증 실패.
        """
        today = date_type.today()

        collector = self._get_collector()
        warnings: list[str] = []

        # 1) 종목 마스터 수집 + 적재
        as_of = end_date or today
        symbol_data = collector.collect_symbols(as_of)
        warnings.extend(symbol_data.warnings)

        symbol_filter: set[str] | None = set(symbols) if symbols is not None else None
        symbol_rows_to_ingest = [
            r for r in symbol_data.rows
            if symbol_filter is None or r.symbol in symbol_filter
        ]
        for row in self._sorted_symbol_rows(
            [
                {
                    "symbol": r.symbol,
                    "name": r.name,
                    "market": r.market,
                    "listing_date": r.listing_date,
                    "sector": r.sector,
                    "delisting_date": r.delisting_date,
                    "is_etf": r.is_etf,
                    "is_etn": r.is_etn,
                    "is_spac": r.is_spac,
                    "is_preferred": r.is_preferred,
                    "is_managed": r.is_managed,
                    "is_halted": r.is_halted,
                }
                for r in symbol_rows_to_ingest
            ]
        ):
            repositories.upsert_symbol(session, row)
        symbols_upserted = len(symbol_rows_to_ingest)

        # 2) 일봉 수집 + 적재 (symbols 목록 결정)
        effective_symbols: list[str]
        if symbols is not None:
            effective_symbols = sorted(symbols)  # 결정론
        else:
            effective_symbols = sorted(r.symbol for r in symbol_data.rows)

        prices_upserted = 0
        if effective_symbols:
            s_date = start_date or today
            e_date = end_date or today
            prices_data = collector.collect_daily_prices(
                symbols=effective_symbols,
                start_date=s_date,
                end_date=e_date,
            )
            warnings.extend(prices_data.warnings)

            price_dicts = self._sorted_price_rows(
                [
                    {
                        "symbol": r.symbol,
                        "date": r.date,
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "volume": r.volume,
                        "adj_open": r.adj_open,
                        "adj_high": r.adj_high,
                        "adj_low": r.adj_low,
                        "adj_close": r.adj_close,
                        "adj_volume": r.adj_volume,
                        "market_cap": r.market_cap,
                    }
                    for r in prices_data.rows
                ]
            )
            if price_dicts:
                prices_upserted = repositories.bulk_upsert_daily_prices(session, price_dicts)

        # 3) 거래일 캘린더 수집 + 적재 (KOSPI 기준)
        s_date_cal = start_date or today
        e_date_cal = end_date or today
        calendar_upserted = 0
        for market in self._markets:
            try:
                cal_data = collector.collect_trading_calendar(
                    start_date=s_date_cal,
                    end_date=e_date_cal,
                    market=market,
                )
                warnings.extend(cal_data.warnings)
                for row in self._sorted_calendar_rows(
                    [
                        {
                            "date": r.date,
                            "market": r.market,
                            "is_trading_day": r.is_trading_day,
                            "holiday_name": r.holiday_name,
                        }
                        for r in cal_data.rows
                    ]
                ):
                    repositories.upsert_trading_day(
                        session,
                        date=row["date"],
                        market=row["market"],
                        is_trading_day=row["is_trading_day"],
                        holiday_name=row.get("holiday_name"),
                    )
                calendar_upserted += len(cal_data.rows)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"거래일 캘린더 수집 실패 ({market}): {exc}")

        if warnings:
            for w in warnings:
                logger.warning("[PykrxProvider] %s", w)

        return IngestResult(
            symbols_upserted=symbols_upserted,
            daily_prices_upserted=prices_upserted,
            trading_days_upserted=calendar_upserted,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # DataFrame 직접 반환 메서드 (DB 없이 pykrx → DataFrame)
    # ------------------------------------------------------------------

    def get_price_df(
        self,
        symbol: str,
        start: date_type,
        end: date_type,
        adjusted: bool = True,
    ) -> pd.DataFrame:
        """단일 종목 일봉을 DataFrame으로 반환 (DB 저장 없음).

        13.7 수정주가 정책: adj_open/adj_high/adj_low/adj_close/adj_volume 컬럼 포함.
        14.10 결손 정책: 거래 없는 봉(공휴일/거래정지)은 row 없음 — forward-fill 금지.
        CLAUDE.md #8 결정론: 반환 DataFrame은 date ASC 정렬.

        Args:
            symbol: KRX 6자리 종목 코드.
            start / end: 조회 범위 (inclusive). look-ahead bias 차단은 호출자 책임.
            adjusted: True이면 adj_* 컬럼을 수정주가로 채움. False이면 raw == adj.
                      PriceLoader / BacktestEngine 연동 시 True 사용 권장 (기본값).

        Returns:
            DataFrame — 컬럼 순서: PYKRX_PROVIDER_COLUMNS.
            데이터 없으면 빈 DataFrame (컬럼 명세는 동일).

        Raises:
            PykrxImportError: pykrx 미설치.
            ValueError: start > end.
        """
        if start > end:
            raise ValueError(
                f"start > end: {start.isoformat()} > {end.isoformat()}"
            )

        collector = self._get_collector()
        raw_data = collector.collect_daily_prices(
            symbols=[symbol],
            start_date=start,
            end_date=end,
        )

        rows = [r for r in raw_data.rows if r.symbol == symbol]

        if not rows:
            return self._empty_price_df()

        records = [
            {
                "date": r.date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                # 13.7: adj_* 컬럼 항상 포함
                "adj_open": r.adj_open,
                "adj_high": r.adj_high,
                "adj_low": r.adj_low,
                "adj_close": r.adj_close,
                "adj_volume": r.adj_volume,
                "market_cap": r.market_cap,
            }
            for r in rows
        ]

        df = pd.DataFrame.from_records(records)
        # 결정론: date ASC
        df = df.sort_values("date").reset_index(drop=True)
        # 컬럼 순서 정규화
        return df[list(PYKRX_PROVIDER_COLUMNS)]

    def get_symbols(self, market: str = "KOSPI") -> list[str]:
        """해당 시장의 상장 종목 코드 목록 반환 (오늘 기준).

        14.9 look-ahead 차단: as_of_date를 오늘로 고정해 미래 데이터 차단.
        결정론: symbol ASC 정렬.

        Args:
            market: "KOSPI" / "KOSDAQ" / "KONEX". 기본 "KOSPI".

        Returns:
            정렬된 종목 코드 문자열 리스트.

        Raises:
            PykrxImportError: pykrx 미설치.
            FatalCollectorError: 지원하지 않는 시장.
        """
        # pykrx 설치 확인 (lazy) — 미설치 시 PykrxImportError
        self._ensure_pykrx_available()
        today = date_type.today()
        # 해당 market만 수집하는 임시 collector 생성
        temp_collector = self._make_collector(markets=(market,))
        symbol_data = temp_collector.collect_symbols(today)
        return sorted(r.symbol for r in symbol_data.rows)

    def get_trading_calendar(
        self,
        start: date_type,
        end: date_type,
        market: str = "KOSPI",
    ) -> list[date_type]:
        """거래일 목록 반환.

        Args:
            start / end: 조회 범위 (inclusive).
            market: "KOSPI" / "KOSDAQ" / "KONEX". 기본 "KOSPI".

        Returns:
            거래일 date 리스트 (date ASC). 비거래일(공휴일 등)은 포함하지 않음.

        Raises:
            PykrxImportError: pykrx 미설치.
            FatalCollectorError: 지원하지 않는 시장 / start > end.
        """
        collector = self._get_collector()
        cal_data = collector.collect_trading_calendar(
            start_date=start,
            end_date=end,
            market=market,
        )
        # 결정론: date ASC (PykrxCollector가 이미 정렬하지만 명시)
        return sorted(r.date for r in cal_data.rows if r.is_trading_day)

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _get_collector(self) -> PykrxCollector:
        """PykrxCollector 인스턴스 반환 (lazy 생성 + pykrx 설치 확인)."""
        if self._collector is None:
            self._ensure_pykrx_available()
            self._collector = self._make_collector(markets=self._markets)
        return self._collector

    def _make_collector(self, markets: tuple[str, ...]) -> PykrxCollector:
        """PykrxCollector 생성 헬퍼."""
        kwargs: dict[str, Any] = {
            "backoff": self._backoff,
            "validate": self._validate,
            "markets": markets,
        }
        if self._sleep_fn is not None:
            kwargs["sleep_fn"] = self._sleep_fn
        return PykrxCollector(**kwargs)

    @staticmethod
    def _ensure_pykrx_available() -> None:
        """pykrx 설치 여부 확인. 미설치 시 PykrxImportError 발생.

        lazy import — 본 메서드 호출 전까지 pykrx import를 시도하지 않음.
        """
        try:
            import pykrx  # noqa: PLC0415, F401
        except ImportError as exc:
            raise PykrxImportError(
                "pykrx 라이브러리가 설치되지 않았습니다. "
                "운용 환경에서는 `pip install pykrx`로 설치하세요. "
                "테스트 환경에서는 unittest.mock.patch로 pykrx를 mock하세요."
            ) from exc

    @staticmethod
    def _empty_price_df() -> pd.DataFrame:
        """빈 결과 — 컬럼 명세 동일 (호출자 안정성)."""
        return pd.DataFrame(
            {col: pd.Series(dtype="object") for col in PYKRX_PROVIDER_COLUMNS}
        )


__all__ = [
    "PykrxProvider",
    "PykrxImportError",
    "PYKRX_PROVIDER_COLUMNS",
]
