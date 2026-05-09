"""FastAPI 애플리케이션 진입점.

실행:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

설계서 10번 문서 3~6절에 따라 도메인별 라우터를 include.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes_conditions import router as conditions_router
from app.api.routes_strategies import router as strategies_router

app = FastAPI(
    title="Stock Strategy Lab API",
    description="레고형 주식 매매 전략 생성 및 백테스트 프로그램 API",
    version=__version__,
)

# 프론트엔드(Vite dev server)에서 호출 가능하게 — 운영 시 도메인 좁힐 것
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


# 도메인 라우터
app.include_router(conditions_router)
app.include_router(strategies_router)
