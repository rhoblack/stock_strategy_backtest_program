"""커스텀 예외 계층.

설계서 10번 API 문서 7.1절의 에러 코드와 매핑되는 예외 클래스를 정의.
모든 도메인 예외는 AppError를 상속한다.

에러 코드 카탈로그 (10번 §7.1 전체):

전략 / 검증:
    INVALID_STRATEGY_JSON, UNKNOWN_CONDITION_TYPE,
    EXIT_POSITION_IN_EXIT_SIGNAL, EXIT_SIGNAL_IN_EXIT_POSITION,
    INVALID_OPERATOR, INVALID_PARAMETER_VALUE, MISSING_REQUIRED_PARAMETER,
    STRATEGY_NOT_FOUND, DUPLICATE_STRATEGY_NAME

백테스트:
    BACKTEST_RUN_NOT_FOUND, BACKTEST_ALREADY_RUNNING, BACKTEST_NOT_RUNNING,
    BACKTEST_TIMEOUT, INVALID_DATE_RANGE, INSUFFICIENT_PRICE_DATA,
    TRADING_CALENDAR_MISSING

데이터:
    MARKET_DATA_NOT_FOUND, SYMBOL_NOT_FOUND, UNIVERSE_EMPTY,
    UNIVERSE_PREVIEW_FAILED

권한 / 인증:
    UNAUTHORIZED, FORBIDDEN, RATE_LIMIT_EXCEEDED

Export:
    EXPORT_FAILED, EXPORT_TOO_LARGE

내부 (카탈로그 외, 개발자용):
    POSITION_CONDITION_MISUSE, TIMESERIES_CONDITION_MISUSE
"""


class AppError(Exception):
    """애플리케이션 전체 공통 베이스 예외."""

    code: str = "APP_ERROR"

    def __init__(self, message: str, *, details: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# === 전략 / 검증 ===


class InvalidStrategyJsonError(AppError):
    code = "INVALID_STRATEGY_JSON"


class UnknownConditionTypeError(AppError):
    code = "UNKNOWN_CONDITION_TYPE"


class ExitPositionInExitSignalError(AppError):
    """포지션 조건이 exit_signal 섹션에 들어간 경우."""

    code = "EXIT_POSITION_IN_EXIT_SIGNAL"


class ExitSignalInExitPositionError(AppError):
    """시계열 조건이 exit_position 섹션에 들어간 경우."""

    code = "EXIT_SIGNAL_IN_EXIT_POSITION"


class InvalidOperatorError(AppError):
    code = "INVALID_OPERATOR"


class InvalidParameterValueError(AppError):
    code = "INVALID_PARAMETER_VALUE"


class MissingRequiredParameterError(AppError):
    code = "MISSING_REQUIRED_PARAMETER"


class StrategyNotFoundError(AppError):
    code = "STRATEGY_NOT_FOUND"


class DuplicateStrategyNameError(AppError):
    """동일 사용자의 전략 이름이 중복되는 경우 (409 Conflict)."""

    code = "DUPLICATE_STRATEGY_NAME"


class PositionConditionMisuseError(AppError):
    """포지션 조건을 시계열 평가(evaluate)로 호출한 경우.

    보통은 schema validator가 먼저 잡아야 하는 프로그래머 오류.
    StrategyEngine에서 `requires_position=True`인 조건을 처리하려고 할 때 발생.
    """

    code = "POSITION_CONDITION_MISUSE"


class TimeseriesConditionMisuseError(AppError):
    """시계열 조건을 포지션 평가(evaluate_position)로 호출한 경우.

    BacktestEngine/Portfolio에서 `requires_position=False`인 조건을 처리하려고 할 때 발생.
    """

    code = "TIMESERIES_CONDITION_MISUSE"


# === 백테스트 ===


class BacktestRunNotFoundError(AppError):
    code = "BACKTEST_RUN_NOT_FOUND"


class BacktestNotRunningError(AppError):
    """이미 종료된 실행에 대해 cancel 등 진행 중 전용 동작을 호출한 경우."""

    code = "BACKTEST_NOT_RUNNING"


class BacktestAlreadyRunningError(AppError):
    """동일 strategy/run에 대해 중복 실행 요청."""

    code = "BACKTEST_ALREADY_RUNNING"


class BacktestTimeoutError(AppError):
    """백테스트 실행이 제한 시간 초과."""

    code = "BACKTEST_TIMEOUT"


class InsufficientPriceDataError(AppError):
    code = "INSUFFICIENT_PRICE_DATA"


class TradingCalendarMissingError(AppError):
    code = "TRADING_CALENDAR_MISSING"


class InvalidDateRangeError(AppError):
    code = "INVALID_DATE_RANGE"


# === 데이터 ===


class MarketDataNotFoundError(AppError):
    code = "MARKET_DATA_NOT_FOUND"


class SymbolNotFoundError(AppError):
    code = "SYMBOL_NOT_FOUND"


class UniverseEmptyError(AppError):
    code = "UNIVERSE_EMPTY"


class UniversePreviewFailedError(AppError):
    """유니버스 미리보기 실패 (데이터 부족, 파라미터 오류 등)."""

    code = "UNIVERSE_PREVIEW_FAILED"


# === 권한 / 인증 ===


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    code = "FORBIDDEN"


class RateLimitExceededError(AppError):
    code = "RATE_LIMIT_EXCEEDED"


# === Export ===


class ExportFailedError(AppError):
    """Export 처리 중 오류."""

    code = "EXPORT_FAILED"


class ExportTooLargeError(AppError):
    """Export 결과가 허용 크기를 초과."""

    code = "EXPORT_TOO_LARGE"
