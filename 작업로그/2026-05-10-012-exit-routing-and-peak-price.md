---
date: 2026-05-10
agent: backtest-engine-developer
phase: 8 (리뷰 011 후속)
status: completed
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/05_portfolio_cash_management_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/03_condition_registry_engine_design.md
  - 리뷰/2026-05-10-011-설계서기반-PM주관-코드리뷰.md
---

# exit_position 라우팅 통일 (C1) + peak_price prev-high 정합화 (C5)

리뷰 011 Critical 2건. A1(010) — exit_position 3종 Registry 등록 — 완료 직후 in_progress 전환. C1과 C5는 둘 다 BacktestEngine + Portfolio 경계라 같은 에이전트가 한 번에 처리하면 회귀 위험을 한 번의 골든 검증으로 막을 수 있음.

## 선행 조건

- [x] 010(A1) — stop_loss / max_holding_days / trailing_stop이 ConditionRegistry에 `requires_position=True`로 등록되어 있어야 함 (이 조건이 충족돼야 Plan 시작)

## Plan

### C1) exit_position 라우팅을 ConditionRegistry로 통일 (13.3 + 03번 4절)
- [ ] `상세설계/03_condition_registry_engine_design.md` 4~5절 (ConditionRegistry.evaluate_position 시그니처) 정독
- [ ] `상세설계/13_backtest_accuracy_policy_design.md` 13.3 (갭 다운 → 갭 업 → 일중 손절 → 일중 익절 → max_holding 우선순위) 정독
- [ ] `backend/app/backtest/engine.py:_evaluate_exit_position`을 다음 흐름으로 재작성:
  - rules 순회 시 `ConditionRegistry.evaluate_position(type, position, market_row, condition)` 호출
  - 갭/일중 우선순위(13.3.1~13.3.4)는 각 포지션 조건 함수가 자체 반환 또는 우선순위 정렬 기준값(예: priority_rank)으로 표현
  - 동일 봉 손절·익절 동시 도달 시 손절 우선이라는 13.3 정책은 보존 (조건 함수 반환에서 자연 만족 또는 엔진의 마지막 결정 단계에서 명시)
  - if/elif `r["type"] == "stop_loss"` 분기 전부 제거
- [ ] take_profit / stop_loss / max_holding_days / trailing_stop 모두 동일 경로

### C5) peak_price prev-high 정합화 (13.3.5 + look-ahead 13.15)
- [ ] `backend/app/portfolio/portfolio.py:Portfolio.update_market_price` 시그니처 변경:
  - `(symbol, current_price, today_high)` 또는 별도 `update_peak_after_close(symbol, today_high)` 메서드 신설
  - `peak_price`는 `adj_high` 기반으로 갱신 (현재 adj_close)
  - 갱신은 **그날 exit_position 평가 후** (look-ahead 방지) — 13.3.5 "다음날부터 적용"
- [ ] `backend/app/backtest/engine.py:run` 루프에서 호출 순서 정렬:
  1. exit_position 평가 (peak_price = 전일까지의 high)
  2. 처리 후 update_peak (오늘 high 반영)
- [ ] trailing_stop 조건 함수가 사용하는 peak_price가 평가 시점에는 전일까지의 값인지 단위 테스트로 보장

### 공통
- [ ] pytest:
  - C1: take_profit / stop_loss / max_holding_days / trailing_stop 4종이 모두 Registry 경유로 트리거되는 통합 테스트
  - C1: 동일 봉 stop+take 동시 도달 시 stop 우선 (보수적) 골든 회귀
  - C5: trailing_stop이 활성화된 시나리오에서 peak를 종가 기반으로 잡으면 발생할 잘못된 청산이 발생하지 않는 회귀 테스트
  - C5: peak_price look-ahead 검증 (당일 high가 즉시 반영되면 안 됨)
- [ ] **Phase 1 골든 fixture 회귀** — 9지표 frozen expected가 동일하게 유지되어야 함 (구조 변경이지 정책 변경 아님)
- [ ] 전체 pytest 통과 (300건 이상 유지) + ruff

### 절대 금지
- BacktestEngine에 신호 생성 / 가격 계산 / 자금 관리 로직 추가
- StrategyEngine, ExecutionModel, CashManager 내부 변경 (다른 에이전트 영역)
- DB 모델 / API / schemas 수정 (backend-api-engineer 영역)
- ExecutionResult dataclass 도입 (별도 후속 작업 — 본 작업의 scope 밖)
- dict/set 순회 순서 의존, 시드 없는 random — 13.12 결정론

