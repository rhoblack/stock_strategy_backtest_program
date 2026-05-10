"""시장 데이터 Provider 공통 인터페이스 (06번 §4 / 14번 §4.4).

본 모듈은 LocalCsvProvider / PykrxProvider / FinanceDataReaderProvider 등
모든 시장 데이터 공급자가 따라야 할 추상 베이스를 정의한다.

설계 결정:
    - **추상 베이스 클래스 (ABC)**를 채택. typing.Protocol도 후보였으나,
      (a) 본 베이스가 공통 헬퍼(정렬/검증)를 보유할 여지가 있고,
      (b) 구현체가 명시적으로 상속해 누락 시 즉시 오류가 나는 편이
      Provider 추가 시 안전하기 때문.
    - **단일 진입점 `ingest_into(session, ...)`**로 흐름을 단순화.
      - LocalCsvProvider: CSV → DB 적재 (외부 fetch 없음)
      - PykrxProvider (Phase 11): pykrx fetch → DB 적재
      - 호출자는 동일한 인터페이스만 알면 됨.
    - 06번 §4의 `get_symbols / get_daily_prices / ...` 메서드는 본 step 범위 밖.
      Phase 11에서 PykrxProvider를 도입할 때 fetch 메서드 시그니처를 함께 확정.

결정론 (CLAUDE.md #8):
    - 모든 구현체는 ingest 시 (symbol ASC, date ASC) 정렬을 보장해야 한다.
    - 본 베이스의 `_sorted_symbol_rows / _sorted_price_rows` 헬퍼 사용 권장.

외부 fetch 0건:
    - 본 모듈은 인터페이스만 정의. 네트워크 호출 없음.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class IngestResult:
    """ingest_into의 반환값 — 적재 통계.

    호출자가 결과를 검증/로깅할 수 있도록 row 카운트를 분리해 보관한다.
    구현체는 모든 카운트를 0 이상으로 채워야 한다 (음수 금지).
    """

    symbols_upserted: int = 0
    daily_prices_upserted: int = 0
    trading_days_upserted: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return (
            self.symbols_upserted
            + self.daily_prices_upserted
            + self.trading_days_upserted
        )


class BaseProvider(ABC):
    """시장 데이터 공급자 공통 베이스 (06번 §4 / 14번 §4.4).

    구현체는 `ingest_into(session, ...)`만 구현하면 되며,
    내부에서 `app.market_data.repositories`의 upsert/bulk_upsert 함수를 호출해
    DB에 적재한다.

    Args:
        name: provider 식별자 (로그/경고 메시지에 사용).

    Subclass 책임:
        - 외부 fetch 또는 파일 I/O로 raw 데이터 수집
        - dict 시퀀스로 정규화 후 repositories.* 호출
        - (symbol ASC, date ASC) 정렬 결정론 보장
        - 14.10 결손 정책: forward-fill 금지 — 결손 봉은 출력에 포함시키지 말 것
        - 13.7 수정주가 정책: close + adj_close 둘 다 채워서 전달
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def ingest_into(
        self,
        session: Session,
        *,
        symbols: Sequence[str] | None = None,
        start_date: date_type | None = None,
        end_date: date_type | None = None,
    ) -> IngestResult:
        """raw 데이터 수집 + DB 적재 단일 진입점.

        Args:
            session: SQLAlchemy Session. commit은 호출자 책임 (provider는 flush까지만).
            symbols: None이면 provider 기본 범위 (LocalCsv는 CSV에 포함된 전 종목,
                Pykrx는 KOSPI+KOSDAQ 전 종목 등). 구현체 문서에 명시.
            start_date / end_date: None이면 provider 기본 범위.

        Returns:
            IngestResult — symbols / daily_prices / trading_days 적재 row 수 + 경고.

        Raises:
            ValueError / KeyError: 입력 데이터가 13.7 / 14.10 정책에 위배될 때.
        """

    # ------------------------------------------------------------------
    # Subclass용 결정론 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _sorted_symbol_rows(
        rows: Iterable[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        """종목 마스터 dict 시퀀스를 (symbol ASC) 정렬해 반환.

        결정론 보장: dict 순회 / 입력 순서에 의존하지 않음.
        """
        return sorted(rows, key=lambda r: str(r["symbol"]))

    @staticmethod
    def _sorted_price_rows(
        rows: Iterable[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        """일봉 dict 시퀀스를 (symbol ASC, date ASC) 정렬해 반환.

        결정론 보장: dict 순회 / 입력 순서에 의존하지 않음.
        """
        return sorted(rows, key=lambda r: (str(r["symbol"]), r["date"]))

    @staticmethod
    def _sorted_calendar_rows(
        rows: Iterable[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        """거래일 캘린더 dict 시퀀스를 (market ASC, date ASC) 정렬해 반환."""
        return sorted(rows, key=lambda r: (str(r["market"]), r["date"]))


__all__ = ["BaseProvider", "IngestResult"]
