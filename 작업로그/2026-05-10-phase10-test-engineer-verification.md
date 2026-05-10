---
date: 2026-05-10
agent: test-engineer
phase: 10 (완료 검증)
status: completed
roadmap_step: phase10-verification
roadmap_impact: []   # 직접 [x] 갱신 없음 (12-h 부분 충족 — Follow-up)
related_docs:
  - .claude/agents/test-engineer.md
  - 상세설계/12_testing_validation_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 작업로그/2026-05-10-020-backtest-engine-multi-symbol.md
  - 작업로그/2026-05-10-021-priority-and-random-seed.md
  - 작업로그/2026-05-10-022-position-limits.md
  - 작업로그/2026-05-10-023-event-log-and-forced-sell.md
ship_readiness: ship-go  # 🟢
---

# Phase 10 완료 검증 (test-engineer)

`.claude/agents/test-engineer.md`의 두 번째 실전 호출. Phase 10 (020·021·022·023)
통합 회귀 + 13.17 acceptance + Phase 1 골든 + 신규 시나리오 + ship-readiness.

## 1. 변경 영역 파악

- Phase 첫 commit: `b987567` (Phase 10-1 020 — BacktestEngine 복수 종목)
- Phase 마지막 commit: `0f56691` (Phase 10-4 023 — event_log + 강제 매도) = HEAD
- 4개 commit 모두 `backtest-engine-developer` 단독 작업

변경 통계 (`git diff --stat ad6bf75..HEAD`):
- 13 files changed, 4,333 insertions(+), 131 deletions(-)
- 백엔드 코드: `app/backtest/{config,engine,result}.py` 3 파일
- 신규 단위 테스트: 4 파일 (multi_symbol / priority / position_limits / event_log)
- 작업 로그 4개 + README + 로드맵.md

신규/대폭 확장 모듈:
- `app/backtest/engine.py` (+825줄, 956줄로 확장) — 복수 종목 입력, priority 4종, 한도 3종, event_log 8종, 강제 매도
- `app/backtest/config.py` (+135줄) — priority/한도/limit 정책 화이트리스트 + `__post_init__` 검증
- `app/backtest/result.py` — `event_log: list[dict]` 필드 추가

신규 단위 테스트 파일 4개 (총 76건):
- `tests/backtest/test_backtest_engine_multi_symbol.py` 15건 (020)
- `tests/backtest/test_priority.py` 14건 (021)
- `tests/backtest/test_position_limits.py` 22건 (022)
- `tests/backtest/test_event_log.py` 25건 (023)

신규 통합 테스트 (test-engineer 작성):
- `tests/integration/test_phase10_multi_symbol_priority_e2e.py` 4건

## 2. 정량 회귀

| 검증 | 결과 | baseline 대비 |
|---|---|---|
| pytest 백엔드 (test-engineer 신규 4건 추가 후) | **616 passed / 1 failed in 19.20s** | +80 vs Phase 9 baseline 536 |
| ruff (`app tests`) | All checks passed | — |

step별 누계:
- Phase 9 종료 시점: 536 passed
- 020 직후: 551 passed (+15)
- 021 직후: 565 passed (+14)
- 022 직후: 587 passed (+22)
- 023 직후: 612 passed (+25)
- 본 검증 시점 (e2e 4건 추가 후): **616 passed**

**유일 실패**: `tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head`
— 016 자기-소유 head 가드. 017이 head를 `b5e8d3c1a924`로 이동시키며 가드가
시대에 뒤처진 것. **알려진 무관 이슈**, Phase 9 검증에서도 동일하게 식별됨.
Phase 11 fix step 예정 — Phase 10 ship 결정에 영향 없음.

## 3. 정확성 정책 13.17 acceptance 매핑

본 Phase에서 영향받은 정책 절번호를 13번 §17 acceptance 항목과 1:1 매핑.