## Execution

### 수정 파일

- `backend/app/portfolio/position.py:55-63`
  - `Position.entry_price` 프로퍼티 alias 추가 → `avg_entry_price` 그대로 반환.
  - 010(A1)에서 등록한 exit_position 조건 함수가 `position.entry_price`를 읽기로 명세돼 있는데(03번 §14), `Position` 모델은 `avg_entry_price`만 노출 → 조건 함수 수정 없이 호환 유지하기 위한 가장 작은 변경.

- `backend/app/portfolio/portfolio.py:243-275`
  - `update_market_price`: peak_price 갱신 로직 제거 → current_price만 갱신.
  - `update_peak_price(symbol, today_high)` 신설 → 그날 high만 peak에 반영.
  - 정확성 정책 13.3.5 + 13.15 (look-ahead bias 방지). peak는 "전일까지의 high"여야 하므로 평가 시점에 그날 high가 들어가서는 안 됨.

- `backend/app/backtest/engine.py:1-15`
  - 모듈 docstring 갱신: 새 흐름 (update_market_price → exit_position → update_peak_price) 명시.

- `backend/app/backtest/engine.py:28-38`
  - `from app.strategy.registry import condition_registry` 추가.
  - `_EXIT_POSITION_PRIORITY` 모듈 상수 신설: `stop_loss=1, take_profit=2, trailing_stop=3, max_holding_days=4`. 정렬 키 (priority, type) 결정론.

- `backend/app/backtest/engine.py:90-130`
  - `run` 루프 호출 순서 정렬:
    1. `update_market_price(adj_close)` — current만
    2. `_evaluate_exit_position` — peak는 전일까지 high
    3. exit 발생 안 했으면 `exit_signal` 평가 (다음 시가 매도)
    4. 보유 유지 시 `update_peak_price(adj_high)` — 평가 후 peak 갱신

- `backend/app/backtest/engine.py:165-265`
  - `_evaluate_exit_position` 전면 재작성:
    - 갭 다운/업은 entry_price 기반 임계값으로만 별도 분기 (stop_rule/take_rule 검색).
    - 일중 평가는 `_EXIT_POSITION_PRIORITY` 정렬 후 `condition_registry.evaluate_position` 단일 진입점 사용.
    - 첫 트리거된 룰의 reason과 `_compute_exit_price` 결과로 청산.
    - `r["type"] == "stop_loss"` 식 if/elif 분기 전부 제거.
  - `_compute_exit_price` 신설: rule_type별 체결가 정책 한 곳 집약.
    - stop_loss → `entry * (1 - pct/100)`
    - take_profit → `entry * (1 + pct/100)`
    - trailing_stop → `peak * (1 - pct/100)`
    - max_holding_days → `adj_close`

### 테스트 수정/신설 파일

- `backend/tests/portfolio/test_portfolio.py:264-321`
  - 기존 `test_update_market_price_updates_current_and_peak` → `test_update_market_price_updates_current_only_not_peak`로 의미 갱신 (구계약 → 신계약).
  - `test_update_peak_price_unknown_symbol_noop` 신설.
  - `test_position_entry_price_alias_returns_avg_entry_price` 신설 (단일 lot + 추가매수 평단가 검증).

- `backend/tests/backtest/test_backtest_engine.py:392-580`
  - `test_exit_position_routes_through_condition_registry` — monkeypatch로 `condition_registry.evaluate_position` 스파이, 4종 모두 호출됨을 검증.
  - `test_exit_position_priority_stop_before_take_via_registry` — 동일 봉 stop+take 동시 도달 시 stop 우선 (보수적, 13.3.2).
  - `test_trailing_stop_triggers_via_registry_after_peak_made_prior_day` — 정상 트리거 시나리오 (Day3에 peak 갱신 → Day4에 트리거).
  - `test_trailing_stop_does_not_use_today_high_for_peak_lookahead` — 같은 봉에서 high 폭등 + low 하락 시 평가 시점에는 prev-high만 보아 트리거 안 됨.
  - `test_peak_updated_after_exit_evaluation_each_day` — 평가 종료 후 그날 high가 peak에 반영되는지 직접 확인.

## Tests

```
py -3.12 -m pytest backend/tests --tb=short -q
397 passed in 14.22s   (baseline 390 + 신규/수정 7건)

py -3.12 -m ruff check backend/app backend/tests
All checks passed!
```

