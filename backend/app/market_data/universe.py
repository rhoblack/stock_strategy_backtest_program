"""UniverseSelector — 06번 §8 공통 필터 + 13번 §13.15 look-ahead 차단.

설계 출처:
    - 06번 §8 (UniverseSelector — 공통 필터 적용 책임)
    - 06번 §9 / §10 (selection_method: ALL / MARKET_CAP_TOP_N / LIQUIDITY_TOP_N)
    - 06번 §11 (생존편향 — listing_date / delisting_date 동적 필터, 016에서 위임)
    - 06번 §12 (기본 제외 옵션 — exclude_etf / exclude_etn / ...)
    - 13번 §7 (수정주가) / §13.13 (생존편향) / §13.15 (look-ahead bias) / §13.12 (결정론)
    - 14번 §8 (시가총액 시계열) / §10 (생존편향)
    - 016 산출물: app.market_data.repositories (get_universe_at_date / get_price_range)
    - 018 산출물: app.market_data.local_csv (테스트 fixture 적재)

본 모듈의 책임:
    1. `repositories.get_universe_at_date`로부터 시점별 활성 종목 받음 (016 — 동적 listing/delisting 필터 이미 적용)
    2. 06번 §8 공통 필터 적용 (exclude_etf / etn / spac / preferred / managed / halted +
       min_market_cap + min_avg_trading_value)
    3. 06번 §9 selection_method 적용 (본 step은 ALL 완전 + MARKET_CAP_TOP_N / LIQUIDITY_TOP_N 부분)

본 모듈의 비책임 (다른 step에서 처리):
    - 외부 fetch (Phase 11 — pykrx collector)
    - corporate_actions / market_indices / universe_history 영속화 (Phase 11)
    - 신호 평가 / 백테스트 실행 (BacktestEngine 영역)

look-ahead bias 차단 정책 (13.15):
    - 시가총액 필터: `daily_prices.date <= as_of_date`만 사용 (as_of_date의 종가 마감 후
      시점에 universe를 재선정하므로 as_of_date 포함은 허용. 미래 데이터 금지).
    - 거래대금 평균 N일: 13.15 체크리스트에 "거래량/거래대금 평균이 전일까지의 데이터인가?"가
      명시되어 있어 **as_of_date 직전 N일(당일 미포함)**을 사용.
    - listing_date / delisting_date: 016 `get_universe_at_date`가 이미
      `listing_date <= as_of_date AND (delisting_date IS NULL OR delisting_date > as_of_date)` 적용.

결손 처리 정책:
    - market_cap 결손 (None / NaN) 시 해당 종목을 필터에서 제외 (보수).
    - 거래대금 평균 N일 중 결손 봉(daily_prices에 row 없음)이 있으면 그 일수만큼 N에서 제외
      후 평균 계산 (단 최소 1건 이상 거래대금이 있어야 함, 0건이면 종목 제외).
    - forward-fill 금지 (14.10).

결정론 (13.12 / CLAUDE.md #8):
    - 모든 list 반환은 (symbol ASC) tie-breaker.
    - selection_method에서 정렬 시 (-metric, symbol ASC) 명시 tie-breaker.

selection_method 구현 상태 (06번 §9):
    - `ALL` (default): 완전 구현 — 필터 통과한 모든 종목.
    - `MARKET_CAP_TOP_N`: 부분 구현 — 016 daily_prices.market_cap 시계열만으로 동작
      (Phase 11 시가총액 정합성 검증 후 완전화 가능).
    - `LIQUIDITY_TOP_N`: 부분 구현 — close × volume 평균 N일.
    - `MANUAL` / `WATCHLIST`: 본 step 범위 밖 (06번 §8의 "모든 선택 결과에 공통 필터 적용"
      원칙은 동일하지만 입력 종목 리스트 출처가 universe_config.symbols라 별도 분기 필요 —
      Phase 10 GUI 작업 시 자연스럽게 추가될 것).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.market_data import repositories
from app.models.daily_price import DailyPrice
from app.models.symbol import Symbol

# 06번 §9 지원 selection_method
SELECTION_METHOD_ALL = "ALL"
SELECTION_METHOD_MARKET_CAP_TOP_N = "MARKET_CAP_TOP_N"
SELECTION_METHOD_LIQUIDITY_TOP_N = "LIQUIDITY_TOP_N"

SUPPORTED_SELECTION_METHODS: frozenset[str] = frozenset(
    {
        SELECTION_METHOD_ALL,
        SELECTION_METHOD_MARKET_CAP_TOP_N,
        SELECTION_METHOD_LIQUIDITY_TOP_N,
    }
)

# 06번 §8 공통 필터 — config 키 기본값.
# True면 해당 종류 종목 제외, False면 포함.
DEFAULT_EXCLUDE_FLAGS: dict[str, bool] = {
    "exclude_etf": True,
    "exclude_etn": True,
    "exclude_spac": True,
    "exclude_preferred": True,
    "exclude_managed": True,
    "exclude_halted": True,
}


@dataclass(frozen=True)
class UniverseSelectionResult:
    """UniverseSelector.select 결과 (디버깅 / 영향분석 / 결과화면 표시용).

    `symbols`는 필터 + selection_method 모두 통과한 최종 종목 리스트 (symbol ASC).
    `excluded_counts`는 각 단계에서 제외된 건수 — 06번 §11.2 영향 분석 표시에 활용.
    """

    symbols: list[Symbol]
    excluded_counts: dict[str, int]
    as_of_date: date_type
    market: str
    selection_method: str

    @property
    def count(self) -> int:
        return len(self.symbols)


class UniverseSelector:
    """시점별 유니버스 선정기.

    Args:
        session: SQLAlchemy Session (read-only 사용).

    사용 예시:
        selector = UniverseSelector(session)
        symbols = selector.select(
            config={
                "market": "KOSPI",
                "selection_method": "ALL",
                "exclude_etf": True,
                "min_market_cap": 100_000_000_000,
                "min_avg_trading_value": 1_000_000_000,
                "avg_trading_value_window_days": 20,
            },
            as_of_date=date(2024, 1, 8),
        )
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def select(
        self,
        config: dict[str, Any],
        as_of_date: date_type,
    ) -> list[Symbol]:
        """공통 필터 + selection_method를 적용한 종목 리스트.

        디버깅 / 영향분석 정보가 필요하면 `select_with_details`를 사용한다.

        Returns:
            Symbol 리스트 — symbol ASC.
        """
        return self.select_with_details(config, as_of_date).symbols

    def select_with_details(
        self,
        config: dict[str, Any],
        as_of_date: date_type,
    ) -> UniverseSelectionResult:
        """공통 필터 + selection_method 적용. 단계별 제외 카운트 포함."""
        market = self._require_market(config)
        method = config.get("selection_method", SELECTION_METHOD_ALL)
        if method not in SUPPORTED_SELECTION_METHODS:
            raise ValueError(
                f"지원하지 않는 selection_method: {method!r}. "
                f"사용 가능: {sorted(SUPPORTED_SELECTION_METHODS)}"
            )

        excluded: dict[str, int] = {}

        # 1) 016: 동적 listing/delisting 필터 적용된 활성 종목 (13.13 / 13.15)
        active_symbols = repositories.get_universe_at_date(
            self.session, market=market, as_of_date=as_of_date
        )

        # 2) 06번 §8 공통 필터 — 종목 마스터 플래그
        flag_filtered, flag_excluded = self._apply_flag_filters(active_symbols, config)
        excluded.update(flag_excluded)

        # 3) 06번 §8 공통 필터 — 시가총액 (look-ahead: as_of_date 이전 + 당일 포함)
        market_cap_filtered, mc_excluded = self._apply_min_market_cap(
            flag_filtered, config, as_of_date
        )
        excluded["min_market_cap"] = mc_excluded

        # 4) 06번 §8 공통 필터 — 거래대금 평균 N일 (look-ahead: 당일 미포함)
        liquidity_filtered, liq_excluded = self._apply_min_avg_trading_value(
            market_cap_filtered, config, as_of_date
        )
        excluded["min_avg_trading_value"] = liq_excluded

        # 5) 06번 §9 selection_method
        selected = self._apply_selection_method(
            liquidity_filtered, config, as_of_date, method
        )
        excluded["selection_method"] = len(liquidity_filtered) - len(selected)

        # 결정론 보장 (이미 정렬되어 있어야 하지만 한 번 더 강제)
        selected_sorted = sorted(selected, key=lambda s: s.symbol)

        return UniverseSelectionResult(
            symbols=selected_sorted,
            excluded_counts=excluded,
            as_of_date=as_of_date,
            market=market,
            selection_method=method,
        )

    # ------------------------------------------------------------------
    # 내부 — 단계별 필터
    # ------------------------------------------------------------------

    @staticmethod
    def _require_market(config: dict[str, Any]) -> str:
        market = config.get("market")
        if not market:
            raise ValueError("UniverseSelector config에 'market' 키가 필요합니다.")
        return str(market)

    @staticmethod
    def _apply_flag_filters(
        symbols: list[Symbol],
        config: dict[str, Any],
    ) -> tuple[list[Symbol], dict[str, int]]:
        """06번 §8 종목 마스터 플래그 기반 제외.

        config의 exclude_* 키가 명시되지 않으면 DEFAULT_EXCLUDE_FLAGS 사용.
        결정론: 입력 순서 유지 (호출 측이 이미 symbol ASC).
        """
        excluded_counts: dict[str, int] = {}
        result: list[Symbol] = []

        # 적용할 플래그 목록
        # 키 → Symbol attribute 매핑
        flag_map = {
            "exclude_etf": "is_etf",
            "exclude_etn": "is_etn",
            "exclude_spac": "is_spac",
            "exclude_preferred": "is_preferred",
            "exclude_managed": "is_managed",
            "exclude_halted": "is_halted",
        }

        # 효과적 설정 (default + override)
        effective: dict[str, bool] = {**DEFAULT_EXCLUDE_FLAGS}
        for key in flag_map:
            if key in config:
                effective[key] = bool(config[key])

        for key in flag_map:
            excluded_counts[key] = 0

        for sym in symbols:
            keep = True
            for key, attr in flag_map.items():
                if effective[key] and bool(getattr(sym, attr)):
                    excluded_counts[key] += 1
                    keep = False
                    # 첫 번째 매칭만 카운트 (중복 카운트 방지)
                    break
            if keep:
                result.append(sym)

        return result, excluded_counts

    def _apply_min_market_cap(
        self,
        symbols: list[Symbol],
        config: dict[str, Any],
        as_of_date: date_type,
    ) -> tuple[list[Symbol], int]:
        """시가총액 하한 필터 (06번 §8, 06번 §12).

        시가총액 시점 정책 (13.15):
            - 미래 데이터 금지 — `daily_prices.date <= as_of_date`.
            - as_of_date의 종가가 확정된 이후 universe를 재선정한다고 간주
              (as_of_date 당일 데이터 사용 허용 — look-ahead 아님).
            - 결손 시 해당 종목 제외 (보수).

        값을 가져오는 방식:
            - 가장 최근 `daily_prices.date <= as_of_date`의 `market_cap`을 사용.
            - 결손이면 None — 필터에서 제외.
        """
        threshold = config.get("min_market_cap")
        if threshold is None:
            return symbols, 0

        threshold_value = float(threshold)
        excluded = 0
        result: list[Symbol] = []

        for sym in symbols:
            mc = self._get_latest_market_cap(sym.symbol, as_of_date)
            if mc is None or mc < threshold_value:
                excluded += 1
                continue
            result.append(sym)

        return result, excluded

    def _apply_min_avg_trading_value(
        self,
        symbols: list[Symbol],
        config: dict[str, Any],
        as_of_date: date_type,
    ) -> tuple[list[Symbol], int]:
        """거래대금 평균 N일 하한 필터 (06번 §8, 06번 §12, 13.15).

        13.15 체크리스트: "거래량/거래대금 평균이 전일까지의 데이터인가?"
            - 거래대금 평균 N일은 **as_of_date 직전 N일 (당일 미포함)**.
            - 거래대금 = `close × volume` (06번 §7 정의 — 13.7과 정합).

        결손 처리:
            - 평균 계산은 실제 존재하는 봉만으로 (forward-fill 금지).
            - 0건이면 종목 제외.
        """
        threshold = config.get("min_avg_trading_value")
        if threshold is None:
            return symbols, 0

        window_days = int(config.get("avg_trading_value_window_days", 20))
        if window_days < 1:
            raise ValueError(
                f"avg_trading_value_window_days는 1 이상이어야 합니다 (입력={window_days})"
            )

        threshold_value = float(threshold)
        excluded = 0
        result: list[Symbol] = []

        # as_of_date 직전 N일 — 당일 미포함이므로 end는 as_of_date - 1.
        # window_days가 N "거래일"이어야 하지만 trading_calendar 의존을 줄이기 위해
        # 달력일 기준으로 충분히 큰 window를 잡고 실제 존재하는 봉만 평균에 포함.
        # (N "달력일" 안에 있는 거래일이 N보다 적을 수 있지만, 정책상 사용 가능한
        #  데이터로 평균 — 최소 1건만 있으면 OK)
        end_inclusive = as_of_date - timedelta(days=1)
        # 거래일 비율 ~5/7 + 안전 마진. window_days * 2 정도면 평일/공휴일 포함 N 거래일 충분.
        # 단, 너무 넓으면 의미가 흐려져 max(window_days * 2, window_days + 14) 정도.
        lookback_calendar_days = max(window_days * 2, window_days + 14)
        start_inclusive = end_inclusive - timedelta(days=lookback_calendar_days - 1)

        for sym in symbols:
            avg = self._compute_avg_trading_value(
                sym.symbol,
                start_date=start_inclusive,
                end_date=end_inclusive,
                window_days=window_days,
            )
            if avg is None or avg < threshold_value:
                excluded += 1
                continue
            result.append(sym)

        return result, excluded

    def _apply_selection_method(
        self,
        symbols: list[Symbol],
        config: dict[str, Any],
        as_of_date: date_type,
        method: str,
    ) -> list[Symbol]:
        """06번 §9 selection_method 적용.

        - ALL: 입력 그대로 (이미 공통 필터 통과).
        - MARKET_CAP_TOP_N: 시가총액(`as_of_date` 직전 또는 당일) 상위 N. tie-breaker symbol ASC.
        - LIQUIDITY_TOP_N: 거래대금 평균 N일 상위 N. tie-breaker symbol ASC.

        결정론: 정렬 키 항상 명시 (-metric, symbol ASC).
        """
        if method == SELECTION_METHOD_ALL:
            return list(symbols)

        top_n = config.get("top_n")
        if top_n is None:
            raise ValueError(
                f"selection_method={method}는 'top_n' 키가 필요합니다."
            )
        top_n_int = int(top_n)
        if top_n_int < 1:
            raise ValueError(f"top_n은 1 이상이어야 합니다 (입력={top_n_int})")

        if method == SELECTION_METHOD_MARKET_CAP_TOP_N:
            scored: list[tuple[float, str, Symbol]] = []
            for sym in symbols:
                mc = self._get_latest_market_cap(sym.symbol, as_of_date)
                if mc is None:
                    # 시가총액 결손은 정렬 대상에서 제외 (선정 불가)
                    continue
                scored.append((float(mc), sym.symbol, sym))
            # (-mc, symbol ASC)로 정렬 — 결정론
            scored.sort(key=lambda item: (-item[0], item[1]))
            return [item[2] for item in scored[:top_n_int]]

        if method == SELECTION_METHOD_LIQUIDITY_TOP_N:
            window_days = int(config.get("avg_trading_value_window_days", 20))
            if window_days < 1:
                raise ValueError(
                    f"avg_trading_value_window_days는 1 이상이어야 합니다 (입력={window_days})"
                )
            end_inclusive = as_of_date - timedelta(days=1)
            lookback_calendar_days = max(window_days * 2, window_days + 14)
            start_inclusive = end_inclusive - timedelta(
                days=lookback_calendar_days - 1
            )
            scored = []
            for sym in symbols:
                avg = self._compute_avg_trading_value(
                    sym.symbol,
                    start_date=start_inclusive,
                    end_date=end_inclusive,
                    window_days=window_days,
                )
                if avg is None:
                    continue
                scored.append((float(avg), sym.symbol, sym))
            scored.sort(key=lambda item: (-item[0], item[1]))
            return [item[2] for item in scored[:top_n_int]]

        raise NotImplementedError(
            f"selection_method={method}는 본 step에서 구현되지 않았습니다."
        )

    # ------------------------------------------------------------------
    # 데이터 조회 헬퍼
    # ------------------------------------------------------------------

    def _get_latest_market_cap(
        self,
        symbol: str,
        as_of_date: date_type,
    ) -> float | None:
        """as_of_date 이전(당일 포함) 가장 최근 daily_prices.market_cap.

        13.15: `date <= as_of_date`만 조회 — 미래 데이터 금지.
        결손(market_cap IS NULL) 또는 데이터 없음 시 None.
        """
        stmt = (
            select(DailyPrice.market_cap)
            .where(
                and_(
                    DailyPrice.symbol == symbol,
                    DailyPrice.date <= as_of_date,
                    DailyPrice.market_cap.is_not(None),
                )
            )
            .order_by(DailyPrice.date.desc())
            .limit(1)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result is None:
            return None
        return float(result)

    def _compute_avg_trading_value(
        self,
        symbol: str,
        start_date: date_type,
        end_date: date_type,
        window_days: int,
    ) -> float | None:
        """`close × volume`의 평균. 13.7: 거래대금 필터는 원 가격 기준.

        14.10 결손: 결손 봉(daily_prices에 row 없음)은 평균에서 제외.
        실제로 가져온 봉 중 가장 최근 `window_days`건만 사용 (lookback 범위 안에서).
        0건이면 None 반환 → 종목 제외.
        """
        rows = repositories.get_price_range(
            self.session,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if not rows:
            return None

        # date ASC로 정렬되어 있음 (016 보장). 가장 최근 window_days건만 사용.
        recent = rows[-window_days:] if len(rows) > window_days else rows

        # close × volume 평균
        values = [float(r.close) * float(r.volume) for r in recent]
        if not values:
            return None
        return sum(values) / len(values)


__all__ = [
    "UniverseSelector",
    "UniverseSelectionResult",
    "SELECTION_METHOD_ALL",
    "SELECTION_METHOD_MARKET_CAP_TOP_N",
    "SELECTION_METHOD_LIQUIDITY_TOP_N",
    "SUPPORTED_SELECTION_METHODS",
    "DEFAULT_EXCLUDE_FLAGS",
]
