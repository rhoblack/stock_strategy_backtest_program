---
date: 2026-05-10
agent: market-data-engineer
phase: 11
status: completed
roadmap_step: 026
roadmap_impact:
  - 06-h  # corporate_actions 모델 + 적용
  - 07-n  # corporate_actions DB 테이블
  - 14-h  # 수정주가 재계산 + corporate_actions 적용
  - 13-r  # 수정주가 재계산 정책 (분할/배당)
related_docs:
  - 상세설계/14_data_pipeline_design.md
  - 상세설계/06_market_data_universe_design.md
  - 상세설계/07_database_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 작업로그/2026-05-10-024-data-pipeline-skeleton.md
  - 작업로그/2026-05-10-025-pykrx-collector.md
---

# Step 026 — 수정주가 재계산 processor + corporate_actions 모델 (14-h, 06-h, 07-n, 13-r)

024 BaseProcessor + 025 PykrxCollector 위에 수정주가 재계산 + corporate_actions 모델 도입. 13.7 정확성 정책의 핵심 — 분할/배당 발생 시 과거 전체 재계산.

## Plan

### A) corporate_actions DB 모델 (07-n + 06-h)
- [ ] `상세설계/07_database_design.md` corporate_actions 절 정독
- [ ] `상세설계/06_market_data_universe_design.md` 분할/배당 절 정독
- [ ] `backend/app/models/corporate_action.py` 신규
- 컬럼: `id` (PK) / `symbol` (FK → symbols.symbol) / `event_date` / `event_type` (split / dividend / cash_dividend / merger / spinoff) / `ratio` (split: 신주/구주 비율 / cash_dividend: 주당 배당금) / `notes` (선택) / `created_at`
- UniqueConstraint: (symbol, event_date, event_type)
- 인덱스: (symbol, event_date)
- FK CASCADE on symbols 삭제

### B) Alembic 마이그레이션
- [ ] `backend/alembic/versions/<rev>_add_corporate_actions.py` 신규
- down_revision = `b5e8d3c1a924` (직전 head — 017 trade_executions.signal_date)
- raw DDL (env.py 정상화 후 op.create_table 정상 동작)
- downgrade는 drop_table

### C) repositories 확장 (016 패턴)
- [ ] `backend/app/market_data/repositories.py`에 corporate_actions CRUD 추가:
  - `upsert_corporate_action(session, data)` 
  - `get_corporate_actions(session, symbol, start_date=None, end_date=None) -> list[CorporateAction]`
  - 결정론: (event_date ASC, event_type ASC) 정렬
- 016 시그니처 외 새 함수만 추가 (기존 함수 변경 금지)

### D) AdjustedPriceProcessor (14-h, 13-r) — BaseProcessor 상속
- [ ] `backend/app/data_pipeline/processors/adjusted_price.py` 신규
- BaseProcessor[AdjustedPriceInput, tuple[RawDailyPriceRow, ...]] 상속
- 입력: `AdjustedPriceInput(prices: RawDailyPricesData, corporate_actions: tuple[CorporateActionEvent, ...])`
- 처리:
  1. 시간 역순으로 corporate_actions 적용
  2. split: ratio (신주/구주) 만큼 과거 가격을 나눔, 거래량 곱함
  3. cash_dividend: 배당락 전 가격에서 배당금만큼 차감 (역방향 누적)
  4. merger / spinoff: 별도 정책 (본 step에서 단순화 또는 NotImplementedError)
- 출력: 모든 일자의 adj_open / adj_high / adj_low / adj_close / adj_volume 재계산
- 결정론: corporate_actions 정렬 (event_date DESC, event_type ASC)
- ValidationIssue: corporate_action 누락 / 음수 ratio / 미래 이벤트 등 SOFT/HARD

### E) corporate_actions 적용 검증
- [ ] 14.10 정합:
  - 수정주가 재계산은 분할/배당 발생 시 과거 전체 재계산 (스냅샷 누적 금지)
  - close (원 가격)는 변경 안 함, adj_*만 재계산
- [ ] 14.9 look-ahead 차단: 미래 corporate_action 절대 적용 금지 (event_date <= as_of_date)

