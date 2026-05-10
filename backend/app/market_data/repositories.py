"""시장데이터 테이블 CRUD 리포지토리 (시장데이터 트랙 1단계).

본 모듈은 LocalCsvProvider / PriceLoader / UniverseSelector / pykrx collector가 위임할
저수준 데이터 액세스 함수만 정의한다. 외부 fetch / 수정주가 재계산 / forward-fill은
모두 후속 step의 책임이다.

설계 출처:
    - 07번 §11 / §12 / §12-A : 테이블 스키마
    - 06번 §6 / §7 / §8       : 종목 마스터, 일봉, UniverseSelector
    - 14번 §10 / §11 / §14    : 생존편향, 캐시, 거래일 캘린더
    - 13번 §7 / §11 / §13.13  : 수정주가, 거래일, 생존편향

결정론 정책 (CLAUDE.md #8 + 13.12):
    - 모든 list 반환 함수는 (date ASC, symbol ASC) tie-breaker 강제
    - dict 순회 의존 금지
    - bulk_upsert는 (symbol, date) 정렬 후 처리
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.corporate_action import (
    CORPORATE_ACTION_EVENT_TYPES,
    CorporateAction,
)
from app.models.daily_price import DailyPrice
from app.models.symbol import Symbol
from app.models.trading_calendar import TradingCalendar

# ---------------------------------------------------------------------------
# symbols
# ---------------------------------------------------------------------------


def upsert_symbol(session: Session, symbol_data: Mapping[str, Any]) -> Symbol:
    """종목 마스터 upsert.

    Args:
        symbol_data: dict — 최소 키: symbol / name / market / listing_date.
            선택 키: sector / delisting_date / is_etf / is_etn / is_spac /
            is_preferred / is_managed / is_halted.

    Returns:
        등록 또는 갱신된 Symbol ORM 객체 (flush까지만, commit은 호출자 책임).

    Raises:
        KeyError: 필수 키 누락.
    """
    if "symbol" not in symbol_data:
        raise KeyError("symbol_data missing required key: 'symbol'")

    symbol_code = symbol_data["symbol"]
    existing = session.get(Symbol, symbol_code)

    # 13.13 / 14.10: delisting_date는 NULL 허용 (폐지 종목 보존). 명시적으로 None 들어오면 그대로 둠.
    if existing is None:
        # 신규 등록: NOT NULL 컬럼은 기본값 적용
        new = Symbol(
            symbol=symbol_code,
            name=symbol_data.get("name", ""),
            market=symbol_data["market"],
            sector=symbol_data.get("sector"),
            listing_date=symbol_data["listing_date"],
            delisting_date=symbol_data.get("delisting_date"),
            is_etf=bool(symbol_data.get("is_etf", False)),
            is_etn=bool(symbol_data.get("is_etn", False)),
            is_spac=bool(symbol_data.get("is_spac", False)),
            is_preferred=bool(symbol_data.get("is_preferred", False)),
            is_managed=bool(symbol_data.get("is_managed", False)),
            is_halted=bool(symbol_data.get("is_halted", False)),
        )
        session.add(new)
        session.flush()
        return new

    # 갱신: 들어온 키만 덮어씀 (None도 명시 키면 반영)
    updatable = (
        "name",
        "market",
        "sector",
        "listing_date",
        "delisting_date",
        "is_etf",
        "is_etn",
        "is_spac",
        "is_preferred",
        "is_managed",
        "is_halted",
    )
    for key in updatable:
        if key in symbol_data:
            setattr(existing, key, symbol_data[key])
    session.flush()
    return existing


def get_symbol(session: Session, symbol: str) -> Symbol | None:
    """단일 종목 조회. 없으면 None."""
    return session.get(Symbol, symbol)


def list_symbols(
    session: Session,
    market: str | None = None,
    as_of_date: date_type | None = None,
) -> list[Symbol]:
    """종목 목록 조회 — (symbol ASC) 정렬.

    Args:
        market: KOSPI / KOSDAQ / KONEX. None이면 전 시장.
        as_of_date: 지정 시 13.13 생존편향 필터 적용
            (`listing_date <= as_of_date < (delisting_date or +∞)`).
            None이면 모든 등록 종목 반환.

    Returns:
        Symbol 리스트 (symbol ASC).
    """
    stmt = select(Symbol)
    if market is not None:
        stmt = stmt.where(Symbol.market == market)
    if as_of_date is not None:
        stmt = stmt.where(
            and_(
                Symbol.listing_date <= as_of_date,
                or_(Symbol.delisting_date.is_(None), Symbol.delisting_date > as_of_date),
            )
        )
    stmt = stmt.order_by(Symbol.symbol.asc())
    return list(session.execute(stmt).scalars().all())


def get_universe_at_date(
    session: Session,
    market: str,
    as_of_date: date_type,
) -> list[Symbol]:
    """특정 날짜에 활성 상태인 종목 리스트 (UniverseSelector가 위임할 진입점).

    13.15 look-ahead bias 차단:
        - listing_date <= as_of_date (미래 상장 종목 제외)
        - delisting_date is NULL OR delisting_date > as_of_date (이미 폐지 종목 제외)

    13.13 / 14.10 생존편향:
        - 폐지 종목도 symbols 테이블에 보존되어 있으므로
          폐지 시점 이전을 조회하면 정상적으로 결과에 포함됨.

    06번 §8 공통 필터(`exclude_etf` 등)는 본 함수가 적용하지 않는다.
    UniverseSelector가 본 함수의 결과에 추가 필터를 적용하는 구조 (책임 분리).

    Args:
        market: KOSPI / KOSDAQ / KONEX (단일 시장만 — 멀티 시장은 호출자가 합집합).
        as_of_date: 기준 날짜.

    Returns:
        Symbol 리스트 (symbol ASC) — 결정론 보장.
    """
    return list_symbols(session, market=market, as_of_date=as_of_date)


# ---------------------------------------------------------------------------
# daily_prices
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def bulk_upsert_daily_prices(
    session: Session,
    rows: Iterable[Mapping[str, Any]],
) -> int:
    """일봉 bulk upsert.

    UniqueConstraint(symbol, date) 위반 시 갱신 (close/adj_close/volume 등 모두 덮어씀).

    13.7 수정주가 정책: open/high/low/close + adj_open/adj_high/adj_low/adj_close +
                      volume/adj_volume이 모두 NOT NULL이므로 dict에 키 누락 시 KeyError.
    14.10 결손 정책: 결손 봉 row는 호출자가 입력에 포함시키지 말 것.
                    forward-fill을 본 함수가 수행하지 않음.

    결정론: 입력을 (symbol ASC, date ASC)로 정렬한 뒤 처리.

    Args:
        rows: dict 시퀀스. 필수 키: symbol / date / open / high / low / close /
              volume / adj_open / adj_high / adj_low / adj_close / adj_volume.
              선택 키: market_cap.

    Returns:
        upsert 처리한 row 수 (신규 + 갱신 합).

    Raises:
        KeyError: 필수 키 누락.
    """
    rows_list = list(rows)
    rows_list.sort(key=lambda r: (str(r["symbol"]), r["date"]))

    required = (
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

    count = 0
    for row in rows_list:
        for key in required:
            if key not in row:
                raise KeyError(
                    f"daily_price row missing required key: {key!r} (symbol={row.get('symbol')})"
                )
        # 기존 row 조회 (UniqueConstraint으로 0 또는 1건)
        existing_stmt = (
            select(DailyPrice)
            .where(DailyPrice.symbol == row["symbol"])
            .where(DailyPrice.date == row["date"])
        )
        existing = session.execute(existing_stmt).scalar_one_or_none()
        if existing is None:
            new = DailyPrice(
                symbol=row["symbol"],
                date=row["date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                adj_open=row["adj_open"],
                adj_high=row["adj_high"],
                adj_low=row["adj_low"],
                adj_close=row["adj_close"],
                adj_volume=row["adj_volume"],
                market_cap=row.get("market_cap"),
                created_at=_utcnow(),
            )
            session.add(new)
        else:
            existing.open = row["open"]
            existing.high = row["high"]
            existing.low = row["low"]
            existing.close = row["close"]
            existing.volume = row["volume"]
            existing.adj_open = row["adj_open"]
            existing.adj_high = row["adj_high"]
            existing.adj_low = row["adj_low"]
            existing.adj_close = row["adj_close"]
            existing.adj_volume = row["adj_volume"]
            if "market_cap" in row:
                existing.market_cap = row["market_cap"]
        count += 1

    session.flush()
    return count


def get_daily_price(
    session: Session,
    symbol: str,
    date: date_type,
) -> DailyPrice | None:
    """단일 (symbol, date) 일봉 조회. 없으면 None (결손 봉 또는 휴장일)."""
    stmt = (
        select(DailyPrice)
        .where(DailyPrice.symbol == symbol)
        .where(DailyPrice.date == date)
    )
    return session.execute(stmt).scalar_one_or_none()


def get_price_range(
    session: Session,
    symbol: str,
    start_date: date_type,
    end_date: date_type,
) -> list[DailyPrice]:
    """기간 일봉 조회 — (date ASC) 정렬.

    14.10 결손 정책: 결손 봉은 row가 없으므로 결과에서도 빠진다.
    PriceLoader가 trading_calendar와 대조해 결손을 별도 보고할 책임을 가짐.

    Args:
        start_date: 포함.
        end_date: 포함.
    """
    stmt = (
        select(DailyPrice)
        .where(DailyPrice.symbol == symbol)
        .where(DailyPrice.date >= start_date)
        .where(DailyPrice.date <= end_date)
        .order_by(DailyPrice.date.asc())
    )
    return list(session.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# trading_calendar
# ---------------------------------------------------------------------------


def is_trading_day(
    session: Session,
    date: date_type,
    market: str = "KOSPI",
) -> bool:
    """해당 날짜가 거래일인지.

    캘린더에 row가 없으면 False (안전 측: 모르는 날짜는 거래일이 아님으로 간주).
    호출자가 캘린더 결손을 별도로 감지하려면 직접 조회 필요.
    """
    stmt = (
        select(TradingCalendar.is_trading_day)
        .where(TradingCalendar.date == date)
        .where(TradingCalendar.market == market)
    )
    result = session.execute(stmt).scalar_one_or_none()
    return bool(result) if result is not None else False


def get_trading_days(
    session: Session,
    start_date: date_type,
    end_date: date_type,
    market: str = "KOSPI",
) -> list[date_type]:
    """기간 내 거래일 리스트 (date ASC).

    Args:
        start_date / end_date: 포함.
        market: 기본 KOSPI.

    Returns:
        is_trading_day=True인 날짜 리스트, 오름차순.
    """
    stmt = (
        select(TradingCalendar.date)
        .where(TradingCalendar.market == market)
        .where(TradingCalendar.is_trading_day.is_(True))
        .where(TradingCalendar.date >= start_date)
        .where(TradingCalendar.date <= end_date)
        .order_by(TradingCalendar.date.asc())
    )
    return list(session.execute(stmt).scalars().all())


def upsert_trading_day(
    session: Session,
    date: date_type,
    market: str,
    is_trading_day: bool,
    holiday_name: str | None = None,
) -> TradingCalendar:
    """거래일 캘린더 단일 row upsert.

    bulk 시드는 후속 step에서 별도 함수로 추가 (본 step은 단일 upsert만으로 충분).
    """
    existing = session.get(TradingCalendar, (date, market))
    if existing is None:
        new = TradingCalendar(
            date=date,
            market=market,
            is_trading_day=is_trading_day,
            holiday_name=holiday_name,
            created_at=_utcnow(),
        )
        session.add(new)
        session.flush()
        return new
    existing.is_trading_day = is_trading_day
    existing.holiday_name = holiday_name
    session.flush()
    return existing


# ---------------------------------------------------------------------------
# corporate_actions (026 추가)
# ---------------------------------------------------------------------------


def upsert_corporate_action(
    session: Session,
    data: Mapping[str, Any],
) -> CorporateAction:
    """corporate_actions 단일 row upsert.

    UniqueConstraint(symbol, event_date, event_type) 위반 시 갱신 (ratio /
    dividend_amount / notes).

    13.7 / 14.9 정합성:
        - close (원 가격)는 본 함수의 책임 밖 — 본 함수는 corporate_action 사실만 보존.
        - adj_* 재계산은 AdjustedPriceProcessor (data_pipeline/processors/adjusted_price.py).

    14.9 look-ahead 차단: 호출자가 미래 event_date를 넣어도 본 함수는 허용한다
    (수집 시점의 사실 자체는 보존). Processor가 적용 시점에 `event_date <= as_of_date`로 필터.

    Args:
        data: dict — 필수 키: symbol / event_date / event_type.
            선택 키: ratio (기본 0.0) / dividend_amount (기본 NULL) / notes.

    Returns:
        등록 또는 갱신된 CorporateAction (flush까지만, commit은 호출자 책임).

    Raises:
        KeyError: 필수 키 누락.
        ValueError: 알 수 없는 event_type.
    """
    for key in ("symbol", "event_date", "event_type"):
        if key not in data:
            raise KeyError(f"corporate_action data missing required key: {key!r}")

    event_type = str(data["event_type"])
    if event_type not in CORPORATE_ACTION_EVENT_TYPES:
        raise ValueError(
            f"알 수 없는 event_type: {event_type!r}. "
            f"허용: {CORPORATE_ACTION_EVENT_TYPES}"
        )

    # 기존 row 조회 (UniqueConstraint으로 0 또는 1건)
    existing_stmt = (
        select(CorporateAction)
        .where(CorporateAction.symbol == data["symbol"])
        .where(CorporateAction.event_date == data["event_date"])
        .where(CorporateAction.event_type == event_type)
    )
    existing = session.execute(existing_stmt).scalar_one_or_none()

    if existing is None:
        new = CorporateAction(
            symbol=data["symbol"],
            event_date=data["event_date"],
            event_type=event_type,
            ratio=float(data.get("ratio", 0.0)),
            dividend_amount=(
                float(data["dividend_amount"])
                if data.get("dividend_amount") is not None
                else None
            ),
            notes=data.get("notes"),
            created_at=_utcnow(),
        )
        session.add(new)
        session.flush()
        return new

    if "ratio" in data:
        existing.ratio = float(data["ratio"])
    if "dividend_amount" in data:
        existing.dividend_amount = (
            float(data["dividend_amount"])
            if data["dividend_amount"] is not None
            else None
        )
    if "notes" in data:
        existing.notes = data["notes"]
    session.flush()
    return existing


def get_corporate_actions(
    session: Session,
    symbol: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> list[CorporateAction]:
    """종목별 corporate_actions 조회 — (event_date ASC, event_type ASC) 정렬.

    결정론 (CLAUDE.md #8): 정렬 키 명시. AdjustedPriceProcessor는 본 결과를 받아
    내부에서 시간 역순(event_date DESC, event_type ASC)으로 다시 정렬해 적용한다.

    Args:
        symbol: 6자리 종목코드.
        start_date: 포함. None이면 무제한 과거.
        end_date: 포함. None이면 무제한 미래.

    Returns:
        CorporateAction 리스트, (event_date ASC, event_type ASC).
    """
    stmt = (
        select(CorporateAction)
        .where(CorporateAction.symbol == symbol)
        .order_by(CorporateAction.event_date.asc(), CorporateAction.event_type.asc())
    )
    if start_date is not None:
        stmt = stmt.where(CorporateAction.event_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(CorporateAction.event_date <= end_date)
    return list(session.execute(stmt).scalars().all())
