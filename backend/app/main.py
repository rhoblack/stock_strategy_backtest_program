"""FastAPI 애플리케이션 진입점.

실행:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

설계서 10번 문서 3~6절에 따라 도메인별 라우터를 include.
10번 7절(에러 envelope) + 8절(X-Request-ID)을 모든 응답에 적용.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestIdMiddleware
from app.api.routes_backtests import router as backtests_router
from app.api.routes_conditions import router as conditions_router
from app.api.routes_market import calendar_router, symbols_router
from app.api.routes_strategies import router as strategies_router

app = FastAPI(
    title="Stock Strategy Lab API",
    description="레고형 주식 매매 전략 생성 및 백테스트 프로그램 API",
    version=__version__,
)

# 미들웨어 등록 순서 주의: 나중에 add_middleware 한 것이 outer가 된다.
# RequestIdMiddleware가 가장 outer여야 모든 응답(예외 포함)이 X-Request-ID를 갖는다.
# 따라서 CORS를 먼저 등록하고 RequestId를 나중에 등록.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIdMiddleware)

# 표준 error envelope 핸들러 (10.7) — AppError / RequestValidationError /
# StarletteHTTPException / Exception 모두 {"error": {...}}로 변환
register_exception_handlers(app)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


# 도메인 라우터
app.include_router(conditions_router)
app.include_router(strategies_router)
app.include_router(backtests_router)
# 시장 데이터 라우터 (10-o)
app.include_router(symbols_router)
app.include_router(calendar_router)