검증 항목 매핑 (정확성 정책 13.17):

| 정책 | 검증 테스트 |
|---|---|
| 13.3.1 stop_loss/take_profit 일중 도달 | (기존) `test_intraday_stop_loss_executes_at_stop_price`, `test_intraday_take_profit_executes_at_target` — Registry 경유 후에도 동일 결과 |
| 13.3.2 동일 봉 동시 도달 stop 우선 | `test_simultaneous_take_profit_and_stop_loss_prefers_stop_loss`, `test_exit_position_priority_stop_before_take_via_registry` |
| 13.3.3/4 갭 다운/업 시가 체결 | (기존) `test_gap_down_stop_loss_executes_at_open_price`, `test_gap_up_take_profit_executes_at_open_price` |
| 13.3.5 trailing_stop peak prev-high | `test_trailing_stop_triggers_via_registry_after_peak_made_prior_day`, `test_trailing_stop_does_not_use_today_high_for_peak_lookahead`, `test_peak_updated_after_exit_evaluation_each_day` |
| 13.12 결정론 | (기존) `test_same_data_same_result_deterministic`, golden_03 10회 반복 |
| 13.15 look-ahead bias | `test_trailing_stop_does_not_use_today_high_for_peak_lookahead` |
| 03번 §4 ConditionRegistry 라우팅 | `test_exit_position_routes_through_condition_registry` (4종 모두 evaluate_position 경유) |
| Phase 1 골든 회귀 (12번 §15) | `test_golden_01_*`, `test_golden_02_*`, `test_golden_03_*`, `test_golden_04_*` 전부 pass — 9지표 frozen expected 일치 |

## Issues

- **peak_price 초기값**: `Portfolio.buy`는 새 Position의 `peak_price`를 매수가로 초기화한다. 13.3.5 ("peak_price = max(peak_price, 당일 high)")에 따르면 매수 첫날에는 peak가 매수가와 같고, 그 다음날부터 update_peak_price로 high가 누적된다. 이는 trailing_stop 시맨틱과 자연스럽게 일치 (매수 직후 trailing 손절선 = entry * (1 - pct/100)). 정책 변경 없음.

- **stop_rule / take_rule 검색이 갭 분기에서 dict 순회**: `next(r for r in rules if r["type"] == "stop_loss")`는 rules 리스트 순회 — 리스트는 입력 순서 보존이므로 결정론 안전. dict 순회 아님.

- **trigger 메타 일관성**: stop_loss/take_profit/trailing_stop의 `trigger` 옵션(`intraday_low`/`close`)이 함수 내부에서 분기되지만, 갭 분기는 항상 `intraday_*` 가정 (시가 기준). `trigger="close"`로 등록된 룰의 갭 처리는 본 작업 scope 밖 — 현재는 갭 분기를 항상 적용하므로 보수적. 13번 문서에서 별도 명시 권장 (Follow-up).

- **golden_01의 stop_loss reason 분포**: 골든 fixture는 trade_count=8, win_rate=37.5%로 stop_loss/take_profit 혼합. Registry 라우팅 후에도 동일 reason 분포 유지됨 (Phase 1 골든 4건 모두 pass).

- **engine.py의 `Any` import**: 그대로 유지 (`_evaluate_exit_position`/`_compute_exit_price`의 position 타입 힌트에 사용).

## Result

### 적용 정확성 정책 절번호

- 13.3.1~13.3.4 — 갭/일중 stop/take 우선순위 보존 (Registry 라우팅 후에도 동일 결과)
- 13.3.5 — trailing_stop peak는 전일까지 high만 사용 (`update_peak_price`는 평가 후 호출)
- 13.12 — dict 순회 미의존 (정렬 키 `(priority, type)`)
- 13.15 — look-ahead bias 차단 (peak_price 갱신 시점 분리)
- 03번 §4 — ConditionRegistry.evaluate_position 단일 진입점
- CLAUDE.md 핵심원칙 #2 — exit_position rules는 `requires_position` 메타로만 라우팅, if/elif 분기 0건

### ConditionRegistry 통일 검증

`backend/app/backtest/engine.py:_evaluate_exit_position`에서 `r["type"] == "..."` 형태의 if/elif 직접 평가 분기 모두 제거. 일중 트리거 4종 (stop_loss / take_profit / trailing_stop / max_holding_days)은 모두 `condition_registry.evaluate_position`을 통해서만 평가됨. `test_exit_position_routes_through_condition_registry` 스파이가 호출 type을 캡처해 4종 모두 검증. 갭 다운/업 분기만 entry_price 임계값 검사로 별도 처리(13.3.3/4 — 시가 체결과 별도 reason이 필요).

