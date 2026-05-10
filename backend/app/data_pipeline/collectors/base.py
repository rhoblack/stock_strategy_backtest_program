"""BaseCollector 추상 인터페이스 (14번 §3 / §5 / §6).

본 모듈은 외부 데이터 소스(pykrx, FinanceDataReader, KRX 직접 호출 등)에서 raw
데이터를 가져와 표준 dataclass로 반환하는 collector의 공통 베이스를 정의한다.

설계 결정 (인계 정보 — 025 PykrxCollector가 그대로 따름):

    1. **3-메서드 분할** (단일 collect 진입점이 아님)
        - `collect_symbols(as_of_date) -> RawSymbolsData`
        - `collect_daily_prices(symbols, start_date, end_date) -> RawDailyPricesData`
        - `collect_trading_calendar(start_date, end_date, market) -> RawCalendarData`

        근거: 14번 §3 데이터 수집 대상이 명확히 3종(종목 마스터 / 일봉 / 거래일).
        각 종류는 호출 빈도, rate-limit 부담, 갱신 주기가 모두 다르므로
        진입점을 분리해 부분 재시도와 잡 단위 스케줄링이 자연스럽다.
        (corporate_actions / market_indices는 027~ 후속 step에서 별도 메서드 추가 예정.)

    2. **Provider(018) vs Collector 책임 분리**
        - `BaseProvider.ingest_into(session, ...)`: raw 수집 + DB 적재 단일 진입점.
          호출자(API/CLI)가 "한 번에 끝내고 싶을 때" 사용.
        - `BaseCollector.collect_*`: 외부 fetch만, DB 미터치.
          ETL의 E(Extract)만 담당. 후속 Processor가 T(Transform), repositories가 L(Load).
        - 두 추상화는 직교: PykrxProvider(향후)는 내부에서 PykrxCollector를 호출하고
          processors → repositories 순으로 위임할 수 있음.

    3. **frozen dataclass + tuple 필드** (결정론, CLAUDE.md #8 + 13.12)
        - dict 순회 의존 금지 → 모든 필드는 tuple로 정렬 보장
        - 변경 불가 → 캐시/스냅샷 안전

    4. **외부 fetch 0건** (본 step)
        - 본 모듈은 ABC + dataclass만 정의. import pykrx 금지.
        - 실제 PykrxCollector는 025에서 본 베이스를 상속.

예외 정책 (`app.data_pipeline.exceptions`):
    - 외부 API 5xx / 일시 차단 → `RetryableCollectorError(CollectorError, RetryableError)` (025)
    - 인증/스키마 위반 → `FatalCollectorError(CollectorError, FatalError)` (025)
    - 본 step에서는 다중상속 구체 예외를 만들지 않음 (025 결정).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date as date_type

# ---------------------------------------------------------------------------
# Raw row dataclasses — 개별 row 표준
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawSymbolRow:
    """종목 마스터 단일 row (14번 §3.1 / 06번 §6).

    14.10 생존편향 정책: delisting_date는 None 허용 (폐지 종목 보존).
    14.9 look-ahead 정책: collector는 as_of_date 기준 미래 상장 종목을 수집해서는 안 됨.

    필수: symbol / name / market / listing_date.
    선택 (기본 False/None): sector / delisting_date / 플래그.
    """

    symbol: str
    name: str
    market: str
    listing_date: date_type
    sector: str | None = None
    delisting_date: date_type | None = None
    is_etf: bool = False
    is_etn: bool = False
    is_spac: bool = False
    is_preferred: bool = False
    is_managed: bool = False
    is_halted: bool = False


@dataclass(frozen=True)
class RawDailyPriceRow:
    """일봉 단일 row (14번 §3.2).

    13.7 수정주가 정책: close + adj_close 둘 다 NOT NULL.
    14.10 결손 정책: 결손 봉은 row를 만들지 말 것 (forward-fill 금지).
    """

    symbol: str
    date: date_type
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_open: float
    adj_high: float
    adj_low: float
    adj_close: float
    adj_volume: float
    market_cap: float | None = None


@dataclass(frozen=True)
class RawCalendarRow:
    """거래일 캘린더 단일 row (14번 §3.3 / §14)."""

    date: date_type
    market: str
    is_trading_day: bool
    holiday_name: str | None = None


# ---------------------------------------------------------------------------
# Raw 컬렉션 dataclasses — collector 출력 표준
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawSymbolsData:
    """`collect_symbols` 반환 — 종목 마스터 정렬 컬렉션.

    Attributes:
        rows: (symbol ASC) 정렬된 종목 row 튜플 — 결정론 강제.
        as_of_date: 어느 기준 일자에 본 스냅샷이 유효한지 (14.9 look-ahead 차단 메타).
        source: 데이터 소스 식별자 (예: "pykrx", "finance_data_reader").
        warnings: 결손/일시 오류 등 경고 메시지 — 호출자가 로깅/알림으로 활용.
    """

    rows: tuple[RawSymbolRow, ...]
    as_of_date: date_type
    source: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RawDailyPricesData:
    """`collect_daily_prices` 반환 — 일봉 정렬 컬렉션.

    Attributes:
        rows: (symbol ASC, date ASC) 정렬된 일봉 row 튜플 — 결정론 강제.
        start_date / end_date: 요청 범위 echo (호출자 검증용).
        source / warnings: RawSymbolsData와 동일.
    """

    rows: tuple[RawDailyPriceRow, ...]
    start_date: date_type
    end_date: date_type
    source: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RawCalendarData:
    """`collect_trading_calendar` 반환 — 거래일 캘린더 정렬 컬렉션.

    Attributes:
        rows: (market ASC, date ASC) 정렬된 캘린더 row 튜플.
        market: 단일 시장만 — 멀티 시장 합집합은 호출자 책임.
    """

    rows: tuple[RawCalendarRow, ...]
    start_date: date_type
    end_date: date_type
    market: str
    source: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# BaseCollector
# ---------------------------------------------------------------------------


class BaseCollector(ABC):
    """외부 데이터 소스에서 raw 데이터를 수집하는 collector의 추상 베이스 (14번 §5).

    구현체는 3개 메서드를 모두 구현해야 한다 (부분 미지원 시 명시적 NotImplementedError 또는
    `FatalCollectorError`). 결정론을 위해 모든 출력은 정렬된 tuple로 반환.

    Args:
        name: collector 식별자 (로그/경고 메시지에 사용).

    Subclass 책임 (025 PykrxCollector가 따라야 함):
        - 외부 API 호출 (pykrx 등)
        - 5xx/rate-limit → `RetryableCollectorError` (025에서 다중상속 정의)
        - 인증/스키마 → `FatalCollectorError`
        - 입력 정규화 후 정렬된 tuple로 RawXxxData 구성
        - source 필드에 본인 식별자 명시 (예: "pykrx")
        - warnings 필드에 부분 결손/일시 오류 누적

    014 BaseProvider와의 차이:
        - Provider: raw 수집 + DB 적재 (ingest_into 단일 진입점, 외부 호출자 친화적)
        - Collector: raw 수집만 (DB 미터치, ETL의 E만 담당)
        - PykrxProvider(향후)는 내부에서 PykrxCollector를 호출하고 processors/repositories에 위임 가능.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def collect_symbols(self, as_of_date: date_type) -> RawSymbolsData:
        """종목 마스터 수집 (14번 §3.1 / §6.2).

        Args:
            as_of_date: 기준 일자. 본 일자 시점에 상장된 종목 + 그 시점 이전 폐지 종목까지.
                14.9 look-ahead 차단: as_of_date 이후 상장 예정 종목 수집 금지.

        Returns:
            RawSymbolsData — (symbol ASC) 정렬.

        Raises:
            CollectorError: 일반 수집 실패.
            RetryableError: 일시적 오류 (재시도 권장).
            FatalError: 영구 오류 (재시도 무의미).
        """

    @abstractmethod
    def collect_daily_prices(
        self,
        symbols: tuple[str, ...] | list[str],
        start_date: date_type,
        end_date: date_type,
    ) -> RawDailyPricesData:
        """일봉 수집 (14번 §3.2 / §6.1).

        Args:
            symbols: 수집할 종목 리스트 (KRX 6자리 코드).
            start_date / end_date: 포함 범위.

        Returns:
            RawDailyPricesData — (symbol ASC, date ASC) 정렬.
            결손 봉은 row 누락(14.10) — forward-fill 금지.

        Raises:
            CollectorError / RetryableError / FatalError.
        """

    @abstractmethod
    def collect_trading_calendar(
        self,
        start_date: date_type,
        end_date: date_type,
        market: str,
    ) -> RawCalendarData:
        """거래일 캘린더 수집 (14번 §3.3 / §14).

        Args:
            start_date / end_date: 포함 범위.
            market: 단일 시장 (KOSPI / KOSDAQ / KONEX).

        Returns:
            RawCalendarData — (market ASC, date ASC) 정렬.
        """

    # ------------------------------------------------------------------
    # Subclass용 결정론 헬퍼 — 정렬 tuple 변환
    # ------------------------------------------------------------------

    @staticmethod
    def _to_sorted_symbol_tuple(rows: list[RawSymbolRow]) -> tuple[RawSymbolRow, ...]:
        """RawSymbolRow 리스트를 (symbol ASC) tuple로 변환.

        결정론 보장: 입력 순서/dict 순회에 의존하지 않음.
        """
        return tuple(sorted(rows, key=lambda r: r.symbol))

    @staticmethod
    def _to_sorted_price_tuple(
        rows: list[RawDailyPriceRow],
    ) -> tuple[RawDailyPriceRow, ...]:
        """RawDailyPriceRow 리스트를 (symbol ASC, date ASC) tuple로 변환."""
        return tuple(sorted(rows, key=lambda r: (r.symbol, r.date)))

    @staticmethod
    def _to_sorted_calendar_tuple(
        rows: list[RawCalendarRow],
    ) -> tuple[RawCalendarRow, ...]:
        """RawCalendarRow 리스트를 (market ASC, date ASC) tuple로 변환."""
        return tuple(sorted(rows, key=lambda r: (r.market, r.date)))


# RawData 별칭 — 호출자가 단일 union 타입으로 다루고 싶을 때
RawData = RawSymbolsData | RawDailyPricesData | RawCalendarData


__all__ = [
    "BaseCollector",
    "RawSymbolRow",
    "RawDailyPriceRow",
    "RawCalendarRow",
    "RawSymbolsData",
    "RawDailyPricesData",
    "RawCalendarData",
    "RawData",
]
