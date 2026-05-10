"""AdjustedPriceProcessor — corporate_actions 기반 수정주가 재계산 (14번 §9 / 13번 §7).

본 프로세서는 025 PykrxCollector가 수집한 `RawDailyPricesData` (이미 1차 adj_*가 채워진
상태) 와 026 corporate_actions를 받아 정책에 따른 정밀한 수정주가를 재계산한다.

설계 결정 (인계 정보 — 027 MarketCapProcessor 참고):

    1. **frozen dataclass 입력** (`AdjustedPriceInput`)
        - prices: RawDailyPricesData (collector 출력 그대로)
        - corporate_actions: tuple[CorporateActionEvent, ...] — DB 모델이 아닌
          frozen dataclass로 감싸 processor의 외부 의존을 끊는다
        - as_of_date: look-ahead 차단 — 본 일자 이후 발생 이벤트는 무시
            (None이면 prices.end_date 사용)

    2. **출력은 tuple[RawDailyPriceRow, ...]** (입력과 동일 타입)
        - 호출자가 그대로 repositories.bulk_upsert_daily_prices에 전달 가능
        - close (원 가격) / volume (원 거래량) 은 변경 안 함
        - adj_open / adj_high / adj_low / adj_close / adj_volume 만 재계산

    3. **시간 역순 적용** (14.9.1)
        - corporate_actions를 (event_date DESC, event_type ASC) 정렬
        - event_date *이전* 가격에 누적 factor 적용
        - 결정론: dict 순회 의존 0건

    4. **이벤트 타입별 처리** (14.9.1, 13.7):

        a) `split` (액면분할 1주 → ratio주):
            adj_factor *= 1.0 / ratio
            adj_volume *= ratio
            예: 1:2 분할 → ratio=2.0, 분할 이전 가격 × 0.5, 거래량 × 2

        b) `reverse_split` (액면병합 ratio주 → 1주):
            adj_factor *= ratio
            adj_volume *= 1.0 / ratio

        c) `bonus_issue` (무상증자, 보유 1주당 ratio주 추가):
            adj_factor *= 1.0 / (1.0 + ratio)
            adj_volume *= (1.0 + ratio)

        d) `cash_dividend` (현금 배당, 주당 dividend_amount):
            14.9.1 공식: adj_factor *= (1 - dividend / price_before)
            price_before는 권리락 직전 종가(=event_date 직전 거래일 close).
            본 step에서는 입력 prices에서 event_date 직전 close를 자동 검색.
            검색 실패 시 ValidationIssue 누적 + 해당 이벤트 skip (가격 변형 0).

        e) `rights_issue` (유상증자):
            본 step에서는 단순화 — ValidationIssue 누적 + skip.
            14.9.1의 "이론권리락 가격 기준 보정"은 028 이후 정밀화.

        f) `merger` / `spinoff`:
            본 step에서는 단순화 — ValidationIssue 누적 + skip.

        g) `delisting`:
            가격 영향 없음 (symbols.delisting_date가 단일 출처). skip.

    5. **검증** (14번 §7):
        - 음수 ratio → HARD (DataValidationError raise)
        - 미래 이벤트 (event_date > as_of_date) → SOFT (skip + 경고)
        - cash_dividend에 dividend_amount 누락 → HARD
        - cash_dividend의 price_before 검색 실패 → SOFT (skip)
        - 미지원 이벤트 (rights/merger/spinoff) → SOFT (skip)

    6. **결정론**:
        - corporate_actions 정렬: (event_date DESC, event_type ASC)
        - 출력 prices: BaseCollector._to_sorted_price_tuple와 동일 (symbol ASC, date ASC)
        - dict 순회 0건 (오로지 sorted/list)

    7. **외부 fetch / DB 미터치**: pure function 성격. 테스트는 in-memory dataclass로만.

13.7 / 14.9 정합성:
    - close (원 가격) 보존 — 가격 조건은 adj_*만 사용, 거래대금 필터만 close × volume
    - 분할/배당 발생 시 과거 *전체* 재계산 (14.9 — 스냅샷 누적 금지)
    - 본 프로세서가 매번 호출되면 동일 입력 동일 출력 (idempotent)

027 인계:
    - 본 프로세서가 출력한 `tuple[RawDailyPriceRow, ...]`를
      `repositories.bulk_upsert_daily_prices`에 전달하면 daily_prices의 adj_*가 갱신됨
    - 027 jobs는 (a) corporate_actions 신규 수집 → (b) AdjustedPriceProcessor.process() →
      (c) bulk_upsert_daily_prices 흐름을 잡으로 묶을 예정
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type

from app.data_pipeline.collectors.base import RawDailyPriceRow, RawDailyPricesData
from app.data_pipeline.exceptions import DataValidationError
from app.data_pipeline.processors.base import (
    BaseProcessor,
    ProcessedResult,
    ValidationIssue,
    ValidationResult,
)

# 본 프로세서 식별자
PROCESSOR_NAME = "adjusted_price"

# event_type별 처리 정책 (본 step에서 지원하는 종류)
SUPPORTED_FACTOR_EVENTS: tuple[str, ...] = (
    "split",
    "reverse_split",
    "bonus_issue",
    "cash_dividend",
)
# 본 step에서 단순화 (skip + 경고) 처리하는 종류 — 028 이후 정밀화
SIMPLIFIED_EVENTS: tuple[str, ...] = (
    "rights_issue",
    "merger",
    "spinoff",
)
# 가격 영향 없음 (참고용)
NO_PRICE_IMPACT_EVENTS: tuple[str, ...] = ("delisting",)


# ---------------------------------------------------------------------------
# 입력 dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorporateActionEvent:
    """AdjustedPriceProcessor 입력용 corporate_action 단일 이벤트.

    DB 모델(`app.models.corporate_action.CorporateAction`)과 분리한 이유:
        - processor는 외부 의존(SQLAlchemy ORM)을 직접 import하지 않음 → 테스트 용이성
        - 호출자(jobs)가 ORM → dataclass 변환 책임 (간단한 list comprehension)

    Attributes:
        symbol: 6자리 종목코드.
        event_date: 권리락 발생일.
        event_type: 14번 §15 enum.
        ratio: split/reverse_split/bonus_issue 비율. cash_dividend는 사용 안 함.
        dividend_amount: cash_dividend 주당 배당금. 그 외 None.
    """

    symbol: str
    event_date: date_type
    event_type: str
    ratio: float = 0.0
    dividend_amount: float | None = None


@dataclass(frozen=True)
class AdjustedPriceInput:
    """AdjustedPriceProcessor 입력 묶음.

    Attributes:
        prices: 025 collector가 수집한 일봉 (이미 1차 adj_*가 채워진 상태).
            본 프로세서는 prices.rows의 adj_*를 corporate_actions로 재계산.
        corporate_actions: 영향 종목들의 corporate_action 이벤트.
            여러 종목/여러 이벤트 혼재 가능. 처리 시 종목별로 그룹핑.
        as_of_date: look-ahead 차단 기준일. 본 일자 이후 event_date는 무시.
            None이면 prices.end_date 사용.
    """

    prices: RawDailyPricesData
    corporate_actions: tuple[CorporateActionEvent, ...] = field(default_factory=tuple)
    as_of_date: date_type | None = None


# ---------------------------------------------------------------------------
# AdjustedPriceProcessor
# ---------------------------------------------------------------------------


class AdjustedPriceProcessor(
    BaseProcessor[AdjustedPriceInput, tuple[RawDailyPriceRow, ...]]
):
    """corporate_actions 기반 수정주가 재계산 프로세서 (14번 §9, 13번 §7).

    `process(input_data)` 진입점이 모든 처리를 수행한다.

    Subclass / 호출자 사용 예 (jobs 가설):

        events = [
            CorporateActionEvent(symbol="005930", event_date=date(2024,5,1),
                                 event_type="split", ratio=2.0),
        ]
        proc = AdjustedPriceProcessor()
        result = proc.process(AdjustedPriceInput(prices=raw_prices,
                                                  corporate_actions=tuple(events)))
        # result.output: tuple[RawDailyPriceRow, ...] — adj_*만 재계산된 신규 row
        # result.validation.issues: skip된 이벤트 / 검증 위배
        # result.stats: ("rows_processed", N), ("events_applied", M) 등

    Args:
        name: 프로세서 식별자 (기본 "adjusted_price").
        raise_on_hard_fail: True면 hard_fail 검증 시 DataValidationError raise.
            기본 True (정책 위반은 즉시 차단). False면 issues에만 누적.
    """

    def __init__(
        self,
        name: str = PROCESSOR_NAME,
        *,
        raise_on_hard_fail: bool = True,
    ) -> None:
        super().__init__(name)
        self._raise_on_hard_fail = raise_on_hard_fail

    # ------------------------------------------------------------------
    # process 진입점
    # ------------------------------------------------------------------

    def process(
        self, input_data: AdjustedPriceInput
    ) -> ProcessedResult[tuple[RawDailyPriceRow, ...]]:
        """수정주가 재계산.

        흐름:
            1. as_of_date 결정 (None이면 prices.end_date)
            2. corporate_actions를 종목별로 그룹핑 + 시간 역순 정렬
               (event_date DESC, event_type ASC)
            3. 종목별 prices.rows를 (date ASC) 정렬해 처리
            4. 각 이벤트를 시간 역순으로 적용:
               - 정책 위배 → ValidationIssue 누적 (HARD/SOFT)
               - 적용 가능 → event_date *이전* row의 adj_* / adj_volume에 factor 적용
            5. 결과 row를 (symbol ASC, date ASC) 정렬해 반환

        검증:
            - 음수/0 ratio (split/reverse_split/bonus_issue) → HARD
            - cash_dividend에 dividend_amount 누락 → HARD
            - 미래 이벤트 (event_date > as_of_date) → SOFT (skip)
            - cash_dividend price_before 결손 → SOFT (skip)
            - 미지원 이벤트 → SOFT (skip)

        Returns:
            ProcessedResult[tuple[RawDailyPriceRow, ...]] —
                output: 재계산된 row 튜플 (입력과 동일 길이, symbol/date/원가격/원거래량 보존)
                validation: 검증 결과
                stats: 처리량 통계
                warnings: 비치명적 경고

        Raises:
            DataValidationError: hard_fail이 발생하고 raise_on_hard_fail=True인 경우.
        """
        as_of_date = (
            input_data.as_of_date
            if input_data.as_of_date is not None
            else input_data.prices.end_date
        )

        issues: list[ValidationIssue] = []
        warnings: list[str] = []
        stats = {
            "rows_processed": 0,
            "events_total": len(input_data.corporate_actions),
            "events_applied": 0,
            "events_skipped_future": 0,
            "events_skipped_unsupported": 0,
            "events_skipped_invalid": 0,
            "events_skipped_missing_price": 0,
        }

        # 종목별로 prices/events 그룹핑 (결정론: 정렬된 시퀀스만 사용)
        # prices.rows는 이미 (symbol ASC, date ASC) 정렬되어 있다고 가정 (collector 정책)
        prices_by_symbol: dict[str, list[RawDailyPriceRow]] = {}
        for row in input_data.prices.rows:
            prices_by_symbol.setdefault(row.symbol, []).append(row)

        events_by_symbol: dict[str, list[CorporateActionEvent]] = {}
        for ev in input_data.corporate_actions:
            events_by_symbol.setdefault(ev.symbol, []).append(ev)

        # 결정론: 종목 처리 순서를 sorted(symbol ASC)로 강제 — dict 순회 의존 차단
        all_symbols = sorted(set(prices_by_symbol.keys()) | set(events_by_symbol.keys()))

        adjusted_rows: list[RawDailyPriceRow] = []

        for symbol in all_symbols:
            symbol_prices = prices_by_symbol.get(symbol, [])
            symbol_events = events_by_symbol.get(symbol, [])

            # corporate_actions가 없는 종목은 입력 그대로 통과 (close 보존, adj_*도 그대로)
            if not symbol_events:
                adjusted_rows.extend(symbol_prices)
                stats["rows_processed"] += len(symbol_prices)
                continue

            # 시간 역순 적용 (14.9.1) — event_date DESC, event_type ASC tie-breaker (결정론)
            sorted_events = sorted(
                symbol_events, key=lambda e: (e.event_date, e.event_type), reverse=False
            )
            # reverse=False로 ASC 정렬 후 reversed() — event_date 동일 시 event_type ASC tie-breaker 유지
            # 실제 적용은 시간 역순이므로 reversed iteration

            # 가격 row를 date ASC로 정렬 (결정론 보장)
            sorted_prices = sorted(symbol_prices, key=lambda r: r.date)

            # 종목별 누적 factor — adj_close/open/high/low에 곱하고, adj_volume에는 역수 곱
            # row index 별 (price_factor, volume_factor) 누적
            n = len(sorted_prices)
            price_factors = [1.0] * n
            volume_factors = [1.0] * n

            for ev in reversed(sorted_events):
                # look-ahead 차단 — 미래 이벤트 무시
                if ev.event_date > as_of_date:
                    issues.append(
                        ValidationIssue(
                            severity="soft_fail",
                            code="CORP_ACTION_FUTURE",
                            message=(
                                f"미래 corporate_action 무시 (look-ahead 차단): "
                                f"symbol={symbol} event_date={ev.event_date.isoformat()} "
                                f"as_of_date={as_of_date.isoformat()}"
                            ),
                            context=BaseProcessor._context_to_tuple(
                                {
                                    "symbol": symbol,
                                    "event_date": ev.event_date.isoformat(),
                                    "event_type": ev.event_type,
                                    "as_of_date": as_of_date.isoformat(),
                                }
                            ),
                        )
                    )
                    stats["events_skipped_future"] += 1
                    continue

                # 미지원 이벤트 (단순화 처리)
                if ev.event_type in SIMPLIFIED_EVENTS:
                    issues.append(
                        ValidationIssue(
                            severity="soft_fail",
                            code="CORP_ACTION_UNSUPPORTED",
                            message=(
                                f"이벤트 타입 단순화 처리 (가격 보정 없음, 028 이후 정밀화): "
                                f"symbol={symbol} type={ev.event_type}"
                            ),
                            context=BaseProcessor._context_to_tuple(
                                {
                                    "symbol": symbol,
                                    "event_date": ev.event_date.isoformat(),
                                    "event_type": ev.event_type,
                                }
                            ),
                        )
                    )
                    stats["events_skipped_unsupported"] += 1
                    continue

                # 가격 영향 없음
                if ev.event_type in NO_PRICE_IMPACT_EVENTS:
                    continue

                if ev.event_type not in SUPPORTED_FACTOR_EVENTS:
                    # 알 수 없는 이벤트 — 보수적으로 skip + soft
                    issues.append(
                        ValidationIssue(
                            severity="soft_fail",
                            code="CORP_ACTION_UNKNOWN_TYPE",
                            message=(
                                f"알 수 없는 event_type 무시: symbol={symbol} type={ev.event_type}"
                            ),
                            context=BaseProcessor._context_to_tuple(
                                {
                                    "symbol": symbol,
                                    "event_type": ev.event_type,
                                }
                            ),
                        )
                    )
                    stats["events_skipped_unsupported"] += 1
                    continue

                # 이벤트 타입별 factor 계산
                price_mult, volume_mult, hard_issue = self._compute_factor(
                    symbol=symbol,
                    event=ev,
                    sorted_prices=sorted_prices,
                )
                if hard_issue is not None:
                    issues.append(hard_issue)
                    stats["events_skipped_invalid"] += 1
                    continue
                if price_mult is None or volume_mult is None:
                    # cash_dividend price_before 결손 등 — soft skip
                    issues.append(
                        ValidationIssue(
                            severity="soft_fail",
                            code="CORP_ACTION_MISSING_PRICE_BEFORE",
                            message=(
                                f"cash_dividend price_before 결손 — 이벤트 skip: "
                                f"symbol={symbol} event_date={ev.event_date.isoformat()}"
                            ),
                            context=BaseProcessor._context_to_tuple(
                                {
                                    "symbol": symbol,
                                    "event_date": ev.event_date.isoformat(),
                                }
                            ),
                        )
                    )
                    stats["events_skipped_missing_price"] += 1
                    continue

                # event_date *이전* row에만 factor 적용 (event_date 당일은 이미 권리락 반영)
                for i, row in enumerate(sorted_prices):
                    if row.date < ev.event_date:
                        price_factors[i] *= price_mult
                        volume_factors[i] *= volume_mult
                stats["events_applied"] += 1

            # factor 적용 → 새 RawDailyPriceRow 생성 (frozen dataclass이므로 신규 생성)
            for i, row in enumerate(sorted_prices):
                pf = price_factors[i]
                vf = volume_factors[i]
                # close (원 가격) / volume (원 거래량) 은 보존
                # adj_*는 입력 adj_*에 factor 적용 (입력의 1차 adj_*가 이미 정확하면 factor=1.0이라 무변화)
                # 본 step 정책: 입력 adj_*는 collector가 채운 raw 그대로 (즉 close == adj_close인 경우 많음)
                # corporate_action을 적용해 *역산*하므로, 입력 adj_*에 factor를 곱하면 정확한 과거값
                adjusted_rows.append(
                    RawDailyPriceRow(
                        symbol=row.symbol,
                        date=row.date,
                        open=row.open,
                        high=row.high,
                        low=row.low,
                        close=row.close,
                        volume=row.volume,
                        adj_open=row.adj_open * pf,
                        adj_high=row.adj_high * pf,
                        adj_low=row.adj_low * pf,
                        adj_close=row.adj_close * pf,
                        adj_volume=row.adj_volume * vf,
                        market_cap=row.market_cap,
                    )
                )
                stats["rows_processed"] += 1

        # 결과 정렬 (symbol ASC, date ASC) — collector와 동일 결정론
        adjusted_rows.sort(key=lambda r: (r.symbol, r.date))

        # 검증 이슈 정렬 (code ASC, severity ASC) — base.py 정책
        sorted_issues = tuple(
            sorted(issues, key=lambda i: (i.code, i.severity))
        )
        hard_count = sum(1 for i in sorted_issues if i.severity == "hard_fail")
        validation = ValidationResult(
            issues=sorted_issues,
            passed=(hard_count == 0),
        )

        if hard_count > 0 and self._raise_on_hard_fail:
            raise DataValidationError(
                f"AdjustedPriceProcessor: hard_fail {hard_count}건 — 첫 메시지: "
                f"{sorted_issues[0].message}"
            )

        return ProcessedResult(
            output=tuple(adjusted_rows),
            validation=validation,
            stats=BaseProcessor._stats_to_tuple(stats),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # 내부 helper — 이벤트 타입별 factor 계산
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_factor(
        symbol: str,
        event: CorporateActionEvent,
        sorted_prices: list[RawDailyPriceRow],
    ) -> tuple[float | None, float | None, ValidationIssue | None]:
        """이벤트 1건에 대한 (price_factor, volume_factor, hard_issue) 계산.

        반환:
            (price_mult, volume_mult, None) — 정상 계산
            (None, None, ValidationIssue(hard_fail)) — 검증 위배 (HARD)
            (None, None, None) — soft skip (price_before 결손 등 — 호출부에서 별도 처리)

        14.9.1 공식:
            split (1주 → ratio주):
                price *= 1/ratio, volume *= ratio
            reverse_split (ratio주 → 1주):
                price *= ratio, volume *= 1/ratio
            bonus_issue (보유 1주당 ratio주 추가):
                price *= 1/(1+ratio), volume *= (1+ratio)
            cash_dividend:
                price *= (1 - dividend / price_before)
                price_before = event_date 직전 거래일의 close
                volume_factor = 1.0 (배당은 거래량 영향 없음)
        """
        et = event.event_type

        if et == "split":
            if event.ratio <= 0:
                return None, None, ValidationIssue(
                    severity="hard_fail",
                    code="CORP_ACTION_INVALID_RATIO",
                    message=(
                        f"split ratio가 0 이하: symbol={symbol} ratio={event.ratio}"
                    ),
                    context=BaseProcessor._context_to_tuple(
                        {
                            "symbol": symbol,
                            "event_date": event.event_date.isoformat(),
                            "event_type": et,
                            "ratio": event.ratio,
                        }
                    ),
                )
            return 1.0 / event.ratio, event.ratio, None

        if et == "reverse_split":
            if event.ratio <= 0:
                return None, None, ValidationIssue(
                    severity="hard_fail",
                    code="CORP_ACTION_INVALID_RATIO",
                    message=(
                        f"reverse_split ratio가 0 이하: symbol={symbol} ratio={event.ratio}"
                    ),
                    context=BaseProcessor._context_to_tuple(
                        {
                            "symbol": symbol,
                            "event_date": event.event_date.isoformat(),
                            "event_type": et,
                            "ratio": event.ratio,
                        }
                    ),
                )
            return event.ratio, 1.0 / event.ratio, None

        if et == "bonus_issue":
            if event.ratio < 0:
                return None, None, ValidationIssue(
                    severity="hard_fail",
                    code="CORP_ACTION_INVALID_RATIO",
                    message=(
                        f"bonus_issue ratio가 음수: symbol={symbol} ratio={event.ratio}"
                    ),
                    context=BaseProcessor._context_to_tuple(
                        {
                            "symbol": symbol,
                            "event_date": event.event_date.isoformat(),
                            "event_type": et,
                            "ratio": event.ratio,
                        }
                    ),
                )
            return 1.0 / (1.0 + event.ratio), 1.0 + event.ratio, None

        if et == "cash_dividend":
            if event.dividend_amount is None or event.dividend_amount < 0:
                return None, None, ValidationIssue(
                    severity="hard_fail",
                    code="CORP_ACTION_INVALID_DIVIDEND",
                    message=(
                        f"cash_dividend dividend_amount 누락 또는 음수: symbol={symbol} "
                        f"amount={event.dividend_amount}"
                    ),
                    context=BaseProcessor._context_to_tuple(
                        {
                            "symbol": symbol,
                            "event_date": event.event_date.isoformat(),
                            "event_type": et,
                            "dividend_amount": event.dividend_amount,
                        }
                    ),
                )
            # event_date 직전 거래일의 close 검색 (sorted_prices에서)
            price_before: float | None = None
            for row in reversed(sorted_prices):
                if row.date < event.event_date:
                    price_before = row.close
                    break
            if price_before is None or price_before <= 0:
                # soft skip — None을 (None, None, None)으로 반환해 호출부에서 처리
                return None, None, None
            mult = 1.0 - (event.dividend_amount / price_before)
            if mult <= 0:
                return None, None, ValidationIssue(
                    severity="hard_fail",
                    code="CORP_ACTION_INVALID_DIVIDEND",
                    message=(
                        f"cash_dividend가 price_before 이상: symbol={symbol} "
                        f"dividend={event.dividend_amount} price_before={price_before}"
                    ),
                    context=BaseProcessor._context_to_tuple(
                        {
                            "symbol": symbol,
                            "event_date": event.event_date.isoformat(),
                            "dividend_amount": event.dividend_amount,
                            "price_before": price_before,
                        }
                    ),
                )
            return mult, 1.0, None

        # 도달하지 않음 (호출부에서 SUPPORTED_FACTOR_EVENTS 외는 이미 분기)
        return None, None, None


__all__ = [
    "AdjustedPriceProcessor",
    "AdjustedPriceInput",
    "CorporateActionEvent",
    "PROCESSOR_NAME",
    "SUPPORTED_FACTOR_EVENTS",
    "SIMPLIFIED_EVENTS",
    "NO_PRICE_IMPACT_EVENTS",
]
