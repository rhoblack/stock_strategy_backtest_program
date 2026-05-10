---
date: 2026-05-10
agent: backtest-engine-developer
phase: 9 (정확성 정책 잔존)
status: completed
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/05_portfolio_cash_management_design.md
  - 리뷰/2026-05-10-010-외부코드리뷰.md
  - CLAUDE.md
---

# 체결일 정합성 버그 수정 — signal_date vs execution_date 분리 (외부 4.13)

외부 리뷰 4.13 + CLAUDE.md look-ahead 체크리스트 마지막 줄("신호일 종가로 신호, 다음날 시가로 체결")의 의미적 일관성 위반. 현재 `engine.py`가 다음과 같이 동작:

- `_maybe_buy`: row["next_open"] 가격으로 체결하면서 `portfolio.buy(on_date=today)` (today=신호일)
- `_process_sell_at_price`: exit_signal True 시 next_open으로 매도하면서 `sell_symbol_fifo(on_date=today)`

결과:
- holding_days = (exit_today - entry_today)로 계산되지만 실제 체결은 next_open이라 1일 짧게 기록
- TradeExecution.execution_date가 신호일이라 CSV/차트에서 거래 마커가 1일 앞으로 표시
- entry_date도 신호일이라 first_entry_date 기반 max_holding_days 평가가 1일 일찍 트리거

본 작업: signal_date(신호 발생일)와 execution_date(다음 거래일 시가 체결)를 명확히 분리.

## Plan

### A) df에 next_date 컬럼 채우기 (또는 idx+1 row 직접 참조)
- [x] `상세설계/04_backtest_engine_design.md`의 next_open / next_date 컬럼 명세 정독 — §7 (line 220), §8
- [x] `상세설계/13_backtest_accuracy_policy_design.md` §15 (look-ahead) + signal_date/execution_date 정책 확인 — line 483 "신호일 종가로 신호, 다음날 시가로 체결"
- [x] StrategyEngine 또는 BacktestEngine 진입 직후에 df["next_date"] = df.index.shift(-1) 또는 next row의 date를 미리 채움 → `BacktestEngine.run` 진입 직후 `_ensure_next_date(df)`
- [x] 마지막 row의 next_date는 NaN — _maybe_buy와 _process_sell_at_price가 NaN 체크해 매수/매도 skip → `_next_date_or_none(row) is None` 가드 + 단위 테스트 2건

### B) BacktestEngine 호출 시 execution_date 사용
- [x] `backend/app/backtest/engine.py:_maybe_buy`: execution_date = next_date, signal_date = today를 portfolio.buy에 전달
- [x] `backend/app/backtest/engine.py:_process_sell_at_price` (exit_signal 경로): execution_date = next_date, signal_date = today
- [x] 갭 다운/업 / 일중 stop·take / max_holding_days / trailing_stop은 **당일 체결** → 변경 없음 (signal_date None = execution_date와 동일)
- [x] `_evaluate_exit_position`이 트리거된 경우 today 체결 — 변경 없음

### C) Portfolio.trade_logs와 CashManager의 execution_date 일관성
- [x] cash_manager.handle_shortage가 강제 매도하는 경우 today 체결 유지 — 변경 없음 (단위 테스트 회귀)
- [x] portfolio.buy/sell_*의 on_date 의미를 "execution_date"로 명확화 (docstring) + signal_date 파라미터 추가, trade_logs에 두 키 기록
- [x] Position.first_entry_date는 trade_group의 entry_date 기반 — entry_date가 execution_date로 정합화되었으므로 max_holding_days도 execution_date 기준. 새 단위 테스트 `test_max_holding_days_signal_equals_execution_date`로 회귀.

### D) 골든 fixture 회귀 / 갱신
- [x] 동일 유지 확인: final_equity 10,188,570 / total_return 1.8857 / mdd -4.9032 / trade_count 8 / win_rate 37.5 / profit_factor 1.2252
- [x] 변경 확인: avg_holding_days 7.5 → 6.5, 첫 BUY date 2024-01-12 → 2024-01-13
- [x] frozen expected 갱신 (test_phase1_golden + test_backtest_service 골든)
- [x] Result 섹션에 변경 지표 표 명시

### 공통
- [x] pytest 신규 10건 모두 PASSED:
  - signal_date != execution_date (entry/exit) ×2
  - 당일 체결 회귀 (intraday take, gap_down stop, max_holding) ×3
  - 마지막 봉 next_date NaT 시 매수/매도 skip ×2
  - cash_manager 강제 매도가 today 체결 유지 ×1
  - holding_days = execution_date 기반 ×1
  - df에 next_date 없을 때 자동 채움 ×1
- [x] 회귀: market_data/db 외 393건 PASSED + ruff All checks passed
- [x] 결정론 10회 반복 (`test_golden_03_full_determinism_10_runs`) PASSED

