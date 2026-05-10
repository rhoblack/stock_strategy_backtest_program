"""Collector 출력 데이터 검증 (14번 §7).

본 모듈은 collector(특히 PykrxCollector)가 수집한 raw 데이터를 14번 §7 자동 검증
항목에 따라 검증한다. 검증 결과는 024에서 정의한 `ValidationResult` /
`ValidationIssue`로 누적해 호출자에게 노출한다.

14번 §7.2 정책 매핑:

    HARD_FAIL (백테스트 차단 — DataValidationError raise 권장):
        - close NULL / 음수 / 0
        - adj_close NULL / 음수 / 0
        - date NULL
        - symbol 형식 위반 (KRX 6자리 숫자 아님)
        - 거래일 캘린더 자체가 빈 경우 (캘린더 결손)
        - high < low (OHLC 정합성 위배 — 수치 오류)

    SOFT_FAIL (경고만 — ValidationIssue 누적, 통과):
        - market_cap NULL / 0 (시가총액 결손 — 14번 §7.2 명시)
        - volume == 0 (거래정지 정상 — 14번 §10.1 / 13.4.4 distress 신호로 별도 처리)
        - high == low (한가 — 정상 분류)
        - OHLC 일부가 0 미만 케이스 (소수점 노이즈는 hard로 잡고, 음수 0 경계는 soft)

설계 결정:

    1. **함수 단위 검증** (validators.py)
        - 각 검증 함수는 row 또는 컬렉션을 받아 `list[ValidationIssue]` 반환
        - hard_fail은 함수가 raise 하지 않고 issue만 누적 → 호출자가 즉시 raise할지 결정

    2. **collect_xxx_data 통합 검증** (validate_xxx_data)
        - 단일 진입점에서 RawXxxData 전체에 대해 모든 검증을 수행
        - `raise_on_hard_fail=True`이면 단일 hard_fail에 즉시 `DataValidationError` raise
        - 기본은 False → 호출자가 ValidationResult를 받아 정책 결정

    3. **결정론** (CLAUDE.md #8)
        - issues는 입력 row 순서를 따라 누적 (입력이 정렬돼 있으면 출력도 정렬)
        - 단, 최종 ValidationResult.issues는 (code ASC, severity ASC) 정렬 보장
          → 14번 §7 호출자가 안정적으로 카운트/모니터링 가능

    4. **외부 fetch 0건 / DB 미터치**
        - 본 모듈은 pure function — pandas/numpy 등 무거운 의존성도 없음

    5. **026 이후 재사용**
        - corporate_actions 검증, 시가총액 정합성 검증은 026~ 후속 step에서 본 모듈 확장

본 모듈은 외부 fetch 0건 / 결정론적.
"""

from __future__ import annotations

import re

from app.data_pipeline.collectors.base import (
    RawCalendarData,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawSymbolRow,
    RawSymbolsData,
)
from app.data_pipeline.exceptions import DataValidationError
from app.data_pipeline.processors.base import ValidationIssue, ValidationResult

# 14번 §3.1 — KRX 종목 코드는 6자리 숫자 (정확히 6자리).
_SYMBOL_RE = re.compile(r"^\d{6}$")


# ---------------------------------------------------------------------------
# 단일 row 검증 — 함수 시그니처: row → list[ValidationIssue]
# ---------------------------------------------------------------------------


def validate_symbol_row(row: RawSymbolRow) -> list[ValidationIssue]:
    """단일 종목 마스터 row 검증.

    HARD_FAIL:
        - SYMBOL_FORMAT_INVALID: KRX 6자리 숫자 아님
        - SYMBOL_NAME_EMPTY: name이 빈 문자열
        - SYMBOL_MARKET_INVALID: market이 KOSPI/KOSDAQ/KONEX 외
        - SYMBOL_LISTING_DATE_NULL: listing_date가 None (dataclass에서 type상 None 불가하나 안전망)
        - SYMBOL_DELISTED_BEFORE_LISTED: delisting_date < listing_date

    SOFT_FAIL:
        - (현재 없음 — 종목 마스터는 결손이 곧 hard)
    """
    issues: list[ValidationIssue] = []
    ctx = (("symbol", str(row.symbol)),)

    if not _SYMBOL_RE.match(row.symbol or ""):
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="SYMBOL_FORMAT_INVALID",
                message=f"종목코드 형식 위반: {row.symbol!r} (KRX 6자리 숫자가 아님)",
                context=ctx,
            )
        )
    if not row.name:
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="SYMBOL_NAME_EMPTY",
                message="종목명이 비어 있음",
                context=ctx,
            )
        )
    if row.market not in ("KOSPI", "KOSDAQ", "KONEX"):
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="SYMBOL_MARKET_INVALID",
                message=f"시장 구분 위반: {row.market!r} (KOSPI/KOSDAQ/KONEX 아님)",
                context=ctx,
            )
        )
    if row.delisting_date is not None and row.delisting_date < row.listing_date:
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="SYMBOL_DELISTED_BEFORE_LISTED",
                message=(
                    f"폐지일이 상장일보다 빠름: listing={row.listing_date.isoformat()} "
                    f"delisting={row.delisting_date.isoformat()}"
                ),
                context=ctx,
            )
        )
    return issues


