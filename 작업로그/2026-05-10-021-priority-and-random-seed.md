---
date: 2026-05-10
agent: backtest-engine-developer
phase: 10
status: completed
roadmap_step: 021
roadmap_impact:
  - 04-k  # priority 알고리즘 + symbol_asc tie-breaker
  - 13-n  # priority 결정론 + symbol_asc tie-breaker
  - 13-o  # random_seed 실사용 (M7 잔존 해소)
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 작업로그/2026-05-10-020-backtest-engine-multi-symbol.md
---

# Step 021 — priority 알고리즘 + symbol_asc tie-breaker + random_seed 실사용

020에서 `_collect_entry_candidates` (engine.py:352-381)가 symbol ASC tie-breaker만 적용. 본 step에서 priority scoring을 도입해 `config.priority.method`별로 후보 정렬. random method는 `config.random_seed` 실사용 (Phase 8에서 영속화만, 사용처 없던 M7 잔존 해소).

## Plan

### A) priority 알고리즘 (04-k)
- [ ] `상세설계/04_backtest_engine_design.md` priority 절 정독
- [ ] `상세설계/13_backtest_accuracy_policy_design.md` 13.12 (결정론) 정독
- [ ] `backend/app/backtest/engine.py:_collect_entry_candidates` 또는 신규 `_apply_priority`:
  - config.priority.method 지원:
    - `"none"` (default 또는 미설정): symbol ASC만 (020 그대로)
    - `"trading_value_desc"`: 후보의 today row `close × volume` 내림차순 + symbol ASC tie-breaker
    - `"market_cap_desc"`: today row `market_cap` 내림차순 + symbol ASC tie-breaker (결손 시 종목 제외)
    - `"random"`: random.Random(seed)로 셔플 + symbol ASC tie-breaker는 의미 없음 (random은 그 자체로 결정론)
  - tie-breaker는 항상 symbol ASC가 마지막 정렬 키

### B) symbol_asc tie-breaker (13-n)
- 위 모든 method에서 동점 시 symbol ASC가 결정적 마지막 키
- 정렬 키 형식: `key=lambda c: (-trading_value, c.symbol)` 같이 명시

### C) random_seed 실사용 (13-o, M7 해소)
- 현재: `BacktestRun.random_seed`는 영속화만, 사용처 없음 (Phase 8 M7 잔존)
- BacktestEngine 생성 시 `config.random_seed`로 `random.Random(seed)` 인스턴스화 → priority.method=random에서 사용
- random_seed=None이면 priority.method=random은 결정론을 깨므로 ValueError 또는 default seed (정책 결정 필요 — Issues에 명시)
- 같은 seed → 같은 결과 단위 테스트로 강제

### D) BacktestConfig 확장
- [ ] `backend/app/backtest/config.py`에 priority 필드 추가:
  - `priority_method: str = "none"`
  - `priority_tie_breaker: str = "symbol_asc"` (현재 symbol_asc만 지원)
- 기존 config 호환: 미설정 시 default "none" → 020 동작과 동일

### E) 호환성
- 020 단일 종목 골든 fixture (priority.method="none" default) → 9지표 frozen expected 그대로
- 결정론 10회 반복 PASSED 유지

### F) 테스트
- [ ] `backend/tests/backtest/test_priority.py` 또는 multi_symbol에 추가:
  - priority="none"이 020 동작과 동일 (symbol ASC)
  - priority="trading_value_desc" 정상 정렬
  - priority="market_cap_desc" 정상 정렬 (결손 종목 제외)
  - priority="random" + 동일 seed 5회 반복 동일 결과
  - priority="random" + 다른 seed 결과 다름
  - tie-breaker symbol ASC: 같은 trading_value 동점 시 symbol ASC
  - random_seed=None + priority="random" 처리 (정책에 따라)
- [ ] Phase 1 골든 회귀 (priority="none" default — 9지표 동일)

### G) 회귀
- [ ] 전체 pytest (Phase 1 골든 + 020 회귀)
- [ ] ruff
- [ ] 016 head 가드 1건은 알려진 무관

