"""표준 에러 envelope 변환 (10번 7절).

모든 에러 응답은 다음 형식이어야 합니다.

```json
{
  "error": {
    "code": "INVALID_STRATEGY_JSON",
    "message": "전략 JSON이 올바르지 않습니다.",
    "details": [
      {"field": "entry.conditions", "message": "매수 조건이 필요합니다."}
    ]
  }
}
```

라우트는 `HTTPException(detail=...)`을 직접 던지지 말고 `AppError`(또는
하위 클래스)를 raise합니다. 본 모듈의 `register_exception_handlers`가
`{"error": {...}}` 형식으로 변환하고 적절한 HTTP 상태 코드(7.2)를 매핑합니다.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


# 에러 코드 → HTTP 상태 매핑 (10번 7.2)
# 카탈로그(7.1)에 없는 코드를 추가하지 말 것 — 정책 변경 시 10번 문서 먼저 갱신.
CODE_STATUS_MAP: dict[str, int] = {
    # 400 검증 실패
    "INVALID_STRATEGY_JSON": status.HTTP_400_BAD_REQUEST,
    "INVALID_OPERATOR": status.HTTP_400_BAD_REQUEST,
    "INVALID_PARAMETER_VALUE": status.HTTP_400_BAD_REQUEST,
    "MISSING_REQUIRED_PARAMETER": status.HTTP_400_BAD_REQUEST,
    "INVALID_DATE_RANGE": status.HTTP_400_BAD_REQUEST,
    # 401/403 인증·권한
    "UNAUTHORIZED": status.HTTP_401_UNAUTHORIZED,
    "FORBIDDEN": status.HTTP_403_FORBIDDEN,
    # 404 not found (리소스별 구체적 코드)
    "STRATEGY_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "BACKTEST_RUN_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "MARKET_DATA_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "SYMBOL_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    # 409 충돌
    "BACKTEST_ALREADY_RUNNING": status.HTTP_409_CONFLICT,
    "DUPLICATE_STRATEGY_NAME": status.HTTP_409_CONFLICT,
    "BACKTEST_NOT_RUNNING": status.HTTP_409_CONFLICT,
    # 422 도메인 검증 (시계열/포지션 라우팅 등)
    "EXIT_POSITION_IN_EXIT_SIGNAL": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "EXIT_SIGNAL_IN_EXIT_POSITION": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "UNKNOWN_CONDITION_TYPE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "POSITION_CONDITION_MISUSE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "TIMESERIES_CONDITION_MISUSE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "INSUFFICIENT_PRICE_DATA": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "TRADING_CALENDAR_MISSING": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "UNIVERSE_EMPTY": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "UNIVERSE_PREVIEW_FAILED": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "BACKTEST_TIMEOUT": status.HTTP_422_UNPROCESSABLE_ENTITY,
    # 429
    "RATE_LIMIT_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
    # Export (500 or 400 계열 선택: 대용량은 400, 처리 실패는 500)
    "EXPORT_FAILED": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "EXPORT_TOO_LARGE": status.HTTP_400_BAD_REQUEST,
    # Watchlist (10번 5-t절)
    "WATCHLIST_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "WATCHLIST_ITEM_ALREADY_EXISTS": status.HTTP_409_CONFLICT,
    # 500 fallback
    "APP_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _envelope_response(
    code: str,
    message: str,
    *,
    details: list[dict] | None = None,
    status_code: int | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """`{"error": {...}}` 형식 응답 생성. X-Request-ID는 미들웨어가 또 한번
    덮어쓰지만, 라우트에서 직접 호출되는 경우를 위해 헤더에도 부착한다.
    """
    http_status = status_code if status_code is not None else CODE_STATUS_MAP.get(
        code, status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        }
    }
    headers: dict[str, str] = {}
    if request_id:
        headers["X-Request-ID"] = request_id
    return JSONResponse(status_code=http_status, content=body, headers=headers)


def _request_id_from(request: Request) -> str | None:
    # request.state에 middleware가 부착해둔 값을 우선
    rid = getattr(request.state, "request_id", None)
    if rid:
        return str(rid)
    incoming = request.headers.get("X-Request-ID")
    return str(incoming) if incoming else None


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    rid = _request_id_from(request)
    logger.warning(
        "AppError code=%s message=%s request_id=%s path=%s",
        exc.code,
        exc.message,
        rid,
        request.url.path,
    )
    return _envelope_response(
        exc.code, exc.message, details=exc.details, request_id=rid
    )


async def _handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic schema 검증 실패도 표준 envelope으로 변환 (10번 §7.1 정식화).

    FastAPI 기본은 `{"detail": [...]}` — 본 핸들러가 카탈로그 코드로 변환한다.
    `details`는 Pydantic의 errors() 결과 중 핵심만 추려 노출한다 (결정론을
    위해 loc 기준 정렬).

    경로별 코드 선택 (10번 §7.1):
        /api/strategies  경로 → INVALID_STRATEGY_JSON
        /api/backtests   경로 → INVALID_STRATEGY_JSON (backtest create 요청)
        그 외            → INVALID_PARAMETER_VALUE (일반 파라미터 검증 실패)
    """
    rid = _request_id_from(request)
    raw = exc.errors()
    details: list[dict] = [
        {
            "field": ".".join(str(p) for p in (item.get("loc") or [])),
            "message": item.get("msg", ""),
            "type": item.get("type", ""),
        }
        for item in raw
    ]
    details.sort(key=lambda d: (d.get("field", ""), d.get("type", "")))

    # 경로 기반 에러 코드 선택 (카탈로그 내 코드만 사용)
    if _looks_like_strategy_payload(request):
        error_code = "INVALID_STRATEGY_JSON"
        message = "요청 본문이 올바르지 않습니다."
    else:
        error_code = "INVALID_PARAMETER_VALUE"
        message = "요청 파라미터가 올바르지 않습니다."

    return _envelope_response(
        error_code,
        message,
        details=details,
        status_code=status.HTTP_400_BAD_REQUEST,
        request_id=rid,
    )