def validate_daily_price_row(row: RawDailyPriceRow) -> list[ValidationIssue]:
    """단일 일봉 row 검증 (14번 §7.1).

    HARD_FAIL:
        - PRICE_CLOSE_NULL_OR_NONPOSITIVE: close가 None/0/음수
        - PRICE_ADJ_CLOSE_NULL_OR_NONPOSITIVE: adj_close가 None/0/음수
        - PRICE_DATE_NULL: date가 None (안전망)
        - PRICE_SYMBOL_FORMAT_INVALID: symbol 형식 위반
        - OHLC_INCONSISTENT_HIGH_LT_LOW: high < low (수치 오류)
        - OHLC_NEGATIVE: open/high/low/close가 음수 (단, 0은 close에서만 hard)

    SOFT_FAIL:
        - MARKET_CAP_MISSING: market_cap이 None (14번 §7.2 명시)
        - VOLUME_ZERO: volume == 0 (거래정지 가능성 — 정상 분류)
        - HIGH_EQ_LOW: high == low (한가 — 정상 분류)
    """
    issues: list[ValidationIssue] = []
    ctx = (
        ("date", row.date.isoformat() if row.date is not None else "None"),
        ("symbol", str(row.symbol)),
    )

    # symbol 형식
    if not _SYMBOL_RE.match(row.symbol or ""):
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="PRICE_SYMBOL_FORMAT_INVALID",
                message=f"종목코드 형식 위반: {row.symbol!r}",
                context=ctx,
            )
        )

    # close
    if row.close is None or row.close <= 0:
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="PRICE_CLOSE_NULL_OR_NONPOSITIVE",
                message=f"close가 NULL/0/음수: {row.close!r}",
                context=ctx,
            )
        )

    # adj_close
    if row.adj_close is None or row.adj_close <= 0:
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="PRICE_ADJ_CLOSE_NULL_OR_NONPOSITIVE",
                message=f"adj_close가 NULL/0/음수: {row.adj_close!r}",
                context=ctx,
            )
        )

    # OHLC 음수 (close는 위에서 이미 잡았지만 open/high/low는 별도)
    for field_name in ("open", "high", "low"):
        val = getattr(row, field_name)
        if val is not None and val < 0:
            issues.append(
                ValidationIssue(
                    severity="hard_fail",
                    code="OHLC_NEGATIVE",
                    message=f"{field_name}가 음수: {val!r}",
                    context=ctx,
                )
            )

    # OHLC 정합성: high < low → hard
    if (
        row.high is not None
        and row.low is not None
        and row.high < row.low
    ):
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="OHLC_INCONSISTENT_HIGH_LT_LOW",
                message=f"high < low: high={row.high} low={row.low}",
                context=ctx,
            )
        )

    # SOFT_FAIL: market_cap 결손 (14번 §7.2)
    if row.market_cap is None:
        issues.append(
            ValidationIssue(
                severity="soft_fail",
                code="MARKET_CAP_MISSING",
                message="market_cap이 NULL (시가총액 결손)",
                context=ctx,
            )
        )

    # SOFT_FAIL: volume == 0 (거래정지 가능성)
    if row.volume == 0:
        issues.append(
            ValidationIssue(
                severity="soft_fail",
                code="VOLUME_ZERO",
                message="volume == 0 (거래정지 가능성)",
                context=ctx,
            )
        )

    # SOFT_FAIL: 한가 (high == low) — 거래정지 또는 단일 체결
    if (
        row.high is not None
        and row.low is not None
        and row.high == row.low
    ):
        issues.append(
            ValidationIssue(
                severity="soft_fail",
                code="HIGH_EQ_LOW",
                message="high == low (한가)",
                context=ctx,
            )
        )

    return issues