### peak_price prev-high 검증

- `Portfolio.update_market_price`는 current_price만 갱신.
- `Portfolio.update_peak_price`는 BacktestEngine이 exit_position 평가 종료 후에만 호출.
- `test_trailing_stop_does_not_use_today_high_for_peak_lookahead`: 같은 봉에서 high 120 + low 108 시나리오 → Day3 평가 시점 peak=110(전일까지), 손절선 104.5, low 108 > 104.5 → 트리거 없음. 위 테스트가 통과하므로 look-ahead 차단 보장.
- `test_peak_updated_after_exit_evaluation_each_day`: Day3 평가 후 peak=120으로 갱신되어 Day4 이후 적용됨을 확인.

### Phase 1 골든 fixture 회귀

`test_golden_01~04` 4건 모두 pass. 9지표 (initial_cash, final_equity, total_return_pct, mdd_pct, trade_count, open_position_count, win_rate, avg_holding_days, profit_factor) frozen expected 일치 + 첫 거래 가격/날짜 (9760/2024-01-12) 일치 + 결정론 (10회 반복) 일치.

### pytest 결과

- 신규/수정 테스트: 7건 (engine 5건 + portfolio 2건)
  - `test_exit_position_routes_through_condition_registry`
  - `test_exit_position_priority_stop_before_take_via_registry`
  - `test_trailing_stop_triggers_via_registry_after_peak_made_prior_day`
  - `test_trailing_stop_does_not_use_today_high_for_peak_lookahead`
  - `test_peak_updated_after_exit_evaluation_each_day`
  - `test_update_market_price_updates_current_only_not_peak` (기존 update_market_price+peak 단일 테스트를 새 계약에 맞춰 갱신, 그 안에 update_peak_price도 검증)
  - `test_update_peak_price_unknown_symbol_noop`
  - `test_position_entry_price_alias_returns_avg_entry_price`
- 전체: **397 passed** (baseline 390 → +7)
- ruff: All checks passed

## Follow-ups

- **engine.py 모듈 docstring의 흐름 정렬과 _maybe_buy 동선 통일**: 매수 흐름은 본 작업 scope 외라 그대로 유지. 향후 priority 알고리즘(Phase 1+)에서 universe loop가 들어올 때 순서를 다시 정리할 필요.

- **trigger="close" 옵션의 갭 처리 정책 명시 (13번 문서)**: 현재 갭 다운/업 분기는 `intraday_*` 트리거를 가정하고 항상 적용되지만, `trigger="close"`로 등록된 룰에서도 시가가 임계선을 돌파하면 갭 분기로 잡힌다. 13.3.3/4의 갭 분기가 trigger 옵션과 어떻게 상호작용하는지 13번 문서에 한 줄 추가 권장. (현재 동작은 보수적이므로 즉시 수정 필요는 아님)

- **`_EXIT_POSITION_PRIORITY` 외부 노출**: 향후 신규 exit_position 조건 등록 시 우선순위를 빠뜨리면 정렬에서 누락된다. ConditionRegistry 메타에 `exit_priority` 필드를 추가해 등록 시 함께 받는 방식이 더 깔끔. 03번 §15 등록 규칙 갱신 후 작업 가능.

- **ExecutionResult dataclass 도입**: 본 작업의 절대금지 항목으로 명시됐고, 별도 후속 작업으로 분리 (리뷰 011 다음 항목으로 추정).

- **trailing_stop 시드 정책**: 매수 첫날 peak=entry로 초기화 → 첫날 trailing은 매수가 기준 손절선과 동일. 일중 폭등 후 같은 봉 폭락 시 매수 첫날에는 trigger 안 되므로 보수적. 의도된 동작이지만 사용자 가이드(02 schema 또는 03 condition catalog)에 명시 권장.

- **13/04번 문서 갱신 필요 여부**: 본 작업은 정책 변경이 아니라 라우팅·갱신 시점 정합화이므로 문서 갱신 불필요. 단, 위 Follow-up 첫 두 항목 (trigger="close"의 갭 처리, 우선순위 메타)은 향후 작업에서 13번/03번 문서 갱신을 먼저 수행해야 함.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] `git commit`
