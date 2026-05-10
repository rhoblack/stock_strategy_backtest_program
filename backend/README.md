# Backend

레고형 주식 매매 전략 생성 및 백테스트 프로그램의 백엔드 패키지.

상위 디렉토리의 `상세설계/` 문서를 단일 출처로 따른다. 작업 흐름과 정책은 프로젝트 루트의 `CLAUDE.md` 참조.

**현재 상태** (2026-05-10, Phase 8 Wave A·B 완료): pytest **397/397 통과** + ruff All checks passed. 리뷰 011 Critical 5건 중 4건(C1·C3·C4·C5) 해소, C2(`ExecutionResult` dataclass)는 다음 작업 1순위.

## 환경 셋업

Python 3.12 사용 (`backend/.venv/`는 Python 3.12.9). 3.11+에서도 동작.

```bash
cd backend
py -3.12 -m venv .venv
source .venv/Scripts/activate    # Git Bash
# 또는 .venv\Scripts\activate      # cmd
pip install -e ".[dev]"
pytest
```

## 디렉토리 구조

```text
app/
  core/          설정, 예외 (AppError 카탈로그), 로깅
  api/           FastAPI 라우트 + 미들웨어
    routes_strategies.py   전략 CRUD + duplicate (user_id scope 강제)
    routes_backtests.py    백테스트 실행/결과/차트/export
    routes_conditions.py   GET /api/conditions (메타데이터)
    errors.py              AppError → 표준 envelope 변환 (10번 7절)
    middleware.py          X-Request-ID middleware (10번 8절)
    dependencies.py        Depends 헬퍼 (get_db, get_current_user_id)
  db/            DB 세션 + Alembic 연동
  models/        SQLAlchemy 모델 (application 테이블)
  schemas/       Pydantic 스키마
    strategy_json.py       StrategyJsonValidator (02번 schema 단일 출처)
  services/      비즈니스 로직 (strategy_service, backtest_service)
  strategy/      ConditionRegistry, StrategyEngine, indicators
    conditions/  조건 함수 (Registry 자동 등록, 현재 8개 등록)
  backtest/      BacktestEngine (오케스트레이터), ExecutionModel, Metrics
  portfolio/     Portfolio, Position, TradeGroup, CashManager, PositionSizer
  market_data/   (미구현 — 외부 CR-002 참조, market-data-engineer 영역)
  reports/       결과 요약, 차트 데이터
  exporters/     CSV, ZIP Export
  main.py        FastAPI 앱 + middleware/handler 등록
  main_state.py  앱 수명주기 상태 (백그라운드 작업 등)
tests/
  api/           라우트 테스트 (scope·envelope 매트릭스 포함)
  schemas/       validator 테스트 (음성 케이스 전수)
  services/      서비스 레이어 통합 테스트
  strategy/      ConditionRegistry + StrategyEngine + 조건 8종
  backtest/      엔진 + Golden test (9지표 frozen expected)
  portfolio/     Portfolio + CashManager + Position
  exporters/     CSV/ZIP
```

## 자주 쓰는 명령

### 테스트 / 린트

```bash
pytest                         # 전체 397건
pytest tests/strategy/         # 모듈별 실행
pytest -k registry             # 패턴 매칭
pytest tests/backtest/test_golden_*.py   # 골든 회귀 (9지표 frozen expected)
ruff check app tests           # 린트
ruff format app tests          # 포맷
```

### 개발 서버

```bash
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs
```

### DB 마이그레이션 (Alembic)

```bash
# 운영/dev DB에 최신 스키마 적용
alembic upgrade head

# 새 마이그레이션 자동 생성 (모델 변경 후)
alembic revision --autogenerate -m "변경 설명"

# 현재 적용된 revision 확인
alembic current

# 한 단계 롤백
alembic downgrade -1
```

테스트 환경은 `init_db(engine)` (create_all)을 사용. 운영/dev는 alembic.

DB URL은 `alembic.ini`의 `sqlalchemy.url` 또는 환경변수 `ALEMBIC_DATABASE_URL`로 override.
