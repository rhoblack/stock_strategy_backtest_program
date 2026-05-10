---
date: 2026-05-10
agent: backtest-engine-developer
phase: 10
status: completed
roadmap_step: 023
roadmap_impact:
  - 04-n  # event_log
  - 04-o  # 상한가/하한가 / 거래정지 / 상장폐지 강제 매도
  - 13-p  # 거래량 0 / 한가 / 거래정지 event_log
  - 13-q  # 상한가/하한가 / 상장폐지 강제 매도
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 작업로그/2026-05-10-022-position-limits.md
  - 작업로그/2026-05-10-019-universe-selector.md
---

# Step 023 — event_log + 강제 매도 (04-n + 04-o + 13-p + 13-q) — Phase 10 마지막

Phase 10 마지막 step. 020·021·022에서 도입된 skip 사유들을 모두 event_log에 기록 + 거래정지/상한가/하한가/상장폐지 강제 매도 정책 도입. 완료 후 test-engineer Phase 10 검증 → ship-go → push.

## Plan

### A) EventLog 구조 (04-n)
- [ ] `상세설계/04_backtest_engine_design.md` event_log 절 정독 (있으면)
- [ ] BacktestEngine.event_log 속성 신설: `list[dict]` (cash_events 패턴 따름)
- [ ] 표준 event 사유 코드:
  - skip_no_volume (거래정지)
  - skip_limit_up_buy (상한가 매수 차단)
  - skip_limit_down_sell (하한가 매도 차단)
  - skip_max_positions (022)
  - skip_max_daily_entries (022)
  - skip_daily_buy_budget (022)
  - skip_max_gap (기존 max_gap_pct_for_entry)
  - force_sell_delisted (상장폐지)
  - force_sell_no_volume_consecutive (선택 — 연속 거래정지 N일 강제 매도)
- 각 event 필드: date / symbol / event_type / reason / detail (dict — 후보별 추가 정보)

### B) 거래정지 (volume==0) event_log 기록 (13-p)
- [ ] 020의 기존 skip_no_volume 분기에 event_log 추가
- 후보 수집 단계 (`_collect_entry_candidates`): volume==0인 후보 → event_log + 후보 제외
- 보유 평가 단계: volume==0 봉에서 exit_position 평가는 skip하되 event_log 기록

### C) 상한가/하한가 처리 (04-o, 13-q)
- [ ] BacktestConfig 신규 필드:
  - `allow_buy_limit_up: bool = False` (default 보수: 상한가 매수 차단)
  - `allow_sell_limit_down: bool = False` (default 보수: 하한가 매도 차단)
- 상한가 판정 정책 (Plan에서 결정): `next_open == today_high` 또는 시가가 전일 종가 대비 +29.x% (KOSPI/KOSDAQ 30%) — 단순화: today row의 `is_limit_up` / `is_limit_down` 컬럼 가정 (PriceLoader 미구현이면 단순 계산 fallback)
- 본 step에서는 단순 fallback: `daily_price.high == daily_price.low and daily_price.close > prev_close * 1.27` 형태 — 정확한 정책은 Issues에 명시
- 매수 차단: 신규 매수 시 next_open이 상한가 → skip + event_log
- 매도 차단: exit_signal/exit_position 매도 시 next_open이 하한가 → skip + event_log

### D) 상장폐지 강제 매도 (04-o, 13-q)
- [ ] universe_resolver 또는 별도 인터페이스로 today에 폐지된 종목 감지
- 보유 포지션이 today 폐지일 → 강제 매도 (당일 종가)
- event_log: force_sell_delisted

### E) 022 한도 skip event_log 추가
- skip_max_positions / skip_max_daily_entries / skip_daily_buy_budget 모두 event_log 기록
- 022의 candidates[cutoff:] 또는 _maybe_buy의 budget skip 자리에 event_log

### F) BacktestResult.event_log 영속화
- BacktestResult dataclass에 event_log 필드 추가 (list[dict])
- engine.run() 종료 시 BacktestResult.event_log = engine.event_log
- Service 레이어 영속화는 별도 후속 (event_log DB 모델 + alembic 필요 — Phase 11 또는 별도)

