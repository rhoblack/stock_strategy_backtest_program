"""BaseProcessor 추상 인터페이스 (14번 §5 / §7 / §9 / §8).

본 모듈은 collector가 수집한 raw 데이터를 가공/검증하는 processor의 공통 베이스를
정의한다. 026 AdjustedPriceProcessor / 027 MarketCapProcessor가 본 베이스를 상속.

설계 결정 (인계 정보 — 026 AdjustedPriceProcessor가 그대로 따름):

    1. **단일 `process(input_data) -> ProcessedResult` 진입점** (3단계 분리 안 함)

        근거:
            - validate / transform / load 3단계 분리는 ETL 패턴의 기본이지만,
              본 파이프라인에서 load(=DB 쓰기)는 `repositories`가 일관되게 담당하므로
              processor는 검증+변환만 하면 되고, 외부 호출자가 결과를 받아 직접
              repositories에 위임하는 편이 명확하다.
            - 검증은 변환과 동시에 일어나는 경우가 많음 (예: 수정주가 재계산 중
              corporate_action 누락 발견 → 즉시 DataValidationError).
            - 단계가 더 필요한 processor는 `process` 내부에서 자체적으로 분할 가능.

    2. **ProcessedResult dataclass (frozen)**
        - rows + warnings + stats 필드만 — 처리량/정합성 통계로 호출자가 모니터링
        - 결정론을 위해 모든 시퀀스는 tuple

    3. **ValidationResult dataclass (frozen)**
        - 검증만 별도로 호출하고 싶은 호출자(예: UI 검증 미리보기)를 위한 부수 산출물
        - 본 step에서는 dataclass만 정의, 실제 검증 로직은 026~ 후속

    4. **외부 fetch 0건 / DB 미터치**
        - processor는 메모리 내에서만 동작 → 테스트 용이성 + 결정론
        - 실제 DB 적재는 호출자(Job) 또는 repositories가 담당

예외 정책 (`app.data_pipeline.exceptions`):
    - 검증 실패 → `DataValidationError` (14번 §7)
    - 가공 중 일반 오류 → `ProcessorError`
    - 영구 오류 (스키마 위배) → `FatalError`와 다중상속 (026 결정)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

# 입력/출력 타입은 구현체별로 다양 — 제네릭으로 추상화
_InputT = TypeVar("_InputT")
_OutputT = TypeVar("_OutputT")


# ---------------------------------------------------------------------------
# 결과 dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationIssue:
    """단일 검증 이슈 — 14번 §7.1 자동 검증 항목 위배 1건.

    Attributes:
        severity: "hard_fail" | "soft_fail" | "warning" — 14번 §7.2 분류.
        code: 안정 식별자 (예: "OHLC_INCONSISTENT", "MARKET_CAP_MISSING").
            테스트와 모니터링이 본 코드로 카운트할 수 있도록 영문/숫자/언더스코어로만 구성.
        message: 사람이 읽을 메시지.
        context: 추가 메타 (symbol, date 등). 결정론 위해 dict 순회 의존 금지.
    """

    severity: str
    code: str
    message: str
    context: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ValidationResult:
    """검증 호출의 결과 묶음 (14번 §7).

    Attributes:
        issues: 발생한 모든 검증 이슈 — code ASC, severity ASC tie-breaker.
            결정론: dict 순회 의존 금지.
        passed: 단일 hard_fail이라도 있으면 False.
    """

    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)
    passed: bool = True

    @property
    def hard_fail_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "hard_fail")

    @property
    def soft_fail_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "soft_fail")


@dataclass(frozen=True)
class ProcessedResult(Generic[_OutputT]):
    """`process` 호출의 결과 (14번 §5 / §9).

    Attributes:
        output: 가공된 데이터 (구현체가 정의 — 예: tuple[RawDailyPriceRow, ...]).
        validation: 부수적으로 발생한 검증 결과 (실패해도 output은 partial 채울 수 있음).
        stats: 처리량/카운트 등 모니터링 메트릭.
            결정론: tuple of (key, value) — dict 순회 의존 금지.
        warnings: 비치명적 경고 메시지.
    """

    output: _OutputT
    validation: ValidationResult = field(default_factory=ValidationResult)
    stats: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# BaseProcessor
# ---------------------------------------------------------------------------


class BaseProcessor(ABC, Generic[_InputT, _OutputT]):
    """raw 데이터를 가공/검증하는 processor 추상 베이스 (14번 §5).

    Args:
        name: processor 식별자 (로그/통계에 사용).

    Subclass 책임 (026~ 구현체가 따라야 함):
        - `process(input_data) -> ProcessedResult[_OutputT]` 구현
        - 14번 §7 검증 항목 매핑 (위배 시 ValidationIssue 누적)
        - 13.7 수정주가 정책 / 14.10 결손 정책 준수
        - 결정론: 같은 입력 같은 출력 보장 (dict 순회/random 사용 금지)
        - 외부 fetch / DB 미터치 — pure function 성격

    예시 026 AdjustedPriceProcessor (참고):
        process(prices, corporate_actions) -> ProcessedResult[tuple[RawDailyPriceRow, ...]]
            - corporate_actions 적용해 adj_* 재계산
            - 정합성 위배 시 validation.issues에 누적, severity 분류
            - stats: ("recalculated_rows", N), ("corporate_actions_applied", M)
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def process(self, input_data: _InputT) -> ProcessedResult[_OutputT]:
        """가공 메인 진입점.

        Args:
            input_data: 구현체가 정의 (예: RawDailyPricesData + corporate_actions 튜플).

        Returns:
            ProcessedResult — output + validation + stats + warnings.

        Raises:
            ProcessorError: 가공 단계 일반 오류.
            DataValidationError: 검증 hard_fail이고 즉시 중단해야 할 때.
                (soft_fail은 ValidationResult.issues에만 누적하고 raise하지 않는 것이 원칙.)
        """

    # ------------------------------------------------------------------
    # Subclass용 결정론 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _stats_to_tuple(stats: dict[str, int]) -> tuple[tuple[str, int], ...]:
        """dict[str, int]를 (key ASC) 정렬 tuple로 변환 — 결정론 보장."""
        return tuple(sorted(stats.items(), key=lambda kv: kv[0]))

    @staticmethod
    def _context_to_tuple(context: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        """dict[str, Any] context를 (key ASC) 정렬된 (key, str(value)) tuple로 변환."""
        return tuple(sorted(((k, str(v)) for k, v in context.items()), key=lambda kv: kv[0]))


__all__ = [
    "BaseProcessor",
    "ProcessedResult",
    "ValidationResult",
    "ValidationIssue",
]
