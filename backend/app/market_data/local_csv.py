"""LocalCsvProvider — CSV 파일에서 시장데이터를 읽어 DB에 적재 (06번 §5 / 14번 §17).

dev/test/demo 용도 — 실제 KRX 데이터 수집은 Phase 11 PykrxProvider 영역.

CSV 형식 (본 step 명세):
    1. `symbols.csv` (필수)
       컬럼: symbol, name, market, [sector, listing_date, delisting_date,
              is_etf, is_etn, is_spac, is_preferred, is_managed, is_halted]
       - symbol: KRX 6자리 코드 (선두 0 보존, 문자열로 읽음)
       - market: KOSPI / KOSDAQ / KONEX
       - listing_date: YYYY-MM-DD (필수)
       - delisting_date: YYYY-MM-DD 또는 빈 문자열 (NULL — 13.13 폐지 종목 보존)
       - is_*: 0/1, true/false, True/False 모두 허용

    2. `daily_prices.csv` (선택 — 파일 없으면 적재 건너뜀)
       컬럼: symbol, date, open, high, low, close, volume,
              adj_open, adj_high, adj_low, adj_close, adj_volume, [market_cap]
       - 모든 가격/거래량 필드는 NOT NULL (13.7 — close + adj_close 둘 다 필수)
       - market_cap은 빈 칸 허용 (NULL — 14.8.3에서 일부 종목/일자 미수집 가능)
       - **결손 봉은 행을 작성하지 말 것** (14.10 — forward-fill 금지).
         본 provider는 결손을 자동 채우지 않음.

    3. `trading_calendar.csv` (선택 — 파일 없으면 적재 건너뜀)
       컬럼: date, market, is_trading_day, [holiday_name]

정책:
    - 13.7: close + adj_close 모두 NOT NULL — 누락 시 명확한 KeyError/ValueError
    - 14.10: 결손 봉 자동 채움 금지 — CSV에 행이 없으면 DB에도 행 없음
    - 13.15 / 13.13: delisting_date 보존 (CSV 빈 칸 → DB NULL)
    - CLAUDE.md #8 결정론: 입력을 정렬한 뒤 처리

외부 fetch: 0건 (네트워크 호출 없음, pykrx import 없음).
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.market_data import repositories
from app.market_data.provider import BaseProvider, IngestResult

# ---------------------------------------------------------------------------
# CSV 파싱 헬퍼
# ---------------------------------------------------------------------------


_BOOL_TRUE = frozenset({"1", "true", "t", "y", "yes"})
_BOOL_FALSE = frozenset({"0", "false", "f", "n", "no", ""})


def _parse_bool(raw: str | None, *, default: bool = False) -> bool:
    """0/1, true/false, T/F를 bool로 변환. 빈 문자열은 default."""
    if raw is None:
        return default
    text = raw.strip().lower()
    if text == "":
        return default
    if text in _BOOL_TRUE:
        return True
    if text in _BOOL_FALSE:
        return False
    raise ValueError(f"불리언 값으로 해석 불가: {raw!r}")


def _parse_date(raw: str | None) -> date_type | None:
    """YYYY-MM-DD를 date로. 빈 문자열은 None."""
    if raw is None:
        return None
    text = raw.strip()
    if text == "":
        return None
    return datetime.strptime(text, "%Y-%m-%d").date()


def _parse_required_date(raw: str | None, *, field: str, symbol: str = "") -> date_type:
    parsed = _parse_date(raw)
    if parsed is None:
        raise ValueError(
            f"필수 날짜 컬럼 누락: {field} (symbol={symbol!r})"
        )
    return parsed


def _parse_float(raw: str | None, *, field: str, symbol: str = "", date: str = "") -> float:
    if raw is None or raw.strip() == "":
        raise ValueError(
            f"필수 숫자 컬럼 누락: {field} (symbol={symbol!r}, date={date!r})"
        )
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"숫자 파싱 실패: {field}={raw!r} (symbol={symbol!r}, date={date!r})"
        ) from exc


def _parse_optional_float(raw: str | None) -> float | None:
    if raw is None or raw.strip() == "":
        return None
    return float(raw)


# ---------------------------------------------------------------------------
# LocalCsvProvider
# ---------------------------------------------------------------------------


# 13.7: close + adj_close 둘 다 NOT NULL — daily_prices.csv 필수 컬럼
_REQUIRED_PRICE_COLUMNS = (
    "symbol",
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
)
_REQUIRED_SYMBOL_COLUMNS = ("symbol", "name", "market", "listing_date")
_REQUIRED_CALENDAR_COLUMNS = ("date", "market", "is_trading_day")


class LocalCsvProvider(BaseProvider):
    """로컬 CSV 디렉토리를 읽어 repositories.* 함수로 DB에 적재.

    Args:
        root: 다음 파일들이 위치한 디렉토리.
              - symbols.csv (필수)
              - daily_prices.csv (선택)
              - trading_calendar.csv (선택)
        name: provider 식별자 (기본 "local_csv").

    사용 예시:
        from app.market_data.local_csv import LocalCsvProvider

        provider = LocalCsvProvider(root=Path("data/sample"))
        result = provider.ingest_into(session)
        session.commit()
        print(result.symbols_upserted, result.daily_prices_upserted)
    """

    def __init__(self, root: str | Path, *, name: str = "local_csv") -> None:
        super().__init__(name=name)
        self.root = Path(root)

    # ------------------------------------------------------------------
    # ingest_into
    # ------------------------------------------------------------------

    def ingest_into(
        self,
        session: Session,
        *,
        symbols: Sequence[str] | None = None,
        start_date: date_type | None = None,
        end_date: date_type | None = None,
    ) -> IngestResult:
        """CSV 파일을 읽어 DB에 적재.

        Args:
            session: SQLAlchemy Session. commit은 호출자 책임.
            symbols: 지정 시 해당 종목만 필터링해 적재 (symbols.csv / daily_prices.csv 모두 적용).
            start_date / end_date: 지정 시 daily_prices / trading_calendar의 date를 필터링.

        Returns:
            IngestResult.

        Raises:
            FileNotFoundError: symbols.csv가 없는 경우.
            KeyError: 필수 컬럼 누락.
            ValueError: 필수 값 누락 또는 파싱 실패.
        """
        if not self.root.exists():
            raise FileNotFoundError(f"CSV root 디렉토리 없음: {self.root}")

        symbol_filter = set(symbols) if symbols is not None else None

        result = IngestResult()

        # 1) symbols.csv (필수)
        symbol_rows = self._load_symbols_csv(symbol_filter=symbol_filter)
        for row in symbol_rows:
            repositories.upsert_symbol(session, row)
        # IngestResult는 frozen dataclass — 새로 만들어 누적
        result = IngestResult(
            symbols_upserted=len(symbol_rows),
            daily_prices_upserted=0,
            trading_days_upserted=0,
            warnings=list(result.warnings),
        )

        # 2) daily_prices.csv (선택)
        price_path = self.root / "daily_prices.csv"
        prices_count = 0
        if price_path.exists():
            price_rows = self._load_daily_prices_csv(
                symbol_filter=symbol_filter,
                start_date=start_date,
                end_date=end_date,
            )
            if price_rows:
                prices_count = repositories.bulk_upsert_daily_prices(session, price_rows)

        # 3) trading_calendar.csv (선택)
        calendar_path = self.root / "trading_calendar.csv"
        calendar_count = 0
        if calendar_path.exists():
            calendar_rows = self._load_trading_calendar_csv(
                start_date=start_date,
                end_date=end_date,
            )
            for row in calendar_rows:
                repositories.upsert_trading_day(
                    session,
                    date=row["date"],
                    market=row["market"],
                    is_trading_day=row["is_trading_day"],
                    holiday_name=row.get("holiday_name"),
                )
            calendar_count = len(calendar_rows)

        return IngestResult(
            symbols_upserted=result.symbols_upserted,
            daily_prices_upserted=prices_count,
            trading_days_upserted=calendar_count,
            warnings=list(result.warnings),
        )

    # ------------------------------------------------------------------
    # CSV 로더 (private)
    # ------------------------------------------------------------------

    def _load_symbols_csv(
        self,
        *,
        symbol_filter: set[str] | None,
    ) -> list[dict[str, Any]]:
        path = self.root / "symbols.csv"
        if not path.exists():
            raise FileNotFoundError(f"symbols.csv 없음: {path}")

        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            self._validate_columns(reader.fieldnames, _REQUIRED_SYMBOL_COLUMNS, file=path)
            for raw in reader:
                symbol = raw["symbol"].strip()
                if symbol_filter is not None and symbol not in symbol_filter:
                    continue
                row: dict[str, Any] = {
                    "symbol": symbol,
                    "name": (raw.get("name") or "").strip(),
                    "market": (raw["market"] or "").strip(),
                    "listing_date": _parse_required_date(
                        raw.get("listing_date"), field="listing_date", symbol=symbol
                    ),
                }
                # 선택 필드
                if "sector" in raw:
                    sector = (raw.get("sector") or "").strip()
                    row["sector"] = sector if sector else None
                # delisting_date: 빈 문자열 → NULL (13.13 폐지 종목 보존)
                if "delisting_date" in raw:
                    row["delisting_date"] = _parse_date(raw.get("delisting_date"))
                # 플래그
                for flag in ("is_etf", "is_etn", "is_spac", "is_preferred", "is_managed", "is_halted"):
                    if flag in raw:
                        row[flag] = _parse_bool(raw.get(flag), default=False)
                rows.append(row)

        # 결정론: symbol ASC
        return self._sorted_symbol_rows(rows)  # type: ignore[return-value]

    def _load_daily_prices_csv(
        self,
        *,
        symbol_filter: set[str] | None,
        start_date: date_type | None,
        end_date: date_type | None,
    ) -> list[dict[str, Any]]:
        path = self.root / "daily_prices.csv"
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            self._validate_columns(reader.fieldnames, _REQUIRED_PRICE_COLUMNS, file=path)
            for raw in reader:
                symbol = raw["symbol"].strip()
                if symbol_filter is not None and symbol not in symbol_filter:
                    continue
                date_str = raw["date"].strip()
                row_date = _parse_required_date(date_str, field="date", symbol=symbol)
                if start_date is not None and row_date < start_date:
                    continue
                if end_date is not None and row_date > end_date:
                    continue

                row: dict[str, Any] = {
                    "symbol": symbol,
                    "date": row_date,
                }
                for col in (
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
                ):
                    row[col] = _parse_float(raw.get(col), field=col, symbol=symbol, date=date_str)
                # 13.7 강제 검증 — close / adj_close NOT NULL은 _parse_float에서 이미 처리되지만
                # 명시적 메시지를 남기기 위해 한 번 더 확인
                if row["close"] is None or row["adj_close"] is None:
                    raise ValueError(
                        f"13.7 위반: close + adj_close 둘 다 필수 (symbol={symbol}, date={date_str})"
                    )
                # 선택 필드
                if "market_cap" in raw:
                    row["market_cap"] = _parse_optional_float(raw.get("market_cap"))
                rows.append(row)

        # 결정론: (symbol ASC, date ASC) — bulk_upsert_daily_prices가 다시 정렬하지만 미리 정렬
        return self._sorted_price_rows(rows)  # type: ignore[return-value]

    def _load_trading_calendar_csv(
        self,
        *,
        start_date: date_type | None,
        end_date: date_type | None,
    ) -> list[dict[str, Any]]:
        path = self.root / "trading_calendar.csv"
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            self._validate_columns(reader.fieldnames, _REQUIRED_CALENDAR_COLUMNS, file=path)
            for raw in reader:
                date_str = raw["date"].strip()
                row_date = _parse_required_date(date_str, field="date")
                if start_date is not None and row_date < start_date:
                    continue
                if end_date is not None and row_date > end_date:
                    continue
                row: dict[str, Any] = {
                    "date": row_date,
                    "market": (raw["market"] or "").strip(),
                    "is_trading_day": _parse_bool(raw.get("is_trading_day"), default=False),
                }
                if "holiday_name" in raw:
                    name = (raw.get("holiday_name") or "").strip()
                    row["holiday_name"] = name if name else None
                rows.append(row)

        return self._sorted_calendar_rows(rows)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # 검증
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_columns(
        actual: Sequence[str] | None,
        required: Sequence[str],
        *,
        file: Path,
    ) -> None:
        actual_set = set(actual or [])
        missing = [c for c in required if c not in actual_set]
        if missing:
            raise KeyError(
                f"{file.name} 필수 컬럼 누락: {missing} (있는 컬럼: {sorted(actual_set)})"
            )


__all__ = ["LocalCsvProvider"]
