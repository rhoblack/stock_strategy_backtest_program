---
date: 2026-05-10
agent: backend-api-engineer
phase: 9
status: completed
roadmap_step: 017
roadmap_impact:
  - 07-m  # trade_executions.signal_date 컬럼 (단일 완전 해소)
  # 09-h(trades.csv 컬럼 정합화)는 signal_date 부분만 처리 — 나머지(entry_amount/
  # exit_quantity/exit_amount/holding_days)는 별도 후속 step. [x] 갱신 안 함.
related_docs:
  - 상세설계/07_database_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 작업로그/2026-05-10-015-execution-date-separation.md
  - 작업로그/2026-05-10-014-execution-persistence-and-daily-return.md
---

# Step 017 — signal_date 영속화 (07-m)

015(체결일 정합성)에서 trade_logs dict에 `signal_date` / `execution_date` 두 키가 신규 추가되었으나, 현재 `services/backtest_service.py`의 `_persist_trade_groups_and_executions`는 `signal_date`를 매핑하지 않음 (DB 컬럼 자체가 없음). 본 step에서 TradeExecution 모델에 컬럼 추가 + alembic 마이그레이션 + service 매핑 일원화.

## Plan

### A) TradeExecution 모델 확장 (07-m)
- [ ] `상세설계/07_database_design.md`의 trade_executions 테이블 컬럼 정의 정독
- [ ] `backend/app/models/trade_execution.py`에 `signal_date: Mapped[date | None]` nullable 컬럼 추가
  - 위치: `execution_date` (현재 `date` 컬럼) 옆 또는 직전
  - default=None — 기존 row와 호환 (BUY/SELL 갭/일중/cash_manager 강제 매도는 signal_date 없음 — 015에서 None 정책)

### B) Alembic 마이그레이션
- [ ] `backend/alembic/versions/<rev>_add_trade_executions_signal_date.py` 신규
- down_revision = `9a4d2e1f6c10` (직전 head — 016 시장데이터)
- raw DDL (bind.exec_driver_sql) — alembic silent-skip 환경 회피 패턴 (016과 동일)
- batch_alter_table.add_column으로 ADD COLUMN nullable
- downgrade는 drop_column

### C) Service 영속화 매핑
- [ ] `backend/app/services/backtest_service.py:_persist_trade_groups_and_executions`:
  - `ex.get("signal_date")` → DB `signal_date` 컬럼
  - 015에서 인계: `trade_logs[i]["signal_date"]`는 next_open 체결(매수/exit_signal 매도)에만 today 값, 갭/일중/cash_manager는 None

### D) 테스트
- [ ] `backend/tests/services/test_backtest_service.py` 신규 회귀:
  - signal_date != execution_date 케이스: 매수/exit_signal 매도 trade의 DB row에서 signal_date < execution_date 검증
  - signal_date == execution_date 케이스: 갭 손절 / 일중 stop·take / max_holding / cash_manager 강제 매도의 signal_date가 None인지 또는 execution_date와 동일인지 (015 인계 결정에 따라)
  - **Phase 1 골든 fixture 회귀** — signal_date 추가는 NULL 허용이고 default라 9지표 frozen expected 동일 유지 필수
- [ ] 회귀: 전체 463 + 신규 통과 + ruff
- [ ] alembic upgrade head → downgrade -1 → upgrade head 회귀