### G) 호환성
- 모든 신규 정책 default = 보수 (상한가/하한가 차단). 단일 종목 골든 fixture는 영향 없도록 (해당 시나리오 없음)
- Phase 1 골든 9지표 frozen expected 일치 필수

### H) 테스트
- [ ] `backend/tests/backtest/test_event_log.py` 신규:
  - 거래정지 봉 event_log 기록
  - 상한가 매수 차단 + event_log
  - 하한가 매도 차단 + event_log
  - 상장폐지 강제 매도 + event_log
  - 022 한도 skip event_log (3종)
  - default 정책 정합성
  - 결정론: 동일 입력 5회 반복 동일 event_log
- [ ] Phase 1 골든 회귀 (event_log 추가는 새 시나리오 없으면 9지표 동일)

### I) 회귀
- [ ] 전체 pytest (Phase 1 골든 + 020/021/022 회귀)
- [ ] ruff
- [ ] 016 head 가드 1건 알려진 무관

### 절대 금지
- StrategyEngine, ExecutionModel, conditions/* / portfolio/* 절대 수정
- API / schemas / services / market_data/* / models/* 절대 수정
- BacktestEngine에 신호 생성 / 가격 계산 로직 직접 추가 금지
- 020·021·022 호환성 유지: 단일 df 자동 wrap, held_at_open_set 가드, priority, _apply_position_limits
- 015 호환성 유지
- 결정론 깨기
- DB 영속화 (event_log DB 모델/저장은 별도 후속 step)
- service 레이어 변경 (BacktestResult.event_log 추가만, services/backtest_service.py는 무영향)

### Phase 10 완료 흐름 (023 마무리 후)
1. PM 호출 → 로드맵 갱신 (04-n, 04-o, 13-p, 13-q [x] / Phase 10 step 023 ✅)
2. **test-engineer 호출 "Phase 10 완료 검증"** — 통합 회귀 + 13.17 acceptance + Phase 1 골든 + 시나리오 + ship-readiness
3. ship-go 시: PM "Phase 10 완료" → 진행률 추이 갱신 → push

## Execution

### 작성/수정 파일

| 파일 | 변경 요지 |
| --- | --- |
| `backend/app/backtest/engine.py:1-32` | 모듈 docstring 업데이트 (step 023 + 04-n/04-o/13-p/13-q 명시) |
| `backend/app/backtest/engine.py:107-122` | 표준 `EVENT_TYPE_*` / `EVENT_REASON_*` 상수 추가 (8종 reason) |
| `backend/app/backtest/engine.py:147-153` | `BacktestEngine.event_log: list[dict]` 신설 (cash_events 패턴) |
| `backend/app/backtest/engine.py:165-205` | `run()` 시그니처에 `delisting_dates: dict[str, date] \| None` 인자 추가 + docstring |
| `backend/app/backtest/engine.py:255-275` | 메인 루프 단계 0 — `_force_sell_delisted_today` 호출 (보유 평가 이전) |
| `backend/app/backtest/engine.py:290-302` | 보유 평가 단계 거래정지 skip → event_log (`skip_no_volume`, phase=exit_evaluation) |
| `backend/app/backtest/engine.py:362-368` | run 종료 시 `result.event_log = list(self.event_log)` 영속화 |
| `backend/app/backtest/engine.py:399-460` | `_evaluate_held_symbol` — exit_signal 매도 경로에 limit_down 가드 + event_log |
| `backend/app/backtest/engine.py:470-528` | 신규 `_force_sell_delisted_today` (today=폐지일 보유 종목 → adj_close 청산) |
| `backend/app/backtest/engine.py:549-595` | `_collect_entry_candidates` — 거래정지 skip event 기록 (final_entry_signal=True 한정) |
| `backend/app/backtest/engine.py:678-770` | `_apply_position_limits` — `today` 인자 추가 + sliced 후보별 skip event 기록 (max_positions/max_daily_entries 사유 분기) |
| `backend/app/backtest/engine.py:777-810` | `_ensure_next_date` 확장 — `prev_close = adj_close.shift(1)` 함께 채움 (limit fallback 판정용) |
| `backend/app/backtest/engine.py:826-908` | 신규 `_log_event` / `_is_limit_up` / `_is_limit_down` 헬퍼 (column 우선 + fallback) |
| `backend/app/backtest/engine.py:1015-1110` | `_maybe_buy` — next_volume 0 / max_gap / limit_up_buy / daily_buy_budget skip 모두 event_log 기록 |
| `backend/app/backtest/config.py:1-25` | 모듈 docstring 업데이트 (step 023 정책) |
| `backend/app/backtest/config.py:76-93` | `allow_buy_limit_up=False` / `allow_sell_limit_down=False` / `limit_pct=0.27` 신규 필드 |
| `backend/app/backtest/config.py:152-180` | `__post_init__` — 한도 validation + bool/숫자 검증 |
| `backend/app/backtest/result.py:25-49` | `BacktestResult.event_log: list[dict]` 필드 + docstring |
| `backend/tests/backtest/test_event_log.py` (신규, 504줄) | 25건 — A~K 검증 (구조/no_volume/limit_up/limit_down/한도/갭/강제매도/결정론/컬럼우선) |

### 모듈 책임 분리 결정 근거

- `event_log`는 BacktestEngine 인스턴스 속성 (cash_events 패턴 그대로 따름). BacktestResult 영속화는 `run()` 종료 시 list 복사로 노출 — service/API 영속화는 후속 step의 책임.
- `delisting_dates`는 per-symbol 매핑이라 BacktestConfig dataclass에 두면 부적절 (config는 전 symbol 공통 정책). `run()` 인자로 전달해 universe_resolver와 같은 호출-시 컨텍스트로 격리.
- limit 판정은 `_is_limit_up` / `_is_limit_down` 두 헬퍼로 분리 (PriceLoader가 채울 수 있는 `is_limit_up` / `is_limit_down` 컬럼을 우선, 없으면 prev_close 기반 fallback). 향후 14번 데이터 파이프라인이 컬럼을 채우게 되면 fallback 경로를 deprecate 가능.
- `_apply_position_limits` 사유 분기는 (max_positions가 더 엄격하면 max_positions, 동률은 max_positions 우선) 결정론 보장 — 같은 입력에 같은 사유가 기록되도록 우선순위 명시.

## Tests

### 신규 테스트 (25건)

`backend/tests/backtest/test_event_log.py`:

- A) 구조: `test_config_default_limit_policy`, `test_config_limit_pct_zero_raises`, `test_config_limit_pct_one_raises`, `test_config_allow_buy_limit_up_int_raises`, `test_event_log_default_initialized_empty`, `test_event_log_no_skip_scenario_remains_empty`, `test_event_log_entry_keys` (7)
- B) 거래정지: `test_event_log_no_volume_in_entry_candidate`, `test_event_log_no_volume_during_held_evaluation`, `test_event_log_no_volume_next_day_blocks_buy` (3)
- C) 상한가: `test_event_log_limit_up_blocks_buy_via_column`, `test_event_log_limit_up_fallback_high_eq_low_and_pct`, `test_event_log_limit_up_allows_buy_when_opted_in` (3)
- D) 하한가: `test_event_log_limit_down_blocks_exit_signal_sell`, `test_event_log_limit_down_allows_sell_when_opted_in` (2)
- E) 한도: `test_event_log_max_positions_skip`, `test_event_log_max_daily_entries_skip`, `test_event_log_daily_buy_budget_skip` (3)
- F) 갭: `test_event_log_max_gap_skip` (1)
- G) 상장폐지: `test_event_log_force_sell_delisted_at_today`, `test_event_log_force_sell_delisted_uses_adj_close`, `test_event_log_force_sell_no_delisting_no_action` (3)
- I) 결정론: `test_event_log_deterministic_across_5_runs`, `test_event_log_ordering_date_asc` (2)
- J) 컬럼 우선: `test_limit_up_column_overrides_fallback` (1)

### pytest 결과

```text
backend/tests/backtest/test_event_log.py    25 passed
backend/tests/                              612 passed, 1 failed (016 head 가드 무관)
```

### ruff 결과

```text
ruff check app/backtest/ tests/backtest/test_event_log.py
All checks passed!
```

### 정확성 정책 13.17 매핑

- 거래정지 종목 매수/매도 차단 → `test_event_log_no_volume_*` (3건)
- 상한가 종목 매수 차단 → `test_event_log_limit_up_*` (3건)
- priority 알고리즘 결정론 (같은 입력 → 같은 결과) → `test_event_log_deterministic_across_5_runs`
- 갭 다운 손절 시 시가 체결 / 갭 업 익절 시 시가 체결 → 회귀 (변경 없음 — 020 호환)
- 동일 봉 익절·손절 동시 도달 시 손절 우선 → 회귀
- 신호일 종가 기준 신호 / 다음날 시가 체결 → exit_signal 매도 경로 가드만 추가 (limit_down)
- 일별 자산 계산 정확성 → Phase 1 골든 frozen 회귀 통과

## Issues

### 정책 결정

1. **상한가/하한가 fallback 임계 = `limit_pct=0.27`** — KOSPI/KOSDAQ 가격 제한폭 30%의 90% 수준. 보다 보수적이면 0.25, 엄격이면 0.295. 실제 한도가 변경되면 본 default 값 갱신 (10번 시장 메타 정책 참조).
2. **상한가/하한가 fallback 조건 = `high == low and pct_change >= ±limit_pct`** — 단일가 거래 + 임계 이상 변동을 동시 요구. 단일가가 아닌 상태로 +30% 도달은 일중 매매 가능했던 경우라 차단 부적절. 14번 데이터 파이프라인이 `is_limit_up` / `is_limit_down` 컬럼을 미래에 채우면 컬럼 우선.
3. **상장폐지 강제 매도 가격 = 당일 `adj_close`** — 13.4.5의 "정리매매 마지막 종가에 강제 매도" 정책. 시세 결손 시 마지막 `current_price` 사용 (조용히 스킵하지 않고 청산 보장).
4. **`max_positions` 사유 우선순위** — `cutoff_pos <= cutoff_daily`이면 max_positions 사유, 동률은 max_positions 우선 (보유 슬롯이 더 근본적 제약). 결정론 보장 위해 명시.
5. **거래정지 보유 평가 skip event는 매일 기록** — 보유 종목이 장기 거래정지면 매일 1건씩 누적. 향후 옵션화(연속 N일 강제 매도 등) 시 별도 step에서 검토.

### 정책 충돌 / look-ahead bias

없음. `prev_close = adj_close.shift(1)`은 전일 종가만 사용해 안전. limit 판정도 today row의 high/low/close + prev_close만 봄. 강제 매도는 폐지일 today에 발동되며 미래 데이터 미사용.

### 잠재 모호 분기점

- `delisting_dates`가 universe_resolver와 분리됨 — universe_resolver는 매수 후보 차단, delisting_dates는 보유 청산만 담당. 두 인터페이스의 데이터를 맞추는 것은 호출자 책임 (Phase 11에서 PriceLoader/UniverseSelector가 동기화).
- `is_limit_up` / `is_limit_down` 컬럼이 PriceLoader에 아직 없음 — 후속 14번 데이터 파이프라인 step에서 채워야 fallback 의존도 감소.

## Result

### 적용 정확성 정책

- 13.4.1 갭 매수 처리 → `skip_max_gap` event_log 추가
- 13.4.2 거래정지 (next_volume=0) → `skip_no_volume` event_log (next_day_entry phase)
- 13.4.3 상한가 / 하한가 → `skip_limit_up_buy` / `skip_limit_down_sell` + 차단 가드
- 13.4.4 거래량 0인 날 → `skip_no_volume` event_log (entry_candidate / exit_evaluation phase)
- 13.4.5 상장폐지 발생 → `force_sell_delisted` + 당일 종가 강제 매도
- 13.8 priority + 13.12 결정론 → event_log 순서 (date ASC + 내부 처리 순서) 유지
- 04번 §6 일별 루프 흐름 — 단계 0 (강제 매도) 신설, 1~4 단계는 020·021·022 호환 유지

### 결정론 보장 방법

- `event_log` append 순서 = 발생 순서. `(date ASC, 내부 처리 순서)`. 보유 평가 → 후보 정렬 → 매수 루프 순서를 따름.
- `_apply_position_limits` 사유 우선순위 명시 (max_positions > max_daily_entries 동률 시).
- `_force_sell_delisted_today` 보유 종목 정렬 = `sorted(...)` 명시.
- `test_event_log_deterministic_across_5_runs`: 모든 한도 활성화 + 5회 반복 → event_log tuple 동일.

### look-ahead bias 검증 결과

- `prev_close = adj_close.shift(1)`만 사용 (전일 종가). 본 row 평가에 미래 데이터 미참조.
- `_is_limit_up` / `_is_limit_down` 모두 today row + prev_close만 본다.
- `_force_sell_delisted_today`는 today == 폐지일에만 발동 (미래 폐지 정보로 오늘 매수 차단하지 않음).
- 신호일 종가 기준 limit 판정 + 다음날 시가 체결 정책 유지.

### 호환성 확인

- 단일 DataFrame 호출 (`engine.run(df)`) → `_normalize_prices` 자동 wrap (020 호환).
- `held_at_open_set` 가드 (020) 유지.
- priority + random_seed (021) 유지.
- `_apply_position_limits` + cumulative_buy_cost (022) 유지.
- 015 signal_date / execution_date 분리 유지.
- Phase 1 골든 fixture 9지표 frozen — 11건 통과 (`tests/integration/test_phase1_golden.py` + `test_phase9_universe_priceloader_e2e.py`).
- 단일 종목 골든 시나리오에는 상한가/하한가/거래정지/상장폐지 없음 → default 보수 정책 (allow_*=False) 적용해도 `event_log == []` 유지.

## Follow-ups

### 후속 step 권고 (DB 영속화)

1. **event_log DB 모델 + alembic 마이그레이션** — 07번 스키마 문서에 `event_log` 테이블 추가 (backtest_run_id FK + date + symbol + event_type + reason + detail JSON). DB 모델 (`models/event_log.py`) + alembic revision 작성. 본 step은 *의도적으로 영속화 미포함*.
2. **service 매핑** — `backtest_service.run_backtest` 종료 시 `result.event_log`를 EventLog ORM으로 일괄 insert. service 레이어 변경은 본 step의 작업 거부 조건이라 별도 step 필요.
3. **API/UI 노출** — backtest run 상세 화면에 event_log 표시 (filter by reason / date range).
4. **PriceLoader 연동** — 14번 데이터 파이프라인이 `is_limit_up` / `is_limit_down` / `prev_close` 컬럼을 채우게 되면 fallback 경로 deprecate 가능 (config.limit_pct도 deprecation 대상).
5. **연속 거래정지 N일 강제 매도** (선택) — Plan A에 언급된 `force_sell_no_volume_consecutive`. 본 step에 포함하지 않음 (추가 정책 결정 필요).

### 04 / 13 문서 갱신 필요 여부

- 04번 §6 흐름에 "0. 상장폐지 강제 매도" 단계가 추가됨 — 04번 문서 §6에 단계 0 추가 권장.
- 04번 §16 검증 항목에 event_log 사유 코드 명세 추가 권장.
- 13번 §4.3 / §4.4 / §4.5는 이미 정책 정의 — 변경 없음 (구현이 정책에 부합).
- 13번 §17 acceptance 항목에 event_log 사유 코드(`skip_*` / `force_sell_*`) 명시 + 결정론 검증 항목 보강 권장.

문서 갱신은 **PM/test-engineer 검증 후** 진행하는 것이 안전.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신 (Phase 10 ✅ 완료 표기)
- [ ] PM 호출 → 로드맵.md 갱신 (04-n, 04-o, 13-p, 13-q [x] / Phase 10 step 023 ✅)
- [ ] **test-engineer 호출 → "Phase 10 완료 검증"**
- [ ] ship-go 시: PM "Phase 10 완료" → 진행률 추이 + Phase 11 첫 step ⏭
- [ ] git commit (단일)
- [ ] **Phase 10 마지막 step**: ship-go 받으면 `git push origin main` (의무)