| 13.17 항목 | Phase 10 영향 | 검증 테스트 | 결과 |
|---|---|---|---|
| 일중 손절 도달 정확성 | — (020·023 호환만) | `test_phase1_golden.*` (회귀) | ✅ |
| 일중 익절 도달 정확성 | — (호환만) | `test_phase1_golden.*` | ✅ |
| 동일 봉 익절·손절 동시 도달 시 손절 우선 | — (호환만) | `test_backtest_engine.*` (회귀) | ✅ |
| 갭 다운 손절 시 시가 체결 | ✓ (`skip_max_gap` event_log 추가, 023) | `test_event_log_max_gap_skip` + 회귀 | ✅ |
| 거래정지 종목 매수/매도 차단 | ✓ (skip_no_volume event_log 3종, 023) | `test_event_log_no_volume_*` (3건) | ✅ |
| 상한가 매수 차단 | ✓ (allow_buy_limit_up=False default, 023) | `test_event_log_limit_up_*` (3건) + e2e 시나리오 3 | ✅ |
| 호가 단위 반올림 | — (ExecutionModel 무영향) | — | n/a |
| 거래세 시계열 적용 | — (ExecutionModel 무영향) | — | n/a |
| 수정주가 사용 일관성 | — (PriceLoader는 Phase 9, BacktestEngine은 adj_* 그대로) | — | n/a |
| 동시 신호 우선순위 결정론 | ✓ (priority 4종, 021 / `_apply_position_limits` 사유 우선순위, 022·023) | `test_priority_*` (14건) + `test_position_limits_*` (22건) + e2e 시나리오 1 | ✅ |
| random_seed 동일 시 동일 결과 | ✓ (BacktestEngine `_rng` 인스턴스화, 021 — M7 잔존 해소) | `test_priority_random_*` + `test_config_random_method_without_seed_raises` | ✅ |

본 Phase가 도입한 정책 추가 (13.x → §17 갱신 권고):

| 13.x 정책 | Phase 10 영향 | 검증 테스트 | 결과 |
|---|---|---|---|
| 13.4.5 상장폐지 강제 매도 | ✓ (`_force_sell_delisted_today`, 023) | `test_event_log_force_sell_delisted_*` (3건) + e2e 시나리오 2 | ✅ |
| 13.8 priority + 한도 흐름 (04 §11) | ✓ (021·022·023) | priority + position_limits + e2e 시나리오 1 | ✅ |
| 13.12 결정론 (dict 순회 금지) | ✓ (모든 step에 영향) | `*_deterministic_across_*_runs` (각 단위 테스트) + e2e 시나리오 4 | ✅ |
| 13.12.2 random_seed 정책 | ✓ (None+random ValueError, 021) | `test_config_random_method_without_seed_raises` | ✅ |
| 13.13 생존편향 (폐지 종목 청산 보존) | ✓ (universe_resolver와 분리된 강제 매도, 023) | e2e 시나리오 2 | ✅ |
| 13.15 look-ahead bias | ✓ (priority scoring today row 한정 / prev_close shift(1)) | `test_priority_*` + `test_event_log_*` 도입 시점 검토 | ✅ |

⚠️ **§17 acceptance 항목 누락 (Follow-up)**:
- 13.4.5 상장폐지 강제 매도가 §17 체크리스트에 미포함 — Phase 10 마지막 step 023이
  도입했으므로 §17에 항목 추가 권고
- 한도 (`max_positions` / `max_daily_entries` / `daily_buy_budget`) 위반 시
  결정론적 skip 사유 — §17에 `event_log` 사유 코드 명세 추가 권고
- 04 §6 흐름의 "0. 상장폐지 강제 매도" 단계 — 04번 §6에 단계 0 추가 권고
  (023 작업 로그 Follow-up과 동일)

## 4. Phase 1 골든 fixture 회귀

`tests/integration/test_phase1_golden.py` **6/6 PASSED in 0.49s**.