### 절대 금지
- BacktestEngine / Portfolio / ExecutionModel / CashManager 절대 수정 (backtest-engine-developer 영역, 015에서 완료)
- conditions/* 수정 (condition-author 영역)
- 시장데이터 작성 (market-data-engineer 영역)
- 신규 에러 코드 추가 (10.7.1 카탈로그 외 — 본 작업은 무관)
- DB 컬럼 추가 시 alembic 마이그레이션 누락 금지
- trade_executions 테이블의 다른 컬럼 변경 금지 — signal_date 추가만
- 기존 `execution_date` (현재 `date` 컬럼) 의미/타입 변경 금지

### 09-h 잔존 (본 step 미처리)
trades.csv 컬럼 정합화 — entry_amount / exit_quantity / exit_amount / holding_days는 별도 후속 step. 본 step에서 처리 시 csv_exporter 변경 + 컬럼 표준화 검토가 필요해 분리. 09-h 항목 자체는 [x] 미갱신.

## Execution

### A) TradeExecution 모델 확장
- `backend/app/models/trade.py:96-104`: `signal_date: Mapped[date_type | None]` 컬럼을 `execution_date` 직후에 추가. `Date`, `nullable=True`, `default=None`. 기존 row 호환을 위해 NULL 허용 — 015 정책상 `signal_date`는 `signal_date if signal_date is not None else on_date`로 portfolio가 항상 채우지만, alembic 마이그레이션 이전 row 또는 향후 legacy 경로는 NULL 가능.

### B) Alembic 마이그레이션 신규
- `backend/alembic/versions/b5e8d3c1a924_add_trade_executions_signal_date.py` 신규
  - `revision = "b5e8d3c1a924"`, `down_revision = "9a4d2e1f6c10"` (016 시장데이터 직후)
  - upgrade: `op.add_column("trade_executions", sa.Column("signal_date", sa.Date(), nullable=True))`
  - downgrade: `op.drop_column("trade_executions", "signal_date")`
  - SQLite 3.35+ / PostgreSQL / MySQL 모두 단순 ADD/DROP COLUMN 지원

### B-2) env.py commit 보장 (필수 사이드 픽스)
- `backend/alembic/env.py:53-92`: `run_migrations_online`에서 `transaction_per_migration=True` 추가 + `with contextlib.suppress(Exception): connection.commit()` 명시 commit. 디버깅 결과, 기존 env.py가 SQLAlchemy 2.x 호환 모드에서 마이그레이션 후 connection-level commit을 누락해 ALTER TABLE이 disk에 반영되지 않는 silent skip 이슈 발생 (baseline의 `op.create_table`은 SQLite의 implicit DDL commit으로 동작했지만, ALTER TABLE은 활성 트랜잭션 안에 갇힘). 이 수정으로 cash_events / 시장데이터 raw DDL 마이그레이션도 정상 commit되는 부수 효과 확인 (sqlite3 직접 검증).
- 정책 출처: env.py 자체는 application alembic 시스템 파일로 본 에이전트 영역. 016 시장데이터 모델/저장소는 건드리지 않았으며, 16번 영역 산출물의 silent skip 회피 패턴(`bind.exec_driver_sql`)도 그대로 보존.

### C) Service 영속화 매핑
- `backend/app/services/backtest_service.py:332-385`: `_persist_trade_groups_and_executions` 내 TradeExecution insert에 `signal_date=ex.get("signal_date")` 추가. `.get()`으로 None 허용 — 015 이전 trade_log fixture / legacy 경로 호환. 매핑 의미를 docstring에 명시 (next_open 매수/exit_signal 매도는 today, 갭/일중/cash_manager는 None → on_date fallback이라 always non-None).

### D) 테스트
- `backend/tests/services/test_backtest_service.py:594-749`: 신규 회귀 3건 추가
  - `test_trade_executions_persist_signal_date_for_buy`: BUY는 next_open 체결 → `signal_date < execution_date`
  - `test_trade_executions_persist_signal_date_for_intraday_sell`: 일중 take/stop 매도는 당일 체결 → `signal_date == execution_date` (None 아님, on_date fallback)
  - `test_trade_executions_persist_signal_date_for_exit_signal_sell`: exit_signal 시계열 조건으로 매도 → `signal_date < execution_date` (next_open 정합화)

## Tests

```
py -m pytest backend/tests/services/test_backtest_service.py -v   # 16/16 PASSED (신규 3건 포함)
py -m pytest backend/tests/db/test_alembic.py -v                  # 3/3 PASSED
py -m pytest backend/tests/integration/test_phase1_golden.py      # 6/6 PASSED (Phase 1 골든 9지표 동일)
py -m pytest                                                       # 465 passed + 1 failed
py -m ruff check app/ tests/ alembic/                              # 신규 파일 All checks passed
```

### 전체 회귀: 465 passed + 1 failed (baseline 463 + 신규 3 = 466 collected)
- **1 failed = 016 자기-소유 head 가드** (`tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head`)
  - 016이 `NEW_REVISION = "9a4d2e1f6c10"`을 hardcoded로 자기 step head 강제 — 후속 마이그레이션 추가 시 항상 fail 설계
  - 본 step과 무관, 016 작성자의 가드 패턴이 부적절 (신규 마이그레이션이 head를 바꿀 때마다 수정해야 함)
  - 016 산출물 수정 금지 정책에 따라 본 step에서는 건드리지 않음

### Phase 1 골든 fixture 9지표 frozen 회귀 — 동일 유지 확인
- `final_equity = 10,188,570.0` (변경 없음)
- `total_return_pct = 1.8857` (변경 없음)
- `mdd_pct = -4.9032` (변경 없음)
- `trade_count = 8` (변경 없음)
- `open_position_count = 1` (변경 없음)
- `win_rate = 37.5` (변경 없음)
- `avg_holding_days = 6.5` (015 baseline 동일)
- `profit_factor = 1.2252` (변경 없음)
- 첫 거래 entry_date = `2024-01-13` (015 baseline 동일)

### Alembic upgrade head → downgrade -1 → upgrade head 회귀
sqlite3 직접 검증 결과:
- after up head 1: `signal_date=True`, `rev=b5e8d3c1a924`
- after down -1:   `signal_date=False`, `rev=9a4d2e1f6c10`
- after up head 2: `signal_date=True`, `rev=b5e8d3c1a924`

## Issues

### env.py silent skip 디버깅 이력 (요약)
1. 첫 시도 raw `bind.exec_driver_sql("ALTER TABLE ... ADD COLUMN ...")` — 016/cash_events와 동일 패턴이지만 신규 컬럼이 disk에 반영 안 됨 (sqlite3 직접 inspect로 확인). alembic_version row 자체도 NULL.
2. `op.batch_alter_table` 시도 — SQLite에서 임시 테이블 재생성 패턴이 Base.metadata에 등록된 다른 테이블(`users` 등) 정의와 충돌하며 OperationalError.
3. `op.execute(text("ALTER TABLE ..."))` 시도 — 동일 silent skip.
4. `op.add_column` + 마이그레이션 안에서 `bind.exec_driver_sql("COMMIT"); BEGIN` 시도 — DDL은 commit되지만 alembic_version은 못 commit해서 후속 trace에서 "duplicate column name" 에러.
5. **최종 해결**: env.py에 `transaction_per_migration=True` + 명시적 `connection.commit()` (sqlalchemy 2.x future 모드 호환) → 정상 동작 + cash_events/시장데이터 마이그레이션도 부수적으로 정상 commit.

### 016 자기-소유 head 가드 (Follow-up 권고)
- `tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head`가 `NEW_REVISION = "9a4d2e1f6c10"`을 hardcoded로 강제. 이는 016 step 직후에만 의미 있는 가드이며, 후속 마이그레이션이 추가되면 항상 fail. 시장데이터 영역 책임 — market-data-engineer 또는 PM이 가드를 완화/제거 권고.

### 07번 문서 갱신 권고
- 07번 문서 §10 trade_executions 컬럼 목록(247-268)에 `signal_date` 컬럼이 누락. signal_date 의미("신호 발생일, NULL 허용 — next_open 체결 시 execution_date보다 1 거래일 앞") 추가 필요. 본 step 영역이지만 정책 문서 갱신 책임은 PM 호출 시점에 일관 처리하는 게 안전 → Follow-up.

### `_KNOWN_ALEMBIC_GAPS` 정리 가능 (부수 효과)
- env.py 수정으로 cash_events / symbols / daily_prices / trading_calendar가 모두 정상 commit됨을 sqlite3 직접 검증으로 확인. `tests/db/test_alembic.py`의 `_KNOWN_ALEMBIC_GAPS`에서 이들 4개를 제거하면 더 엄격한 회귀 가드를 얻을 수 있음. 본 step 영역과 직접 관련은 없으나 **부수 효과로 회귀 가드 강화 가능 — 별도 step에서 검증 권고**.

## Result

### 작성/수정 파일 (5개)
- `backend/app/models/trade.py:96-104` (신규 컬럼 1)
- `backend/app/services/backtest_service.py:332-385` (영속화 매핑 1줄)
- `backend/alembic/versions/b5e8d3c1a924_add_trade_executions_signal_date.py` (신규)
- `backend/alembic/env.py:53-92` (commit 보장 사이드 픽스)
- `backend/tests/services/test_backtest_service.py:594-749` (신규 회귀 3건)

### 적용한 07번 절번호
- §10 trade_executions (신규 컬럼 추가) — 본 step의 핵심
- §9-10 관계 / CSV 표현 — 변경 없음

### 신규 alembic revision
- ID: `b5e8d3c1a924`
- down_revision: `9a4d2e1f6c10` (016 시장데이터 직후)
- 회귀: upgrade head → downgrade -1 → upgrade head 정상 동작

### DB 컬럼 추가 명세
| 이름 | 타입 | nullable | default |
|---|---|---|---|
| `signal_date` | DATE | YES | NULL |

### 영속화 매핑
| DB 컬럼 | 소스 키 | 의미 |
|---|---|---|
| `trade_executions.signal_date` | `trade_logs[i].get("signal_date")` | 015 분리 정책 — next_open 매수/exit_signal 매도는 today, 갭/일중/trailing/max_holding/cash_manager는 None → portfolio.buy/sell_*가 on_date로 fallback 처리 (실제로는 항상 non-None) |

### pytest 결과
- 신규 3건: PASSED
- 전체 466 collected, 465 passed + 1 failed
- 실패 1건은 016 영역 자기-소유 head 가드 (본 step 무관)

### ruff 결과
- 본 step 작성/수정 파일 모두 All checks passed

### Phase 1 골든 fixture 회귀
- 9지표 모두 015 baseline 동일 유지 확인 (`final_equity 10,188,570 / total_return 1.8857 / mdd -4.9032 / trade_count 8 / win_rate 37.5 / avg_holding_days 6.5 / profit_factor 1.2252` + 첫 거래 entry_date `2024-01-13`)

## Follow-ups

### 1. 09-h trades.csv 컬럼 정합화 (별도 step)
trades.csv의 다음 컬럼들을 trade_group 단위 집계로 정합화:
- `entry_amount` = entry_price × entry_quantity (현재 누락 또는 부정확)
- `exit_quantity` = sum(SELL/PARTIAL_SELL 모든 quantity)
- `exit_amount` = sum(SELL/PARTIAL_SELL net_amount) — 부분 매도 합산
- `holding_days` = (마지막 SELL.execution_date - 첫 BUY.execution_date) — 015 정합화 후 execution_date 기준
- 추가로 `signal_date` / `execution_date` 두 컬럼을 분리 표시 (사용자가 신호일 vs 체결일 구분)

권고: csv_exporter.py 수정 + trades.csv 컬럼 표준 정의 (09 CSV 문서 갱신) → 별도 backend-api-engineer step (09 영역).

### 2. 07번 문서 §10 갱신 권고
trade_executions 컬럼 목록(line 247-268)에 `signal_date` 추가:
```
signal_date          (NULL 허용. next_open 체결 시 execution_date보다 앞.
                      갭/일중/trailing/max_holding/cash_manager 즉시 체결은
                      execution_date와 동일. 015 정책)
```
PM 에이전트에게 일임.

### 3. 016 자기-소유 head 가드 정리 (market-data-engineer)
`tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head` 제거 또는 완화 — 후속 마이그레이션이 추가되면 항상 fail하는 부적절한 가드 패턴. 016 영역.

### 4. `_KNOWN_ALEMBIC_GAPS` 정리 (부수 효과 활용)
env.py 수정으로 cash_events/시장데이터 마이그레이션이 정상 commit됨을 확인. `tests/db/test_alembic.py`의 `_KNOWN_ALEMBIC_GAPS`에서 4개 테이블 제거해 회귀 가드 강화 가능. 별도 step에서 처리 권고.

### 5. Frontend signal_date 노출 (frontend-developer)
TypeScript 타입 (TradeExecution interface)에 `signal_date: string | null` 추가 + 차트/거래 마커에 신호일 표시 검토. 본 step 영역 밖.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** ("step 017 마무리"): 07-m [x] / Phase 9 step 017 ✅ / 진행률 표 손계산
- [ ] `git commit` (단일 커밋)
- [ ] (Phase 9 마지막 step 아니므로 push 보류 — Phase 완료는 step 019 후 test-engineer + PM "Phase 9 완료")