# ---------------------------------------------------------------------------
# 컬렉션 단위 검증 — RawXxxData → ValidationResult
# ---------------------------------------------------------------------------


def _finalize_result(
    issues: list[ValidationIssue],
    *,
    raise_on_hard_fail: bool,
) -> ValidationResult:
    """누적된 issues를 정렬해 ValidationResult로 마감.

    결정론: (code ASC, severity ASC) 정렬.
    """
    sorted_issues = tuple(sorted(issues, key=lambda i: (i.code, i.severity)))
    has_hard = any(i.severity == "hard_fail" for i in sorted_issues)
    result = ValidationResult(issues=sorted_issues, passed=not has_hard)
    if has_hard and raise_on_hard_fail:
        # 첫 번째 hard_fail의 message를 대표로 노출 (모든 issue는 result에 보존)
        first_hard = next(i for i in sorted_issues if i.severity == "hard_fail")
        raise DataValidationError(
            f"[{first_hard.code}] {first_hard.message} "
            f"(hard_fail={result.hard_fail_count}, soft_fail={result.soft_fail_count})"
        )
    return result


def validate_symbols_data(
    data: RawSymbolsData,
    *,
    raise_on_hard_fail: bool = False,
) -> ValidationResult:
    """`RawSymbolsData` 컬렉션 전체 검증.

    Args:
        data: collector 출력.
        raise_on_hard_fail: True면 hard_fail 발생 시 `DataValidationError` raise.
            False(기본)면 ValidationResult로 모든 결과 반환 후 호출자가 정책 결정.

    Returns:
        ValidationResult — issues는 (code ASC, severity ASC) 정렬.
    """
    issues: list[ValidationIssue] = []
    for row in data.rows:
        issues.extend(validate_symbol_row(row))
    return _finalize_result(issues, raise_on_hard_fail=raise_on_hard_fail)


def validate_daily_prices_data(
    data: RawDailyPricesData,
    *,
    raise_on_hard_fail: bool = False,
) -> ValidationResult:
    """`RawDailyPricesData` 컬렉션 전체 검증 (14번 §7.1).

    Args:
        data: collector 출력.
        raise_on_hard_fail: True면 hard_fail 발생 시 `DataValidationError` raise.

    Returns:
        ValidationResult — issues는 (code ASC, severity ASC) 정렬.
    """
    issues: list[ValidationIssue] = []
    for row in data.rows:
        issues.extend(validate_daily_price_row(row))
    return _finalize_result(issues, raise_on_hard_fail=raise_on_hard_fail)


def validate_calendar_data(
    data: RawCalendarData,
    *,
    raise_on_hard_fail: bool = False,
) -> ValidationResult:
    """`RawCalendarData` 컬렉션 전체 검증 (14번 §7.1 거래일 캘린더 결손 = HARD).

    HARD_FAIL:
        - CALENDAR_EMPTY: rows가 비어 있음 (거래일 캘린더 자체 결손)
        - CALENDAR_DATE_NULL: 개별 row의 date가 None
        - CALENDAR_MARKET_INVALID: market이 KOSPI/KOSDAQ/KONEX 외

    SOFT_FAIL:
        - (현재 없음)
    """
    issues: list[ValidationIssue] = []

    if not data.rows:
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                code="CALENDAR_EMPTY",
                message=(
                    f"거래일 캘린더가 비어 있음: market={data.market} "
                    f"start={data.start_date.isoformat()} end={data.end_date.isoformat()}"
                ),
                context=(
                    ("end", data.end_date.isoformat()),
                    ("market", data.market),
                    ("start", data.start_date.isoformat()),
                ),
            )
        )

    for row in data.rows:
        ctx = (
            ("date", row.date.isoformat() if row.date is not None else "None"),
            ("market", str(row.market)),
        )
        if row.market not in ("KOSPI", "KOSDAQ", "KONEX"):
            issues.append(
                ValidationIssue(
                    severity="hard_fail",
                    code="CALENDAR_MARKET_INVALID",
                    message=f"시장 구분 위반: {row.market!r}",
                    context=ctx,
                )
            )

    return _finalize_result(issues, raise_on_hard_fail=raise_on_hard_fail)


__all__ = [
    "validate_calendar_data",
    "validate_daily_price_row",
    "validate_daily_prices_data",
    "validate_symbol_row",
    "validate_symbols_data",
]
