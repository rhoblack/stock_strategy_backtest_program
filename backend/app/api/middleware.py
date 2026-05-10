"""HTTP 미들웨어 — X-Request-ID 발급/보존 (10번 8절).

설계 원칙(10.8):
    "모든 응답에 X-Request-ID 헤더 포함."

incoming 요청에 X-Request-ID가 있으면 그대로 보존하고, 없으면 새로 발급하여
응답 헤더와 `request.state.request_id`에 부착한다.

errors.py의 exception_handler가 request.state.request_id를 읽어 에러 응답
헤더에도 부착하므로 정상 응답·에러 응답 모두 같은 ID를 갖는다.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """X-Request-ID 미들웨어.

    동작:
        1. incoming 요청에서 X-Request-ID 헤더를 찾음
        2. 없으면 uuid4().hex를 새로 발급
        3. request.state.request_id에 저장 (라우트/handler에서 읽기 가능)
        4. 응답 헤더에 X-Request-ID 부착 — 에러 응답 포함

    예외가 미들웨어 안에서 던져지면(라우트에서 raise된 AppError 등) Starlette
    스택이 등록된 exception_handler로 라우팅한다. 그 핸들러가 다시 같은
    request.state.request_id를 읽어 응답 헤더에 부착하므로 ID가 보존된다.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming if incoming else uuid.uuid4().hex
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception:
            # 예외는 등록된 exception_handler가 envelope 응답을 만든다.
            # 다만 그 응답에도 같은 ID가 부착되도록 로깅만 하고 재발생.
            logger.debug(
                "request_id=%s path=%s 예외가 핸들러로 위임됨", request_id, request.url.path
            )
            raise

        # 라우트가 응답에 직접 헤더를 안 넣었으면 미들웨어가 부여
        if REQUEST_ID_HEADER not in response.headers:
            response.headers[REQUEST_ID_HEADER] = request_id
        return response