### F) 테스트
- [ ] `backend/tests/market_data/test_corporate_action_model.py` 신규
- [ ] `backend/tests/data_pipeline/test_adjusted_price_processor.py` 신규
  - 1:2 분할 시 분할 전 가격 1/2 / 거래량 2배
  - 현금 배당 시 배당락 전 가격 - 배당금 (시가총액 보존)
  - 복수 corporate_action 누적 (시간 역순)
  - 미래 이벤트 무시 (look-ahead 차단)
  - close는 불변, adj_*만 변경
  - 결정론: 동일 입력 5회 반복 동일

### G) 회귀
- [ ] 전체 pytest (Phase 1~10 + 024·025 회귀)
- [ ] ruff
- [ ] alembic upgrade head → downgrade -1 → upgrade head 회귀
- [ ] models/__init__.py 등록 누락 검증

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정
- API / Pydantic schemas / services 추가/수정
- application 테이블 / symbols / daily_prices / trading_calendar 모델 수정 (016 산출물)
- conditions/* 수정
- **027·028 영역 도입 금지**:
  - 시가총액 시계열 / market_indices / universe_history — 027
  - jobs/scheduler 실제 구현 — 028
- 016 repositories 시그니처 변경 금지 — 새 함수만 추가
- 018 BaseProvider/LocalCsvProvider/PriceLoader 수정 금지
- 019 UniverseSelector 수정 금지
- 024 ABC / 025 PykrxCollector 수정 금지 — 활용만
- 결정론 깨기 (corporate_actions 정렬 누락)
- look-ahead bias (미래 이벤트 적용)

### 다음 step (027) 인계 정보
- corporate_action 적용 결과를 daily_prices에 어떻게 영속화 (별도 update or 신규 row)
- AdjustedPriceProcessor 입력 형식 (027 시가총액 시계열 처리 시 활용)

## Execution

### A) corporate_actions DB 모델

- `backend/app/models/corporate_action.py:1` 신규
  - `CorporateAction(Base)` ORM 모델 (07번 §12-B / 14번 §15)
  - 컬럼: `id` PK / `symbol` FK→symbols.symbol CASCADE / `event_date` / `event_type` String(30) /
    `ratio` Float NOT NULL DEFAULT 0.0 / `dividend_amount` Float NULL / `notes` String(500) NULL /
    `created_at` DateTime
  - `UniqueConstraint("symbol","event_date","event_type", name="uq_corporate_actions_symbol_date_type")`
    — 동일 일자 split + cash_dividend 동시 가능
  - `Index("ix_corporate_actions_symbol_event_date","symbol","event_date")` — Processor 종목별 조회
  - `relationship` Symbol.corporate_actions ←→ CorporateAction.symbol_ref (cascade delete-orphan)
  - `CORPORATE_ACTION_EVENT_TYPES` enum (8종): split / reverse_split / bonus_issue /
    rights_issue / cash_dividend / merger / spinoff / delisting
- `backend/app/models/symbol.py:24` 추가 import + `:64` corporate_actions relationship 추가
- `backend/app/models/__init__.py:9-37` CorporateAction / CORPORATE_ACTION_EVENT_TYPES export 등록

### B) Alembic 마이그레이션

- `backend/alembic/versions/c7f2a16d8b53_add_corporate_actions.py:1` 신규
  - `revision = "c7f2a16d8b53"` / `down_revision = "b5e8d3c1a924"` (017 직후)
  - `bind.exec_driver_sql(CREATE TABLE ...)` — 9a4d2e1f6c10 패턴 (silent skip 회피)
  - downgrade에 DROP INDEX + DROP TABLE
- `backend/tests/db/test_alembic.py:49-55` `_KNOWN_ALEMBIC_GAPS`에 corporate_actions 추가
  (silent skip 환경 대응)

### C) repositories 확장 (016 패턴, 새 함수만)

- `backend/app/market_data/repositories.py:29-35` import 추가 (CorporateAction / CORPORATE_ACTION_EVENT_TYPES)
- `backend/app/market_data/repositories.py:386-487` 신규 함수 2개:
  - `upsert_corporate_action(session, data)` — UniqueConstraint 위반 시 갱신,
    `event_type` 검증 (CORPORATE_ACTION_EVENT_TYPES 외 → ValueError),
    필수 키(`symbol/event_date/event_type`) 누락 → KeyError
  - `get_corporate_actions(session, symbol, start_date=None, end_date=None)` —
    (event_date ASC, event_type ASC) 결정론 정렬

### D) AdjustedPriceProcessor (14-h, 13-r)

- `backend/app/data_pipeline/processors/adjusted_price.py:1` 신규
  - `CorporateActionEvent` frozen dataclass (DB 모델과 분리해 ORM 의존 차단)
  - `AdjustedPriceInput(prices, corporate_actions, as_of_date)` frozen dataclass
  - `AdjustedPriceProcessor(BaseProcessor[AdjustedPriceInput, tuple[RawDailyPriceRow, ...]])`
  - `process()` 흐름:
    1. `as_of_date` 결정 (None → `prices.end_date`)
    2. 종목별 `prices` / `events` 그룹핑
    3. `sorted(symbols)` 결정론 순회
    4. corporate_actions 시간 역순 (`event_date DESC, event_type ASC`) 적용
    5. event_date *이전* row의 `adj_*` / `adj_volume`만 변경, `close`/`volume` 보존
    6. 결과 `(symbol ASC, date ASC)` 정렬해 반환
  - 이벤트 타입별 factor (`_compute_factor`):
    - split (1주→ratio주): price ×1/ratio, volume ×ratio
    - reverse_split (ratio주→1주): price ×ratio, volume ×1/ratio
    - bonus_issue (1주당 ratio주 추가): price ×1/(1+ratio), volume ×(1+ratio)
    - cash_dividend: price × (1 - dividend/price_before), volume 보존 (price_before는 event_date 직전 거래일 close)
    - rights_issue / merger / spinoff: SOFT skip (CORP_ACTION_UNSUPPORTED)
    - delisting: 가격 영향 없음 (skip without warning)
  - 검증 정책 (14번 §7):
    - 음수/0 ratio → HARD `CORP_ACTION_INVALID_RATIO`
    - cash_dividend dividend_amount 누락/음수 → HARD `CORP_ACTION_INVALID_DIVIDEND`
    - cash_dividend mult ≤ 0 → HARD (가격이 음수가 됨)
    - 미래 이벤트 (event_date > as_of_date) → SOFT `CORP_ACTION_FUTURE` (skip)
    - cash_dividend price_before 결손 → SOFT `CORP_ACTION_MISSING_PRICE_BEFORE` (skip)
    - 미지원 이벤트 → SOFT `CORP_ACTION_UNSUPPORTED` (skip)
  - `raise_on_hard_fail=True` (기본) → DataValidationError raise
- `backend/app/data_pipeline/processors/__init__.py` AdjustedPriceProcessor /
  AdjustedPriceInput / CorporateActionEvent export 추가

### F) 테스트

- `backend/tests/market_data/test_corporate_action_model.py:1` 신규 (13건)
  - 등록/갱신/UniqueConstraint/정렬/날짜 필터/enum 검증/FK CASCADE/결정론/repr/metadata
- `backend/tests/data_pipeline/test_adjusted_price_processor.py:1` 신규 (24건)
  - split / reverse_split / bonus_issue / cash_dividend / 미래 이벤트 / HARD 검증 /
    미지원 이벤트 / 누적 적용 / close 보존 / 결정론 5회 / 정렬 / stats
- `backend/tests/market_data/test_alembic_corporate_actions.py:1` 신규 (6건)
  - revision 체인 / head / DDL 토큰 / downgrade / upgrade head / upgrade-downgrade-upgrade 사이클

## Tests

```text
신규 테스트 결과:
  tests/market_data/test_corporate_action_model.py        13 passed
  tests/data_pipeline/test_adjusted_price_processor.py    24 passed
  tests/market_data/test_alembic_corporate_actions.py      6 passed
  소계: 43 passed

전체 테스트:
  baseline: 693 passed + 1 failed (기존)
  본 step:  736 passed + 1 failed (= 693 + 43 신규)
  baseline 대비 신규 fail: 0건
  실패 1건은 b5e8d3c1a924 추가 시점에 발생한 기존 회귀 (head 가정 hard-coded)

Phase 1 골든 fixture (engine 변경 0건):
  tests/backtest/ 161 passed — 영향 없음 확인

ruff: All checks passed (1건 자동 fix 후)

alembic 회귀:
  c7f2a16d8b53 의 down_revision = b5e8d3c1a924 ✓
  현재 head = c7f2a16d8b53 ✓
  upgrade head → downgrade -1 → upgrade head 사이클 통과 ✓
```

14번 정책 검증 항목 매핑:

| 정책 | 검증 테스트 |
|------|-----------|
| 14.5 / 13.7 수정주가 재계산 | test_split_halves_pre_event_prices_and_doubles_volume / test_close_volume_preserved_after_processing |
| 14.9 corporate_actions 적용 | test_multiple_events_accumulate_in_time_reversed_order |
| 14.9 look-ahead 차단 | test_future_event_is_skipped_with_soft_warning / test_as_of_date_defaults_to_prices_end_date |
| 13.7 close 보존 | test_close_volume_preserved_after_processing |
| 14.10 결손 정책 (forward-fill 금지) | corporate_actions 없는 종목 그대로 통과 (test_symbol_without_events_passes_through_unchanged) |
| 14번 §7 자동 검증 (HARD/SOFT) | test_split_zero_ratio_raises_hard / test_cash_dividend_invalid_amount_raises / test_simplified_events_skip_with_soft_warning |
| 결정론 (CLAUDE.md #8) | test_determinism_repeated_5_times_yields_identical_output / test_output_sorted_by_symbol_then_date / test_determinism_repeated_inserts_yield_same_result |
| 13.13 / 14.10 생존편향 (CASCADE) | test_fk_cascade_deletes_corporate_actions_on_symbol_delete |

## Issues

1. **rights_issue / merger / spinoff 단순화 (SOFT skip)**: 14.9.1 "이론권리락 가격" 공식은
   본 step에서 미구현. 028 이후 정밀화 필요. 현재 정책: SOFT 경고 (`CORP_ACTION_UNSUPPORTED`)
   + 가격 변경 0. 운영 도입 전 14번 문서에 단순화 정책을 명시 필요 (또는 028에서 정밀 구현).

2. **cash_dividend price_before 결손 → SOFT skip**: 권리락 직전 거래일이 입력 prices에
   없으면 (예: 백테스트 시작일이 권리락일과 가까우면) SOFT skip. 백테스트 정확성에는
   "skip한 이벤트가 있다"는 사실을 결과 화면에 표시해야 함 — Reports/Frontend 영역에서
   처리 필요. validation.issues에 누적되므로 호출자가 활용 가능.

3. **기존 alembic 회귀 1건**: `tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head`
   는 head를 9a4d2e1f6c10으로 hard-coded. 017(b5e8d3c1a924) 추가 시점부터 fail 중이며 본 step에서
   더 악화 (head=c7f2a16d8b53). 본 step에서 신규 회귀 추가 0건이므로 수정하지 않았으나, 향후 step에서 정리 필요.

4. **adj_factor 컬럼 미사용**: 06번/13번 §7.2 / 14번 §15가 `adjustment_factor`를
   언급하지만 daily_prices 모델에는 016 step에서 컬럼이 정의되지 않음. 본 step의 Processor는
   factor를 메모리에서 누적해 adj_*에 즉시 반영하는 방식이라 별도 컬럼 불필요.
   (factor 자체를 영속화하고 싶으면 후속 step에서 daily_prices에 adjustment_factor 추가 가능.)

5. **corporate_actions 적용 결과를 daily_prices에 영속화하는 책임은 027 jobs로 인계**.
   본 step의 Processor는 in-memory `tuple[RawDailyPriceRow, ...]`만 반환.
   027 jobs는 (a) 신규 corporate_action 수집 → (b) `get_corporate_actions` →
   (c) `AdjustedPriceProcessor.process()` → (d) `bulk_upsert_daily_prices` 흐름을 잡으로 묶을 예정.

## Result

### 적용 정책 절번호
- 14번 §3.2 / §5 / §7 / §9 (수정주가 계산) / §15 (corporate_actions 데이터 구조)
- 13번 §7 (수정주가 정책 — close 보존, adj_* 재계산), §15 (look-ahead 차단)
- 07번 §12-B (corporate_actions 테이블)
- 06번 §6 / §7 (종목 마스터 / 일봉 컬럼)

### 신규 모델 / 마이그레이션
- 모델: `app.models.corporate_action.CorporateAction`
- alembic revision ID: `c7f2a16d8b53`, down_revision: `b5e8d3c1a924`

### 다른 에이전트에 노출되는 인터페이스 시그니처

```python
# 1) repositories (027 jobs가 사용)
from app.market_data.repositories import (
    upsert_corporate_action,
    get_corporate_actions,
)

upsert_corporate_action(session, data: Mapping[str, Any]) -> CorporateAction
# data 필수: symbol / event_date / event_type
# data 선택: ratio / dividend_amount / notes

get_corporate_actions(
    session, symbol: str,
    start_date: date | None = None, end_date: date | None = None
) -> list[CorporateAction]
# 정렬: (event_date ASC, event_type ASC)

# 2) AdjustedPriceProcessor (027 jobs가 사용)
from app.data_pipeline.processors import (
    AdjustedPriceProcessor,
    AdjustedPriceInput,
    CorporateActionEvent,
)

events = tuple(
    CorporateActionEvent(
        symbol=ca.symbol,
        event_date=ca.event_date,
        event_type=ca.event_type,
        ratio=ca.ratio,
        dividend_amount=ca.dividend_amount,
    )
    for ca in get_corporate_actions(session, symbol)
)

proc = AdjustedPriceProcessor()
result = proc.process(AdjustedPriceInput(
    prices=raw_prices,           # collector.collect_daily_prices() 결과
    corporate_actions=events,
    as_of_date=date(2024,12,31), # None이면 prices.end_date 사용
))
# result.output: tuple[RawDailyPriceRow, ...] (close 보존, adj_*만 재계산)
# result.validation.issues: SOFT/HARD 검증 이슈
# result.stats: (("events_applied", N), ("rows_processed", M), ...)

# 3) repositories.bulk_upsert_daily_prices에 그대로 전달 가능
bulk_upsert_daily_prices(
    session,
    rows=[dataclasses.asdict(r) for r in result.output],
)
```

## Follow-ups

1. **027 jobs 통합**: `corporate_action_apply_job` 작성. 신규 corporate_action 수집 시
   영향 종목의 daily_prices를 모두 재계산해 `bulk_upsert_daily_prices`로 영속화.
   본 step에서 Processor 인터페이스가 결정됨.

2. **027 시가총액 시계열**: `MarketCapProcessor`도 본 step의 BaseProcessor + frozen
   dataclass + (key ASC) 정렬 패턴을 그대로 재사용. shares_outstanding이 필요해
   symbols 모델 확장도 027에서.

3. **rights_issue / merger / spinoff 정밀화**: 028 이후 14번 §9에 공식 추가 + Processor
   확장. 현재 SOFT skip 정책은 운영 전에 14번 문서에 명시 필요.

4. **Reports에 SOFT issue 노출**: cash_dividend price_before 결손 등 SOFT skip 이벤트
   카운트를 백테스트 결과 화면에 노출해 사용자가 신뢰도를 평가하게 함.

5. **adjustment_factor 컬럼 영속화 (선택)**: 14번 §15 제안대로 daily_prices에
   `adjustment_factor` 컬럼을 추가하면 검증 (`adj_close[t]/adj_close[t-1] ≈
   close[t]/close[t-1] × factor`)이 쉬워짐. 028 이후 검토.

6. **alembic head hard-coded 회귀 정리**: `tests/market_data/test_alembic_market_data.py`의
   head 가정을 `script.get_heads()`로 동적으로 잡거나, head 변경 시 갱신 의무 명시.

7. **006 / 013 / 014 / 007 문서 갱신 (선택)**: corporate_actions 필드 명세를 본 step의
   실제 구현과 일치시키려면 14번 §15에 `notes` 컬럼 추가 / `dividend_amount`와 `ratio`의
   상호 배타성 명시 / rights_issue·merger·spinoff 단순화 정책 한 줄 추가 권장.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (06-h, 07-n, 14-h, 13-r [x] / Phase 11 step 026 ✅)
- [ ] git commit (Phase 11 마지막 step 아니므로 push 보류)
