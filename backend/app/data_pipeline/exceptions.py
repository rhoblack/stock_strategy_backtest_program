"""data_pipeline 예외 계층 (14번 §6.3 / §6.4 / §7 / §13).

본 모듈은 collectors / processors / jobs 전 단계에서 공통으로 던지고 잡는
예외 계층을 정의한다. 실제 collector/processor/job 구현체(025~028)는 본
계층을 상속하거나 그대로 사용해 분류된 오류를 발생시킨다.

분류 원칙:
    - 단계별 (Collector / Processor / Job) → 어느 단계에서 실패했는지 즉시 파악
    - 재시도 정책별 (Retryable / Fatal) → 14번 §6.3 재시도/백오프와 직결
    - 검증 실패 (DataValidation) → 14번 §7 자동 검증 항목 위배

설계 결정:
    - 모든 예외는 `DataPipelineError`를 단일 루트로 가져 호출자가 한 번에 잡을 수 있게 함.
    - `RetryableError` / `FatalError`는 단계와 직교하는 mixin성 분류이므로
      `CollectorError`와 다중 상속한 구체 예외(예: `RetryableCollectorError`)를
      후속 step에서 자유롭게 만들 수 있도록 베이스만 제공한다.
    - `DataValidationError`는 처리 단계에서 검증 실패 시 던진다 (14번 §7.2 — HARD/SOFT FAIL은 호출자 판단).

사용 예 (025~028에서):
    raise RetryableCollectorError("pykrx HTTP 503", retry_after_seconds=5)
    raise FatalCollectorError("KRX API key revoked")
    raise DataValidationError("OHLC 정합성 위반: high < low (symbol=005930, date=...)")

본 모듈 자체는 외부 fetch 0건 / 결정론적.
"""

from __future__ import annotations


class DataPipelineError(Exception):
    """data_pipeline 모듈의 모든 예외 루트.

    호출자(스케줄러, 상위 잡 러너)는 본 예외만 잡으면 파이프라인 단계 어디에서
    발생한 오류든 일괄 처리할 수 있다.
    """


# ---------------------------------------------------------------------------
# 단계별 예외 (Collector / Processor / Job)
# ---------------------------------------------------------------------------


class CollectorError(DataPipelineError):
    """수집 단계 (collectors/) 실패.

    예:
        - pykrx 응답 파싱 실패
        - HTTP 5xx
        - rate limit 차단 감지
    """


class ProcessorError(DataPipelineError):
    """가공 단계 (processors/) 실패.

    예:
        - 수정주가 재계산 중 corporate_actions 누락
        - 시가총액 계산용 상장주식수 미보유
    """


class JobError(DataPipelineError):
    """잡 실행 단계 (jobs/) 실패.

    예:
        - 잡이 의존하는 사전 잡이 미완료
        - 잡 타임아웃
    """


# ---------------------------------------------------------------------------
# 재시도 정책 직교 분류 (14번 §6.3)
# ---------------------------------------------------------------------------


class RetryableError(DataPipelineError):
    """재시도 가능한 일시적 오류 (네트워크/rate-limit 등).

    14번 §6.3 재시도 백오프 (1초 → 5초 → 30초 → 큐 보류) 적용 대상.

    Args:
        retry_after_seconds: 호출자가 권장 대기 시간을 명시할 때 사용.
            None이면 호출자 기본 백오프 정책 사용 (025에서 활용).
    """

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class FatalError(DataPipelineError):
    """재시도 불가능한 영구적 오류 — 즉시 큐에서 제거.

    14번 §6.3 "연속 실패 5회" 알림 큐와 별개로, 본 예외는 단 1회로 영구 실패 분류.
    예: 인증 실패, 스키마 위반, 잡 의존성 영구 누락.
    """


# ---------------------------------------------------------------------------
# 데이터 검증 실패 (14번 §7)
# ---------------------------------------------------------------------------


class DataValidationError(ProcessorError):
    """수집/가공 데이터가 14번 §7 자동 검증 항목을 위배.

    ProcessorError 하위로 둔 이유:
        - 검증은 본질적으로 가공 단계의 한 종류 (transform 전 validate)
        - 단, 호출자가 단계 무관하게 검증 실패만 잡고 싶다면 본 예외를 직접 사용 가능

    예:
        - OHLC 정합성 (high < low)
        - volume < 0
        - 가격 ±35% 점프인데 corporate_action 미보유
        - 수정주가 계산 정합성 어긋남
    """


__all__ = [
    "DataPipelineError",
    "CollectorError",
    "ProcessorError",
    "JobError",
    "RetryableError",
    "FatalError",
    "DataValidationError",
]