015 baseline 9지표 그대로 유지 (Phase 10 4개 step 모두 Phase 1 골든 frozen 보존):
- final_equity 10,188,570 / total_return 1.8857 / mdd -4.9032
- trade_count 8 / win_rate 37.5 / avg_holding_days 6.5 / profit_factor 1.2252
- 첫 거래 entry_date 2024-01-13 / signal_date 2024-01-12
- 결정론 10회 반복 PASSED

Phase 10 영향 없음의 핵심 정합:
1. **020**: 단일 DataFrame 입력 자동 wrap (`_normalize_prices`) + `held_at_open_set` 가드로 015 흐름의 `if/elif` 의미 보존 (final_equity 변동 0)
2. **021**: priority_method default `"none"` → 020 동작과 동일
3. **022**: max_positions / max_daily_entries / daily_buy_budget 모두 default `None` → 021 동작과 동일
4. **023**: allow_buy_limit_up / allow_sell_limit_down default `False` + 골든 fixture에 상한가/하한가/거래정지/상장폐지 시나리오 없음 → event_log 빈 list, 9지표 변동 0

## 5. 신규 시나리오 (test-engineer 작성)

**위치**: `backend/tests/integration/test_phase10_multi_symbol_priority_e2e.py`
(4건, 모두 PASSED in 0.72s)

본 시나리오는 Phase 10 4개 step (020 다종목 + 021 priority + 022 한도 + 023 event_log)
이 동일 BacktestEngine 인스턴스에서 협업할 때 cross-component contract를 보호한다.
단위 테스트는 각 step 영역만 검증.

| # | 시나리오 | 정책 매핑 |
|---|---|---|
| 1 | 다종목 entry → priority(trading_value_desc) → max_positions=2 cap → priority 1·2위만 매수 + 3위 skip event_log | 13.8, 13.12, 04 §11 (020+021+022+023 cross) |
| 2 | 상장폐지 강제 매도가 universe_resolver와 분리되어 보유 청산만 담당 — universe에서 제외돼도 강제 매도 발동 | 13.4.5, 13.13, 04 §6 step 0 (023 핵심 정합) |
| 3 | 신호일 상한가 → 매수 차단 + BacktestResult.event_log 인터페이스 (사본 — mutation 차단) | 13.4.3, 023 영속화 인터페이스 |
| 4 | UniverseSelector + PriceLoader (Phase 9) + BacktestEngine 다종목 (Phase 10) 라운드트립 + 결정론 3회 반복 | 13.7, 13.12, 13.15, CLAUDE.md #8 (Phase 9 → Phase 10 contract 통합) |

신규 시나리오의 정합성 결정:
- **시나리오 1**: priority 정렬 + 한도 cap + event_log skip 사유까지 cross-component
  검증 → 020·021·022·023이 동일 흐름에서 협업한다는 contract 보호
- **시나리오 2**: `delisting_dates` 인자가 universe_resolver와 의도적으로 분리되어
  있다는 023 정합 (작업 로그 §Issues 참조)을 e2e로 보호
- **시나리오 3**: `BacktestResult.event_log = list(self.event_log)` (`engine.py:367`)
  의 list 사본 영속화 인터페이스를 검증 — service/DB 영속화 후속 step의 의존
- **시나리오 4**: Phase 9 e2e (UniverseSelector + PriceLoader 라운드트립) 위에
  Phase 10 다종목 BacktestEngine을 얹어 결정론 3회 반복 + priority(trading_value_desc)
  순서 정합 (000001 첫 매수)까지 확인

## 6. 회귀 발견

**없음** (016 자기-소유 head 가드 1건은 Phase 9 검증 시점부터 알려진 무관 이슈로
Phase 10 ship 결정과 무관).

## 7. ship-readiness 결정

# 🟢 ship-go

근거:
1. 회귀 통과: **616 passed / 1 failed** (Phase 9 baseline 536 → +80, 단위 76 + e2e 4)
2. 단일 실패는 016 자기-소유 head 가드 (알려진 무관, Phase 11 fix step 예정)
3. ruff: All checks passed (변경 영역 + 신규 영역 모두)
4. **Phase 1 골든 9지표 frozen expected 변동 없음** — Phase 10 4개 step의
   default 정책 (priority="none" / 한도 None / allow_*=False) 모두 020 이전과
   동작 동일. 015 baseline 유지.