def _looks_like_strategy_payload(request: Request) -> bool:
    """요청 경로가 strategy/backtest 관련이면 INVALID_STRATEGY_JSON 코드를 사용."""
    path = request.url.path
    return "/api/strategies" in path or "/api/backtests" in path


async def _handle_starlette_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """남아있는 raw HTTPException(예: 존재하지 않는 라우트의 404)도 envelope으로."""
    rid = _request_id_from(request)
    detail = exc.detail
    code: str
    message: str
    details: list[dict] = []
    if isinstance(detail, dict) and "code" in detail:
        # 과거 코드가 detail={"code": "..."} 형식으로 던진 경우
        code = str(detail.get("code", "APP_ERROR"))
        message = str(detail.get("message", code))
        nested = detail.get("details")
        if isinstance(nested, list):
            details = nested
    else:
        # 404 등 standard message
        code = _status_to_code(exc.status_code)
        message = str(detail) if detail is not None else code
    return _envelope_response(
        code, message, details=details, status_code=exc.status_code, request_id=rid
    )


def _status_to_code(http_status: int) -> str:
    """HTTP 상태 → 카탈로그 코드 추정 (10번 §7.1 정식 코드만 사용).

    라우트 미등록 404, 405 등 Starlette 자체 HTTPException에서 호출된다.
    카탈로그에 없는 코드는 APP_ERROR로 fallback한다.

    NOTE: 404는 리소스별 코드(STRATEGY_NOT_FOUND 등)를 사용해야 하지만,
    라우트가 존재하지 않는 경우에는 리소스를 특정할 수 없으므로
    APP_ERROR로 처리한다. 실제 리소스 미존재는 AppError 서브클래스를 raise한다.
    """
    if http_status == 401:
        return "UNAUTHORIZED"
    if http_status == 403:
        return "FORBIDDEN"
    if http_status == 429:
        return "RATE_LIMIT_EXCEEDED"
    # 404 (라우트 없음), 405 (메서드 없음) → APP_ERROR (리소스 특정 불가)
    # 라우트 자체가 없는 경우이므로 카탈로그 리소스별 코드 사용 불가.
    return "APP_ERROR"


async def _handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    rid = _request_id_from(request)
    logger.exception(
        "Unhandled exception request_id=%s path=%s", rid, request.url.path
    )
    return _envelope_response(
        "APP_ERROR",
        f"{type(exc).__name__}: {exc}",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=rid,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """FastAPI 앱에 표준 envelope 핸들러를 등록.

    main.py의 앱 생성 직후 1회 호출.
    """
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_starlette_http_exception)
    # 마지막 안전망 — 미처리 예외도 envelope으로
    app.add_exception_handler(Exception, _handle_unexpected_exception)
