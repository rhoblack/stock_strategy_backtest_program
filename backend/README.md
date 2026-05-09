# Backend

레고형 주식 매매 전략 생성 및 백테스트 프로그램의 백엔드 패키지.

상위 디렉토리의 `상세설계/` 문서를 단일 출처로 따른다. 작업 흐름과 정책은 프로젝트 루트의 `CLAUDE.md` 참조.

## 환경 셋업

Python 3.11 이상 필요. Windows에서는 공식 Python (py launcher) 권장.

```bash
cd backend
py -m venv .venv
source .venv/Scripts/activate    # Git Bash
# 또는 .venv\Scripts\activate      # cmd
pip install -e ".[dev]"
pytest
```

## 디렉토리 구조

```text
app/
  core/          설정, 예외, 로깅
  api/           FastAPI 라우트 (Phase 4부터)
  db/            DB 세션, 마이그레이션 (Phase 2부터)
  models/        SQLAlchemy 모델 (Phase 2부터)
  schemas/       Pydantic 스키마
  services/      비즈니스 로직 서비스
  strategy/      ConditionRegistry, StrategyEngine, indicators
    conditions/  조건 함수 (Registry에 자동 등록)
  backtest/      BacktestEngine, ExecutionModel, Metrics
  portfolio/     Portfolio, Position, TradeGroup, CashManager
  market_data/   Provider, UniverseSelector (Phase 14)
  reports/       결과 요약, 차트 데이터
  exporters/     CSV, ZIP Export
tests/           pytest 단위/통합 테스트
```

## 자주 쓰는 명령

```bash
pytest                         # 전체 테스트
pytest tests/strategy/         # 모듈별 실행
pytest -k registry             # 패턴 매칭
ruff check app tests           # 린트
ruff format app tests          # 포맷
```