5. 13.17 영향 acceptance 항목 모두 ✅:
   - 거래정지 / 상한가 / 동시 신호 priority / random_seed (직접 영향)
   - 일중 stop·take / 갭 / 호가 / 세율 / 수정주가 (간접 / 호환)
6. **Phase 10이 도입한 신규 정책 13.4.5 / 13.8 한도 / 13.12 결정론 / 13.12.2 / 13.13 / 13.15 모두 ✅**
7. 신규 e2e 통합 시나리오 4건 PASSED — Phase 10 cross-component contract 보호
   (단위 테스트가 검증하지 못하는 020·021·022·023 cross-step 협업 + Phase 9 →
   Phase 10 라운드트립)

알려진 016 head 가드 실패는 Phase 10 ship-go 결정에 영향 없음. Phase 11 fix
step에서 정리 (Phase 9 검증의 Follow-up 2번과 동일 — 누적).

## 8. Follow-up (우선순위 순)

1. **(중) 13번 §17 acceptance 체크리스트 갱신** — Phase 10이 도입한 신규 정책 추가:
   - 13.4.5 상장폐지 강제 매도 (`force_sell_delisted` 검증 항목)
   - 13.8 한도 정책 — `max_positions` / `max_daily_entries` / `daily_buy_budget`
     위반 시 결정론적 `event_log` 사유 코드 매핑
   - 04 §6 흐름의 "0. 상장폐지 강제 매도 → 1. 보유 평가 → ..." 단계 0 명시화
2. **(중) 016 자기-소유 head 가드 정리** — Phase 9 검증 Follow-up 2번 누적.
   `test_new_revision_is_current_head`를 alembic 단일 head 보장 검증으로 대체
   또는 제거. Phase 11 첫 step 후보.
3. **(중) event_log DB 영속화** — 023 작업 로그 Follow-up 1·2 누적. 07번 schema
   문서에 `event_log` 테이블 추가 + DB 모델 + alembic + service 매핑.
4. **(중) 04번 문서 §11.2 갱신** — 021 작업 로그 Follow-up. priority `trading_value_desc`
   가 "today close × adj_volume" 단봉 점수임을 명시 (사전계산 컬럼 도입 시
   교체 가능). 13.8.3과 동기화.
5. **(중) 04번 문서 §11.1 흐름 7번/8번 갱신** — 022 작업 로그 Follow-up. "max_positions:
   보유 + 신규 후보 합" 의미 + "daily_buy_budget: 실 체결 net_amount 누적" 정책 명시.
6. **(저) 13번 문서 §12.2 갱신** — 021 작업 로그 Follow-up. "random_seed=None +
   priority_method='random'은 ValueError" 한 줄 추가.
7. **(저) Phase 9 baseline 536건 → 누계 표 PM 갱신 시 참고** (Phase 9 검증
   Follow-up 4번 누적).
8. **(저) test-engineer 신규 e2e 누적 9건** (Phase 9 5건 + Phase 10 4건) — 12-h
   (13.17 acceptance 1:1 별도 파일) + 12-i (fixtures/expected 표준) 부분 충족.
   완전 충족은 후속 step (12 testing 문서 §15 갱신).

## 메인 세션 마무리 체크 (참고용 — test-engineer는 직접 수행 안 함)

ship-go 받으면 메인 세션이:
- [ ] PM 호출 → 로드맵.md 갱신 (Phase 10 ✅ 완료 + Phase 11 첫 step ⏭ + 진행률 추이 새 행)
- [ ] 작업로그/README.md 갱신 (Phase 10 완료 표기 + Phase 11 다음 step 후보)
- [ ] **`git push origin main`** (Phase 10 마지막 step 직후 의무)