### 절대 금지
- StrategyEngine, ExecutionModel, conditions/* / portfolio/* 절대 수정 (다른 에이전트 영역)
- API / schemas / services / market_data/* / models/* 절대 수정
- BacktestEngine에 신호 생성 / 가격 계산 / 자금 관리 로직 직접 추가 금지
- **max_positions / max_daily_entries / daily_buy_budget 도입 금지** — step 022 영역
- **event_log / 거래정지·상한가·하한가·상장폐지 강제 매도 도입 금지** — step 023 영역
- 020 호환성 유지: 단일 df 자동 wrap, held_at_open_set 가드
- 015 호환성 유지: signal_date / execution_date
- Wave B1·C1 호환성 유지
- 결정론 깨기 (dict 순회, 시드 없는 random.shuffle)
- look-ahead bias

### 다음 step (022) 인계 정보
- priority 후 후보 리스트 흐름 (어느 함수가 022의 max_positions 적용 자리인지)
- BacktestConfig 확장 패턴 (022도 max_positions / max_daily_entries / daily_buy_budget 추가)

## Execution

### 작성/수정 파일

- `backend/app/backtest/config.py` (전면 갱신)
  - `SUPPORTED_PRIORITY_METHODS` (config.py:14-22) — 화이트리스트 frozenset
    ("none", "trading_value_desc", "market_cap_desc", "random")
  - `SUPPORTED_PRIORITY_TIE_BREAKERS` (config.py:26) — 현재 {"symbol_asc"}만
  - `BacktestConfig.priority_method: str = "none"` (config.py:48)
  - `BacktestConfig.priority_tie_breaker: str = "symbol_asc"` (config.py:50)
  - `BacktestConfig.random_seed: int | None = None` (config.py:54)
  - `__post_init__` (config.py:56-78) — method/tie-breaker 화이트리스트 검증 +
    `priority_method='random'` ↔ `random_seed=None` 조합 ValueError

- `backend/app/backtest/engine.py` (priority 적용)
  - `import random` (engine.py:62)
  - `__init__` (engine.py:117-128) — `self._rng = random.Random(seed)` 인스턴스화.
    seed=None이면 RNG=None (random method가 도달 불가하므로 안전).
  - run() docstring (engine.py:18-31, 161-167) — priority 4종 분기 명시
  - 호출자 (engine.py:248-251) — `_collect_entry_candidates` 직후 `_apply_priority` 적용
  - `_apply_priority` 신규 (engine.py:402-481) — 4종 method 분기

- `backend/tests/backtest/test_priority.py` (신규, 14건)

### 모듈 책임 분리

- BacktestConfig: 화이트리스트 + 정책 검증 (`priority_method='random'` ↔ seed) —
  엔진 호출 시점에 invalid 상태 도달 불가
- BacktestEngine: 후보 수집(`_collect_entry_candidates`)과 정렬(`_apply_priority`)을
  별도 메서드로 분리 — step 022가 `_apply_priority` 다음 단계(max_positions 등)를
  추가할 자리 명확
- StrategyEngine / Portfolio / ExecutionModel / conditions 영역 미수정

## Tests

```bash
cd backend && .venv/Scripts/pytest.exe tests/backtest/test_priority.py -v
# 14 passed in 0.59s

cd backend && .venv/Scripts/pytest.exe --tb=line -q
# 565 passed, 1 failed (016 head 가드, 무관)

cd backend && .venv/Scripts/pytest.exe tests/integration/test_phase1_golden.py \
    tests/backtest/test_backtest_engine.py \
    tests/backtest/test_backtest_engine_multi_symbol.py -v
# 48 passed (Phase 1 골든 9지표 frozen + 015 + 020 모두 회귀 없음)

cd backend && .venv/Scripts/python.exe -m ruff check \
    app/backtest/config.py app/backtest/engine.py tests/backtest/test_priority.py
# All checks passed!
```

### 정확성 정책 13.17 매핑

| 정책 절 | 검증 테스트 |
|---|---|
| 13.17 "동시 신호 우선순위 결정론" | `test_priority_trading_value_desc_*` / `test_priority_market_cap_desc_*` / `test_priority_none_keeps_symbol_asc_order` |
| 13.17 "random_seed 동일 시 동일 결과" | `test_priority_random_same_seed_same_result_5_runs` / `test_priority_random_seed_zero_is_deterministic` |
| 13.8.4 tie-breaker symbol_asc | `test_priority_*_tie_breaker_symbol_asc` (2건) |
| 13.12.1 dict 순회 의존 금지 | `test_priority_random_seed_zero_is_deterministic` (sorted 입력 강제 검증) |
| 13.12.2 random_seed 정책 | `test_config_random_method_without_seed_raises` |

## Issues

### random_seed=None + priority_method='random' 처리 — ValueError 채택

3개 옵션 검토:
1. **ValueError (채택)** — 명시적 거부. 정책 위반을 즉시 표면화.
2. default seed=0 fallback — "보이지 않는 결정론"이 되어 의도하지 않은 결과를
   재현 가능하게 만들지만, 사용자가 random_seed 누락을 인지하지 못함 → 운영
   리스크.
3. `random.Random()` 시드 없이 사용 — CLAUDE.md #8 결정론 깨짐, 13.12.1 위반.

CLAUDE.md #8 ("dict/set 순서 의존 금지, 무작위는 random.Random(seed)") + 13.12.2
("metadata.random_seed로 무작위 priority 결정론 보장")의 정신은 "결정론을 깰 수
있는 상태를 절대 허용하지 않음"이므로 **명시적 ValueError**가 정합. `BacktestConfig
.__post_init__`에서 차단해 엔진 호출 전에 거부됨.

문서 갱신 필요 — `13.12.2` 절에 "random_seed=None일 때 priority_method='random'은
ValueError" 한 줄 추가 권장 (Follow-ups 참조).

### trading_value_desc — "20일 평균 거래대금" vs "today close × volume"

13.8.3 명세는 "20일 평균 거래대금 큰 순"이지만, 본 step에서는 별도 컬럼 사전계산
없이 **today (close × adj_volume)** 단일 봉 점수로 도입. PriceLoader가 사전
계산한 `avg_trading_value_20d` 컬럼이 없는 상태에서, 매 today마다 20봉 rolling을
역산하면 결정론·성능·look-ahead 모두 위험. 현재 구현은:

- 정렬 키 함수만 교체하면 사전계산 컬럼으로 전환 가능 (`row["avg_trading_value_20d"]`).
- 본 step에서는 04번 §11.2 예시의 "scores[s]"를 today 단봉으로 대체.
- 후속 step (Phase 11/12)에서 PriceLoader가 컬럼을 채우면 정렬 키만 교체.

문서 갱신 필요 — 04번 §11.2 / 13.8.3에 "MVP는 today close×volume, 사전계산
컬럼 도입 후 20일 평균으로 교체" 주석 권장.

### 04번 / 13번 본문 상의 "tie_breaker symbol_desc"

13.8.4는 `symbol_asc` / `symbol_desc` 둘 다 명시하지만, 본 step에서는 `symbol_asc`
만 화이트리스트에 도입. `symbol_desc`는 결정론은 보장되지만 사실상 unused이므로
보수적으로 거부. 후속 step에서 필요하면 화이트리스트 + 04번 §11.2 reverse 분기
한 줄 추가로 가능.

### look-ahead bias 검증

- `trading_value_desc`: today close × today adj_volume → today row만 사용 ✓
- `market_cap_desc`: today market_cap → today row만 사용 ✓
- `random`: rng.random()은 시장 데이터 무관 ✓
- 다음 거래일 가격/거래량을 priority scoring에 사용한 곳 없음.

### 결정론 보장 메커니즘

- 모든 method의 정렬 key에 `c[0]` (symbol)이 마지막 요소로 들어감.
- random method는 `sorted(candidates, key=lambda c: c[0])`로 입력을 먼저 정렬한
  뒤 rng를 호출 — upstream candidate 순서가 바뀌어도 결과 동일.
- rng는 `__init__`에서 한 번만 생성, 같은 seed → 같은 호출 시퀀스 → 같은 결과.

## Result

### 적용 정확성 정책

- 13.8 (priority schema, methods, tie-breaker, 적용 흐름)
- 13.12 (결정론 — dict 순회 금지, random.Random(seed))
- 13.12.2 (random_seed 실사용 + None일 때 명시적 거부)
- 13.17 (검증 항목 매핑 — 동시 신호 우선순위 / random_seed 결정론)
- 04 §11.1~11.2 (priority 적용 흐름과 예시 코드)

### look-ahead bias 차단 검증

- priority scoring은 today row 컬럼만 참조 (close, adj_volume, market_cap)
- next_date / next_open / next_volume은 매수 체결 단계에서만 사용 (기존 흐름 유지)

### Phase 1 골든 fixture 9지표 frozen 회귀

`tests/integration/test_phase1_golden.py` PASS (priority_method="none" default →
020 동작 보존 → 015 baseline 유지). 565/566 전체 회귀에서 신규 14건만 추가, 기존
551건 변동 없음.

### 결정론 검증

- random 동일 seed 5회 반복: 매수 순서 + final_equity 동일 (`test_priority_random_same_seed_same_result_5_runs`)
- random 서로 다른 seed (0/1/2/3/7/42/100 7개): 최소 2개 이상 다른 매수 순서 (`test_priority_random_different_seeds_can_yield_different_orders`)
- seed=0 truthy 체크 회귀 보호: 3회 반복 동일 (`test_priority_random_seed_zero_is_deterministic`)

### 다음 step (022) 인계 정보

- **priority 적용 후 후보 리스트는 `engine.py:251` (`entry_candidates = self._apply_priority(...)`)에서 확정.** 022는 이 결과 위에 max_positions / max_daily_entries / daily_buy_budget을 적용한다.
- 적용 자리 후보:
  1. `_apply_priority` 직후 `_collect_then_filter_by_limits` 같은 헬퍼를 추가
  2. 또는 매수 순회 루프 내에서 카운터 누적 후 차단
  - 권장: 정렬-필터 단계 분리가 깔끔. `_apply_priority` 다음에 `_apply_position_limits` 신설.
- BacktestConfig 확장 패턴 동일 — 화이트리스트 frozenset + `__post_init__` 검증 + default 값으로 020/021 호환.
- random_seed는 본 step에서 인스턴스화 완료. 022가 추가 시드를 필요로 하면 같은 `self._rng` 재사용 가능 (현재 priority="random"일 때만 생성됨).

## Follow-ups

- **04번 문서 §11.2 갱신** — 예시 함수의 "20일 평균 거래대금"을 "사전계산 컬럼이 있으면 그 값, 없으면 today close × volume"으로 명시. 현재 코드는 후자만 구현.
- **13번 문서 §12.2 갱신** — "random_seed=None + priority_method='random'은 ValueError" 한 줄 추가. 현 코드와 정책 동기화.
- **13번 문서 §8.4 갱신 (선택)** — symbol_desc는 미구현임을 주석. 향후 도입 시 화이트리스트만 확장.
- **step 022** — `_apply_priority` 직후에 max_positions / max_daily_entries / daily_buy_budget 적용 헬퍼 신설. 본 step에서 분리한 (수집 / 정렬 / 매수 루프) 구조를 그대로 따라 (수집 / 정렬 / 한도 / 매수 루프) 4단계로 확장.
- **step 023** — event_log + 거래정지·상한·하한·상장폐지 강제 매도. 본 step의 priority 정렬은 신규 매수 후보에만 적용되므로, 강제 매도 영역과 분리됨.
- **PriceLoader (Phase 11/12)** — `avg_trading_value_20d` 사전계산 컬럼 도입 시 `_apply_priority` trading_value_desc 분기를 1줄 교체.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (04-k, 13-n, 13-o [x] / Phase 10 step 021 ✅)
- [ ] git commit (Phase 10 마지막 step 아니므로 push 보류)
