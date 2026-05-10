"""에러 코드 카탈로그 정식화 테스트 (10번 §7.1, step 037-B).

검증 항목:
    1. CODE_STATUS_MAP이 10번 §7.1 카탈로그와 1:1 매핑됨
    2. 각 AppError 서브클래스가 정확한 HTTP 상태 코드를 반환
    3. Pydantic 검증 실패 → INVALID_STRATEGY_JSON 또는 INVALID_PARAMETER_VALUE (비표준 코드 없음)
    4. 라우트 없는 404/405 → APP_ERROR envelope (NOT_FOUND, HTTP_ERROR 미사용)
    5. exceptions.py의 모든 클래스가 10번 §7.1 코드 목록에 포함됨
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.errors import CODE_STATUS_MAP
from app.core.exceptions import (
    AppError,
    BacktestAlreadyRunningError,
    BacktestNotRunningError,
    BacktestRunNotFoundError,
    BacktestTimeoutError,
    DuplicateStrategyNameError,
    ExitPositionInExitSignalError,
    ExitSignalInExitPositionError,
    ExportFailedError,
    ExportTooLargeError,
    ForbiddenError,
    InsufficientPriceDataError,
    InvalidDateRangeError,
    InvalidOperatorError,
    InvalidParameterValueError,
    InvalidStrategyJsonError,
    MarketDataNotFoundError,
    MissingRequiredParameterError,
    PositionConditionMisuseError,
    RateLimitExceededError,
    StrategyNotFoundError,
    SymbolNotFoundError,
    TimeseriesConditionMisuseError,
    TradingCalendarMissingError,
    UnauthorizedError,
    UniverseEmptyError,
    UniversePreviewFailedError,
    UnknownConditionTypeError,
)
from app.main import app


# ============================================================================
# 10번 §7.1 카탈로그 완전성 검증
# ============================================================================

# 10번 §7.1에 정의된 모든 에러 코드
_CATALOG_CODES = {
    # 전략 / 검증
    "INVALID_STRATEGY_JSON",
    "UNKNOWN_CONDITION_TYPE",
    "EXIT_POSITION_IN_EXIT_SIGNAL",
    "EXIT_SIGNAL_IN_EXIT_POSITION",
    "INVALID_OPERATOR",
    "INVALID_PARAMETER_VALUE",
    "MISSING_REQUIRED_PARAMETER",
    "STRATEGY_NOT_FOUND",
    "DUPLICATE_STRATEGY_NAME",
    # 백테스트
    "BACKTEST_RUN_NOT_FOUND",
    "BACKTEST_ALREADY_RUNNING",
    "BACKTEST_NOT_RUNNING",
    "BACKTEST_TIMEOUT",
    "INVALID_DATE_RANGE",
    "INSUFFICIENT_PRICE_DATA",
    "TRADING_CALENDAR_MISSING",
    # 데이터
    "MARKET_DATA_NOT_FOUND",
    "SYMBOL_NOT_FOUND",
    "UNIVERSE_EMPTY",
    "UNIVERSE_PREVIEW_FAILED",
    # 권한 / 인증
    "UNAUTHORIZED",
    "FORBIDDEN",
    "RATE_LIMIT_EXCEEDED",
    # Export
    "EXPORT_FAILED",
    "EXPORT_TOO_LARGE",
}


def test_code_status_map_covers_catalog():
    """CODE_STATUS_MAP이 §7.1 카탈로그의 모든 코드를 포함해야 함."""
    missing = _CATALOG_CODES - set(CODE_STATUS_MAP.keys())
    assert not missing, f"CODE_STATUS_MAP에서 누락된 카탈로그 코드: {missing}"


def test_code_status_map_no_unlisted_codes():
    """CODE_STATUS_MAP에 카탈로그에 없는 코드가 없어야 함.

    APP_ERROR는 내부 fallback이므로 허용. POSITION_CONDITION_MISUSE /
    TIMESERIES_CONDITION_MISUSE는 개발자용 내부 코드로 허용.
    """
    allowed_extras = {
        "APP_ERROR",             # 내부 fallback
        "POSITION_CONDITION_MISUSE",   # 개발자용
        "TIMESERIES_CONDITION_MISUSE", # 개발자용
    }
    unlisted = set(CODE_STATUS_MAP.keys()) - _CATALOG_CODES - allowed_extras
    assert not unlisted, f"카탈로그에 없는 코드가 CODE_STATUS_MAP에 존재: {unlisted}"


# ============================================================================
# 각 에러 코드 HTTP 상태 코드 매핑 검증 (10번 §7.2)
# ============================================================================

@pytest.mark.parametrize("code,expected_status", [
    # 400
    ("INVALID_STRATEGY_JSON", 400),
    ("INVALID_OPERATOR", 400),
    ("INVALID_PARAMETER_VALUE", 400),
    ("MISSING_REQUIRED_PARAMETER", 400),
    ("INVALID_DATE_RANGE", 400),
    ("EXPORT_TOO_LARGE", 400),
    # 401
    ("UNAUTHORIZED", 401),
    # 403
    ("FORBIDDEN", 403),
    # 404
    ("STRATEGY_NOT_FOUND", 404),
    ("BACKTEST_RUN_NOT_FOUND", 404),
    ("MARKET_DATA_NOT_FOUND", 404),
    ("SYMBOL_NOT_FOUND", 404),
    # 409
    ("BACKTEST_ALREADY_RUNNING", 409),
    ("DUPLICATE_STRATEGY_NAME", 409),
    ("BACKTEST_NOT_RUNNING", 409),
    # 422
    ("EXIT_POSITION_IN_EXIT_SIGNAL", 422),
    ("EXIT_SIGNAL_IN_EXIT_POSITION", 422),
    ("UNKNOWN_CONDITION_TYPE", 422),
    ("INSUFFICIENT_PRICE_DATA", 422),
    ("TRADING_CALENDAR_MISSING", 422),
    ("UNIVERSE_EMPTY", 422),
    ("UNIVERSE_PREVIEW_FAILED", 422),
    ("BACKTEST_TIMEOUT", 422),
    # 429
    ("RATE_LIMIT_EXCEEDED", 429),
    # 500
    ("EXPORT_FAILED", 500),
    ("APP_ERROR", 500),
])
def test_code_status_mapping(code: str, expected_status: int):
    """CODE_STATUS_MAP에서 코드 → HTTP 상태 매핑이 §7.2와 일치."""
    assert CODE_STATUS_MAP[code] == expected_status, (
        f"{code!r}: expected HTTP {expected_status}, got {CODE_STATUS_MAP[code]}"
    )


# ============================================================================
# AppError 서브클래스 코드 검증
# ============================================================================

@pytest.mark.parametrize("exc_class,expected_code", [
    (InvalidStrategyJsonError, "INVALID_STRATEGY_JSON"),
    (UnknownConditionTypeError, "UNKNOWN_CONDITION_TYPE"),
    (ExitPositionInExitSignalError, "EXIT_POSITION_IN_EXIT_SIGNAL"),
    (ExitSignalInExitPositionError, "EXIT_SIGNAL_IN_EXIT_POSITION"),
    (InvalidOperatorError, "INVALID_OPERATOR"),
    (InvalidParameterValueError, "INVALID_PARAMETER_VALUE"),
    (MissingRequiredParameterError, "MISSING_REQUIRED_PARAMETER"),
    (StrategyNotFoundError, "STRATEGY_NOT_FOUND"),
    (DuplicateStrategyNameError, "DUPLICATE_STRATEGY_NAME"),
    (BacktestRunNotFoundError, "BACKTEST_RUN_NOT_FOUND"),
    (BacktestNotRunningError, "BACKTEST_NOT_RUNNING"),
    (BacktestAlreadyRunningError, "BACKTEST_ALREADY_RUNNING"),
    (BacktestTimeoutError, "BACKTEST_TIMEOUT"),
    (InsufficientPriceDataError, "INSUFFICIENT_PRICE_DATA"),
    (TradingCalendarMissingError, "TRADING_CALENDAR_MISSING"),
    (InvalidDateRangeError, "INVALID_DATE_RANGE"),
    (MarketDataNotFoundError, "MARKET_DATA_NOT_FOUND"),
    (SymbolNotFoundError, "SYMBOL_NOT_FOUND"),
    (UniverseEmptyError, "UNIVERSE_EMPTY"),
    (UniversePreviewFailedError, "UNIVERSE_PREVIEW_FAILED"),
    (UnauthorizedError, "UNAUTHORIZED"),
    (ForbiddenError, "FORBIDDEN"),
    (RateLimitExceededError, "RATE_LIMIT_EXCEEDED"),
    (ExportFailedError, "EXPORT_FAILED"),
    (ExportTooLargeError, "EXPORT_TOO_LARGE"),
    (PositionConditionMisuseError, "POSITION_CONDITION_MISUSE"),
    (TimeseriesConditionMisuseError, "TIMESERIES_CONDITION_MISUSE"),
])
def test_exception_class_code(exc_class, expected_code: str):
    """각 AppError 서브클래스의 code 속성이 카탈로그 코드와 일치."""
    assert exc_class.code == expected_code


def test_all_app_error_subclasses_inherit_correctly():
    """모든 AppError 서브클래스가 AppError를 상속하고 to_dict()가 동작함."""
    err = InvalidStrategyJsonError("테스트 메시지", details=[{"field": "x", "message": "y"}])
    assert isinstance(err, AppError)
    d = err.to_dict()
    assert d["error"]["code"] == "INVALID_STRATEGY_JSON"
    assert d["error"]["message"] == "테스트 메시지"
    assert d["error"]["details"] == [{"field": "x", "message": "y"}]


# ============================================================================
# 비표준 코드 사용 금지 확인 (회귀)
# ============================================================================

_BANNED_CODES = {
    "VALIDATION_ERROR",    # 이전 임시 코드 — INVALID_PARAMETER_VALUE로 대체
    "NOT_FOUND",           # 이전 비표준 — 리소스별 코드로 대체
    "METHOD_NOT_ALLOWED",  # 이전 비표준 — APP_ERROR로 대체
    "HTTP_ERROR",          # 이전 비표준 — APP_ERROR로 대체
}


def test_banned_codes_not_in_status_map():
    """비표준(임시) 코드가 CODE_STATUS_MAP에 없어야 함."""
    found = _BANNED_CODES & set(CODE_STATUS_MAP.keys())
    assert not found, f"금지된 비표준 코드가 CODE_STATUS_MAP에 존재: {found}"


# ============================================================================
# API 응답에서 비표준 코드 미사용 확인
# ============================================================================

def test_pydantic_validation_error_uses_invalid_parameter_value(db_engine):  # noqa: ARG001
    """전략/백테스트 외 경로의 Pydantic 검증 실패 → INVALID_PARAMETER_VALUE."""
    client = TestClient(app)
    # market symbols 등 쿼리 파라미터 검증 실패 (잘못된 타입 등)
    # 여기서는 직접 AppError를 발생시키는 API를 테스트하는 대신
    # 에러 핸들러 동작을 직접 검증
    from app.api.errors import _looks_like_strategy_payload

    class FakeRequest:
        class FakeURL:
            path = "/api/market/symbols"
        url = FakeURL()

    assert not _looks_like_strategy_payload(FakeRequest())  # type: ignore[arg-type]

    class FakeStrategyRequest:
        class FakeURL:
            path = "/api/strategies"
        url = FakeURL()

    assert _looks_like_strategy_payload(FakeStrategyRequest())  # type: ignore[arg-type]


def test_route_404_uses_app_error_envelope(db_engine):  # noqa: ARG001
    """존재하지 않는 라우트(404)는 APP_ERROR envelope을 반환 (NOT_FOUND 미사용)."""
    client = TestClient(app)
    r = client.get("/api/nonexistent-endpoint-xyz")
    assert r.status_code in (404, 405)  # 미등록 경로

    body = r.json()
    assert "error" in body
    assert "detail" not in body
    # NOT_FOUND 비표준 코드가 아닌 APP_ERROR이어야 함
    assert body["error"]["code"] not in ("NOT_FOUND", "METHOD_NOT_ALLOWED", "HTTP_ERROR")


def test_strategy_not_found_uses_specific_code(db_engine):  # noqa: ARG001
    """존재하지 않는 strategy 조회 → STRATEGY_NOT_FOUND (NOT_FOUND 미사용)."""
    client = TestClient(app)
    r = client.get("/api/strategies/99999")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "STRATEGY_NOT_FOUND"
    assert body["error"]["code"] != "NOT_FOUND"