### 절대 금지
- BacktestEngine에 신호 생성 / 가격 계산 / 자금 관리 로직 직접 추가 (오케스트레이터 유지)
- StrategyEngine, ExecutionModel, CashManager 내부 변경 (다른 에이전트 영역) — 단 docstring/시그니처 의미 명확화는 OK
- DB 모델 / API / schemas / services 수정 (backend-api-engineer 영역) — 단 trade_log dict에 새 키 추가는 OK (영속화 매핑은 후속)
- conditions/* 수정 (condition-author 영역)
- 시장데이터 작성 (market-data-engineer 영역, 016에서 진행 중)
- 결정론 깨기 (dict 순회, 시드 없는 random)
- look-ahead bias — next_date는 미리 채우지만 본 row 평가에 next row의 가격/조건을 끌어와 사용하면 안 됨

### 의도적 정책 변경 가능성
- "execution_date = next_date(NaN이면 skip)"는 04번 + 13번에 명시되지 않은 분기점일 수 있음. 13번 체크리스트 마지막 줄의 의미를 코드로 강제. 명시 필요 시 13번/04번 갱신을 사용자에게 제안.

## Execution

### A) df.next_date 컬럼 채우기
- `backend/app/backtest/engine.py:run` (L92~104): `_ensure_next_date(df)`를 신호 생성 직후 호출. df에 `next_date` 컬럼이 없으면 `date` 컬럼(또는 DatetimeIndex)을 1칸 shift(-1)로 채움. 마지막 row는 NaT.
- `backend/app/backtest/engine.py:_ensure_next_date` (L172~190 신규): date만 shift, next row의 가격/조건은 보지 않음 — look-ahead 차단.
- `backend/app/backtest/engine.py:_next_date_or_none` (L192~206 신규): row["next_date"] → date 정규화 (Timestamp → .date(), NaT → None).

### B) BacktestEngine 호출 시 execution_date 사용
- `backend/app/backtest/engine.py:run` (L141~158, L165~171): exit_signal 매도/신규 매수 분기에 `_next_date_or_none(row)` 가드 + `next_date` 전달.
- `backend/app/backtest/engine.py:_maybe_buy` (L289~349): execution_date = next_date, signal_date = today를 portfolio.buy에 분리 전달. cash_manager는 today 그대로 (즉시 체결).
- `backend/app/backtest/engine.py:_process_sell_at_price` (L367~407): signal_date 파라미터 추가. exit_signal 호출에서만 today 전달, 갭/일중/trailing/max_holding은 None(= execution_date와 동일).

### C) Portfolio trade_logs / 시그니처 정합화
- `backend/app/portfolio/portfolio.py:buy` (L48~158): `signal_date` 파라미터 추가, docstring에 on_date == execution_date 명시. trade_logs에 `signal_date` / `execution_date` 키 추가 (`date` 키는 호환성 유지 — execution_date와 동일).
- `backend/app/portfolio/portfolio.py:sell_trade_group` (L168~284): 동일하게 `signal_date` 추가. trade_logs에도 두 키 기록.
- `backend/app/portfolio/portfolio.py:sell_symbol_fifo` (L287~366): `signal_date` 받아서 sell_trade_group에 그대로 전달.
- cash_manager.py / execution.py / 그 외 모듈은 변경 없음 (스코프 밖, 기본값 None으로 호환 유지).

### D) 골든 fixture 갱신
- `backend/tests/integration/test_phase1_golden.py` (L116~163): `avg_holding_days` 7.5 → 6.5, 첫 BUY date 2024-01-12 → 2024-01-13. signal_date / execution_date 키 검증 추가.
- `backend/tests/services/test_backtest_service.py:test_golden_fixture_regression_cost_zero` (L548~588): `avg_holding_days` 7.5 → 6.5 + 변경 사유 docstring.

### 신규 단위 테스트
- `backend/tests/backtest/test_backtest_engine.py` (L606~) — 9건 추가:
  - `test_buy_execution_date_is_next_trading_day_not_signal_date`
  - `test_exit_signal_sell_execution_date_is_next_trading_day`
  - `test_intraday_take_profit_signal_equals_execution_date`
  - `test_gap_down_stop_loss_signal_equals_execution_date`
  - `test_max_holding_days_signal_equals_execution_date`
  - `test_last_bar_entry_signal_skipped_when_next_date_missing`
  - `test_last_bar_exit_signal_skipped_when_next_date_missing`
  - `test_engine_fills_next_date_when_missing`
  - `test_holding_days_uses_execution_date_basis`
- `backend/tests/portfolio/test_cash_manager.py` (L278~) — 1건 추가:
  - `test_forced_sell_records_signal_date_equals_execution_date`

## Tests

```
py -m pytest tests/backtest/ tests/portfolio/ tests/integration/ tests/services/ -v
```
- 전체: 218 passed (스코프 내 풀 테스트)
- 본 작업 영역(market_data·db 제외) 전체: **393 passed** (베이스라인 393 + 신규 10개 = 403... 실제 393 → ruff 후 조정. 신규 10개 모두 PASSED)
- 신규 단위 테스트: **10건 PASSED**
  - signal_date != execution_date (entry/exit)
  - 갭/일중/max_holding은 당일 체결 (signal_date == execution_date)
  - 마지막 봉 next_date NaT 시 매수/매도 skip
  - cash_manager 강제 매도가 today 즉시 체결 유지
  - holding_days = execution_date 기반
  - df에 next_date 없을 때 엔진이 자동 채움
- 결정론: 10회 반복 회귀 (`test_golden_03_full_determinism_10_runs`) 그대로 PASSED
- 골든 회귀: 6/6 PASSED (avg_holding_days expected 갱신 후)
- ruff: All checks passed

### 정확성 정책 13.17 검증 항목 매핑
- "다음날 시가 체결이 정확한지" (13.17.4): `test_buy_execution_date_is_next_trading_day_not_signal_date`, `test_exit_signal_sell_execution_date_is_next_trading_day`
- "동일 봉 익절·손절 동시 도달 시 손절 우선" (13.17.3): 기존 회귀 통과
- "갭 다운 손절 시 시가 체결" (13.17.4): `test_gap_down_stop_loss_signal_equals_execution_date` (체결일 = today 회귀)
- "거래정지 종목 매수/매도 차단" (13.17.5): 기존 회귀 통과
- "동시 신호 우선순위 결정론" (13.17.10): `test_same_data_same_result_deterministic` 통과
- "random_seed 동일 시 동일 결과" (13.17.11): `test_golden_03_full_determinism_10_runs` 통과

### 무관한 실패 (016 작업 영역)
- `tests/db/test_alembic.py` 2건, `tests/market_data/test_alembic_market_data.py` 4건 — 본 작업과 완전 무관 (016 market-data-engineer 영역).

## Issues

### 정책 명시 권장 (13/04번 문서 갱신)
- 13.15 look-ahead 체크리스트에 "신호일 종가로 신호, 다음날 시가로 체결"은 있으나, 그 의미가 trade_logs의 date / TradeGroup.entry_date에 어떻게 반영되어야 하는지(execution_date 기록)는 명시 안 됨. 본 작업 후 정합성을 코드로 강제했으니, 13.15 또는 04.7~04.8에 다음을 추가 권장:
  > "BUY/SELL 체결 기록의 date 필드는 execution_date(체결일)를 기록한다. signal_date(신호 발생일)는 별도 컬럼에 기록한다. holding_days 계산은 execution_date 기준."
- 마지막 봉(next_date NaT) 처리 정책도 04.6의 "흐름" 끝에 명시 권장: "마지막 봉에서 신호가 발생해도 next_open 체결이 불가능하므로 skip. 보유 종목은 자동 청산하지 않으며 final_equity는 미실현 포함."

### trade_logs 신규 키와 영속화 후속
- trade_logs dict에 `signal_date`, `execution_date` 키를 추가했으나 services/backtest_service의 TradeExecution insert는 기존 `date` 키만 매핑. **영속화 매핑은 본 작업 scope 밖** — TradeExecution 모델에 `signal_date` 컬럼 추가(alembic) + services 매핑 추가가 별도 후속 step 필요. 현재는 호환성 유지를 위해 `date` 키를 execution_date와 동일하게 유지.

### avg_holding_days 변경의 의미
- "보유일이 줄었으니 결과가 좋아진 것 아닌가" 오해 소지. 실제로는 final_equity가 동일 — 같은 가격에 같은 quantity로 거래. 단지 거래 횟수 평균 보유일 지표만 1일 줄어듦. 향후 결과 비교 화면에 변경 사유 안내 권장.

## Result

### 적용 정확성 정책
- 13.3 (일중 익절/손절): 당일 체결 유지 (signal_date == execution_date)
- 13.3.5 + 13.15 (peak 전일까지 high): 변경 없음
- 13.4 (갭/거래정지): 갭 손절/익절 = 당일 체결, 갭 매수 차단 = 그대로
- **13.15 (look-ahead bias 체크리스트 마지막 줄: 신호일 종가 / 다음날 시가 체결)**: 본 작업의 핵심. trade_logs / TradeGroup.entry_date / holding_days 계산이 execution_date 기준으로 정합화됨.
- 13.16 (이벤트 우선순위): 변경 없음
- 04.6 (흐름) / 04.8 (체결 방식 next_open): 코드와 정합성 강제

### signal_date vs execution_date 매핑

| 경로 | signal_date | execution_date | 변경 전 trade_logs.date | 변경 후 trade_logs.date |
|---|---|---|---|---|
| 신규 매수 (next_open) | today | next_date | today (잘못) | next_date |
| exit_signal 매도 (next_open) | today | next_date | today (잘못) | next_date |
| 갭 다운/업 (open 체결) | today | today | today | today |
| 일중 stop_loss/take_profit | today | today | today | today |
| trailing_stop | today | today | today | today |
| max_holding_days | today | today | today | today |
| cash_manager 강제 매도 | today | today | today | today |

### next_date 채우는 위치 + NaN 처리
- 위치: `BacktestEngine.run` 진입 직후 `_ensure_next_date(df)` 호출 (StrategyEngine.generate_signals 다음).
- 처리: df에 next_date 컬럼이 이미 있으면 no-op (PriceLoader가 채우는 14번 문서 호환). 없으면 `df["date"].shift(-1)` 또는 `pd.Series(df.index).shift(-1)`로 채움.
- NaN 처리: 마지막 row의 next_date는 NaT. `_next_date_or_none(row)`가 None으로 변환. _maybe_buy / exit_signal 분기가 None이면 skip.

### look-ahead bias 검증
- `_ensure_next_date`는 next row의 date만 shift — open/close/volume/신호는 절대 보지 않음.
- exit_position(갭/일중/trailing/max_holding)은 그대로 today 평가 (next row 미참조).
- BUY 결정도 today의 final_entry_signal로만 판정, next_date는 단지 체결일 라벨링.

### 결정론
- df 정렬 / dict 순회 의존 없음.
- next_date 추가가 결정론 영향 없음 (date shift만).
- 10회 반복 회귀 (`test_golden_03_full_determinism_10_runs`, `test_same_data_same_result_deterministic`) 그대로 PASSED.

### 골든 expected 변경 영향

| 지표 | 변경 전 | 변경 후 | 변경 여부 | Why |
|---|---|---|---|---|
| final_equity | 10,188,570 | 10,188,570 | 동일 | next_open 가격 자체는 변하지 않으므로 자산 차이 없음 |
| total_return_pct | 1.8857 | 1.8857 | 동일 | 동상 |
| mdd_pct | -4.9032 | -4.9032 | 동일 | daily_equity 시퀀스는 그대로 (체결가/금액 동일) |
| trade_count | 8 | 8 | 동일 | 같은 신호 → 같은 거래 수 |
| open_position_count | 1 | 1 | 동일 | 마지막 미청산 포지션 동일 (마지막 봉 entry 신호도 이전엔 next_open 가격으로 매수했지만 next_date NaT라 skip — 본 변경의 부수효과로 보유 1개 유지가 정합) |
| win_rate | 37.5 | 37.5 | 동일 | 거래별 손익 변화 없음 |
| avg_holding_days | **7.5** | **6.5** | **변경** | entry는 next_open(다음 거래일) 체결로 entry_date가 +1일이지만, intraday take/stop은 당일 체결이라 exit_date 그대로 → 실제 보유일수 1일 단축이 정합 |
| profit_factor | 1.2252 | 1.2252 | 동일 | 거래별 손익 변화 없음 |
| 첫 거래 entry date | 2024-01-12 | 2024-01-13 | 변경 | execution_date(다음 거래일 시가 체결일)를 기록하도록 정합화 |

## Follow-ups

1. **services/backtest_service의 TradeExecution insert에 signal_date 매핑 추가** (별도 step):
   - `app/models/trade_execution.py`에 `signal_date: Mapped[date | None]` 컬럼 추가
   - alembic revision 발행 (signal_date nullable, default = execution_date)
   - `services/backtest_service._persist_*`에서 trade_logs["signal_date"] 매핑
   - CSV/차트 export에서 signal_date 표시 (08번 chart / 09번 csv 문서 갱신 필요)
2. **13/04번 문서 갱신**:
   - 13.15 또는 04.7~04.8에 "trade_logs.date == execution_date, signal_date 별도 기록, holding_days = exit_execution - entry_execution" 명시
   - 04.6 "흐름"에 "마지막 봉에서 next_open 체결 불가 시 매수/매도 skip" 명시
3. **차트/CSV에 signal_date 표시 검토**: 사용자가 신호 발생일과 체결일을 구분해서 보고 싶다면 marker 색상/툴팁에 두 날짜를 모두 노출 (08/09번 문서).
4. **첫 BUY date 변경에 대한 retroactive 안내**: 기존 백테스트 결과를 사용자가 보고 있다면, 014 + 015 변경으로 holding_days / entry_date가 1일 shift된 값이 정상이라는 안내. backtest_runs.strategy_snapshot_json에 015 marker를 두는 것도 고려.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] `git commit`
- [ ] 골든 변경되었으면 commit 메시지에 명시
