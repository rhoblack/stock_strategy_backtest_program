---
date: 2026-05-09
agent: main
phase: 2
status: completed
related_docs:
  - 상세설계/07_database_design.md
  - 상세설계/02_strategy_json_schema_design.md
---

# Phase 2 / Step 1 — SQLAlchemy DB 인프라 + users / strategies / strategy_versions 모델

## Plan

설계서 07번 문서 4~6절. SQLAlchemy 2.x 스타일 (DeclarativeBase + mapped_column + Mapped[Type]). Alembic은 별도 step으로 분리 (이번엔 create_all로 시작).

### 작성할 파일

- [x] `pyproject.toml` 업데이트 (sqlalchemy>=2.0)
- [x] `app/db/base.py` — Base + TimestampMixin
- [x] `app/db/session.py` — create_db_engine / make_session_factory / init_db / drop_db
- [x] `app/db/__init__.py` 노출
- [x] `app/models/__init__.py` (User/Strategy/StrategyVersion 등록 트리거)
- [x] `app/models/user.py` — User
- [x] `app/models/strategy.py` — Strategy + StrategyVersion

### 테스트

- [x] `tests/db/__init__.py`, `tests/db/conftest.py`
- [x] `tests/db/test_models_user.py` (4건)
- [x] `tests/db/test_models_strategy.py` (7건)

### 정책 / 주의

- SQLAlchemy 2.x 스타일 일관 사용
- JSON은 SQLAlchemy의 `JSON` 타입 (SQLite TEXT, PostgreSQL JSONB 둘 다 지원)
- timezone: created_at은 UTC datetime (정확성 정책 13.13)
- soft delete: deleted_at IS NULL인 행만 보이도록 헬퍼 메서드 (이번 step에선 컬럼만 추가, 쿼리 헬퍼는 후속)
- User 삭제 시 cascade 정책: MVP는 RESTRICT (User 삭제 자체를 막거나 Strategy를 먼저 삭제하도록). 단순화로 cascade='all, delete-orphan' 적용 검토 → MVP는 RESTRICT 안전.
- Phase 1 코드와의 통합은 다음 step (BacktestRun 모델)에서 본격화

## Execution

```text
backend/pyproject.toml                   sqlalchemy>=2.0 추가
backend/app/db/base.py                   Base (DeclarativeBase) + TimestampMixin (UTC)
backend/app/db/session.py                create_db_engine + make_session_factory + init_db + drop_db
backend/app/db/__init__.py               노출
backend/app/models/__init__.py           User/Strategy/StrategyVersion 등록 트리거
backend/app/models/user.py               User (email unique, hashed_password nullable, strategies cascade)
backend/app/models/strategy.py
  - Strategy (user_id FK CASCADE, strategy_json JSON, tags JSON list,
              favorite, deleted_at index, versions cascade)
  - StrategyVersion (strategy_id FK CASCADE, version, strategy_json JSON,
                     change_note, created_at)

backend/tests/db/__init__.py             빈 파일
backend/tests/db/conftest.py             db_engine + db_session fixture (in-memory SQLite)
backend/tests/db/test_models_user.py     4건 (생성/unique/full fields/repr)
backend/tests/db/test_models_strategy.py 7건 (생성/relationship/version 순서/
                                              cascade/soft delete/User cascade)
```

설계 결정:
- **SQLAlchemy 2.x 스타일**: DeclarativeBase + Mapped[Type] + mapped_column. 타입 힌트 친화적.
- **TimestampMixin**: UTC datetime 자동 채움 (created_at default, updated_at default+onupdate). 정확성 정책 13.13 준수.
- **JSON 컬럼은 SQLAlchemy의 `JSON` 타입**: SQLite TEXT, PostgreSQL JSONB 자동 처리. dict/list round-trip 검증 통과.
- **Strategy ↔ User cascade**: User 삭제 → Strategy CASCADE. MVP는 단순화.
- **StrategyVersion ↔ Strategy cascade**: 버전은 부모 전략에 종속. 단독 존재 의미 없음.
- **soft delete**: `deleted_at` 컬럼만 추가 + index. 쿼리 헬퍼 (deleted_at IS NULL 자동 필터)는 후속 step에서.
- **init_db / drop_db**: Alembic 도입 전 임시 헬퍼. 다음 step에서 Alembic으로 교체.
- **`models/__init__.py`에서 모든 모델 import**: Base.metadata가 모델을 인식하려면 import가 트리거되어야 함.

## Tests

```text
============== 227 passed in 1.21s ==============
ruff: All checks passed
```

신규 11건 (DB 모델):
- User 생성/unique/full/repr (4)
- Strategy 생성/relationship/cascade/soft delete (5)
- StrategyVersion 생성+order_by/cascade (2)

회귀: 기존 216건 모두 통과 (Phase 1 코드 영향 없음).

## Issues

- ruff UP037 / UP008 등 4건 자동 수정 (TYPE_CHECKING 안의 string annotation을 일반 forward ref로 변환).
- SQLAlchemy의 expire_on_commit=False로 설정해서 commit 후 객체 attribute 접근이 가능하도록 (테스트 편의).

## Result

- 추가/수정 파일: 11개
- 설계서 07번 4~6절 모델 완성: User / Strategy / StrategyVersion
- in-memory SQLite 기반 테스트 인프라 구축 → 후속 step의 모델/서비스 테스트가 동일 패턴으로 빠르게 추가 가능
- pytest 227/227, ruff All checks passed
- Phase 1 코드와 충돌 없음 (단방향 의존: 모델 → core, db / Phase 1 코드 → 모델 미참조)

## Follow-ups

- **Step 2 (다음)**: backtest_runs + backtest_results 모델
  - strategy_snapshot_json (필수), tax_rate_json, priority_method, random_seed 등 정확성 정책 스냅샷 컬럼
  - calculate_metrics 결과를 backtest_results에 저장
- **Step 3**: trade_groups + trade_executions 모델 (07번 9~10절). Phase 1의 Portfolio가 메모리에 만든 trade_logs를 영속화.
- **Step 4**: daily_equity 모델 (07번 9절). DailyEquity dataclass와 동기화.
- **Step 5**: services 레이어 — strategy_service.py (CRUD + 버전 자동 생성), backtest_service.py (실행 → 저장 흐름).
- **Alembic 도입 (별도 step)**: create_all 대신 마이그레이션 기반. 첫 revision 생성.
- **Soft delete 쿼리 헬퍼**: `Query(Strategy).active()` 같은 메서드 또는 SQLAlchemy event listener.

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 1행 추가
- [x] Phase 상태가 변경되었으면 Phase 표 갱신 (Phase 2 진행 중)
- [x] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
