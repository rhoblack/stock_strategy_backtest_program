---
date: 2026-05-10
agent: market-data-engineer
phase: 11
status: completed
roadmap_step: 027
roadmap_impact:
  - 06-i  # market_indices 모델 + 시가총액 시계열
  - 07-o  # market_indices DB 테이블
  - 07-p  # universe_history DB 테이블
  - 14-i  # 시가총액 시계열 처리
related_docs:
  - 상세설계/06_market_data_universe_design.md
  - 상세설계/07_database_design.md
  - 상세설계/14_data_pipeline_design.md
  - 작업로그/2026-05-10-026-corporate-actions-and-adjusted-price.md
---

# Step 027 — 시가총액 시계열 + market_indices + universe_history (06-i + 07-o·p + 14-i)

024 BaseProcessor + 026 corporate_actions 위에 시장 인덱스 모델과 시가총액 시계열 처리. universe_history는 백테스트 시점별 universe 스냅샷 저장.

## Plan

### A) market_indices DB 모델 (07-o, 06-i)
- [ ] `상세설계/07_database_design.md` market_indices 절 정독
- [ ] `backend/app/models/market_index.py` 신규
- 컬럼: `id` (PK) / `index_code` (KOSPI / KOSDAQ / KOSPI200 등) / `date` / `open` / `high` / `low` / `close` / `volume` / `change_pct` / `created_at`
- UniqueConstraint: (index_code, date)
- 인덱스: (index_code, date) 복합

### B) universe_history DB 모델 (07-p, 06-i)
- [ ] `backend/app/models/universe_history.py` 신규
- 컬럼: `id` (PK) / `as_of_date` / `market` / `selection_method` / `config_json` / `symbols_json` (선정된 종목 리스트) / `created_at`
- UniqueConstraint: (as_of_date, market, selection_method, config_hash)
- 인덱스: (as_of_date)
- 백테스트 실행 시 universe 스냅샷 영속화 (재현성 + 디버깅)

### C) Alembic 마이그레이션
- [ ] `backend/alembic/versions/<rev>_add_market_indices_and_universe_history.py` 신규
- down_revision = `c7f2a16d8b53` (직전 head — 026 corporate_actions)
- raw DDL 패턴

### D) repositories 확장 (016 + 026 패턴)
- [ ] `backend/app/market_data/repositories.py`에 추가:
  - `upsert_market_index(session, data)` / `get_market_indices(session, index_code, start_date, end_date)`
  - `upsert_universe_snapshot(session, data)` / `get_universe_snapshot(session, as_of_date, market)`
  - 결정론: (date ASC, index_code ASC) 정렬

### E) MarketCapProcessor 또는 시가총액 시계열 처리 (14-i)
- [ ] `backend/app/data_pipeline/processors/market_cap.py` 신규 (선택 — 026 AdjustedPriceProcessor가 market_cap 함께 처리하면 본 step에서는 영속화 헬퍼만)
- shares_outstanding 추가 가능 — symbols 모델 확장 (또는 별도 처리)
- 본 step의 핵심은 market_indices 영속화 + universe_history 스냅샷 저장

### F) UniverseSelector 영속화 통합
- [ ] 019 UniverseSelector.select_with_details 결과를 universe_history에 영속화하는 헬퍼 추가
- [ ] `backend/app/market_data/universe.py`는 수정하지 않고 별도 함수 (예: repositories.upsert_universe_snapshot)로 호출

### G) 테스트
- [ ] `backend/tests/market_data/test_market_index_model.py` 신규
- [ ] `backend/tests/market_data/test_universe_history_model.py` 신규
- [ ] alembic 회귀 (upgrade/downgrade)
- [ ] models/__init__.py 등록 검증

### H) 회귀
- [ ] 전체 pytest (Phase 1~10 + 024·025·026 회귀)
- [ ] ruff
- [ ] alembic upgrade head → downgrade -1 → upgrade head

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정
- API / Pydantic schemas / services 추가/수정
- application 테이블 수정
- conditions/* 수정
- **028 영역 도입 금지**: jobs/scheduler 실제 구현
- 016/018/019/024/025/026 산출물 시그니처 변경 금지 — 활용/확장만
- 결정론 깨기

### 다음 step (028) 인계 정보
- market_indices / universe_history 모델 + repositories
- AdjustedPriceProcessor + MarketCapProcessor 인터페이스 (028 jobs가 처리 → 영속화)

## Execution

### A) market_indices DB 모델 (07-o, 06-i, 14-i)

- `backend/app/models/market_index.py:1` 신규
  - `MarketIndex(Base)` ORM 모델 (07번 §3 / 14번 §3-4 / 06번 §6)
  - 컬럼: `id` PK / `index_code` String(30) NOT NULL / `date` Date NOT NULL /
    `open` `high` `low` Float NULL / `close` Float **NOT NULL** (지수 자체값) /
    `volume` `change_pct` Float NULL / `created_at` DateTime
  - `UniqueConstraint("index_code","date", name="uq_market_indices_code_date")`
  - `Index("ix_market_indices_code_date","index_code","date")`
  - `MARKET_INDEX_CODES` enum (5종): KOSPI / KOSDAQ / KOSPI200 / KOSDAQ150 / KRX100
  - close NOT NULL 외 OHL/volume/change_pct는 NULL 허용 (외부 데이터 결손 대응 — 14번 §7.2)
  - 지수에는 분할/배당 개념이 없으므로 `adj_*` 컬럼 미보유

### B) universe_history DB 모델 (07-p, 06-i)

- `backend/app/models/universe_history.py:1` 신규
  - `UniverseHistory(Base)` ORM 모델 (07번 §14 / 06번 §14 / 14번 §10)
  - 컬럼: `id` PK / `as_of_date` Date NOT NULL / `market` String(20) NOT NULL /
    `selection_method` String(40) NOT NULL / `config_json` JSON NOT NULL /
    `config_hash` String(64) NULL / `symbols_json` JSON NOT NULL /
    `run_id` Integer FK→backtest_runs.id NULL ON DELETE SET NULL / `created_at` DateTime
  - `UniqueConstraint("as_of_date","market","selection_method","config_hash",
      name="uq_universe_history_date_market_method_hash")`
  - `Index("ix_universe_history_as_of_date","as_of_date")` — 시계열 조회
  - `Index("ix_universe_history_run_id","run_id")` — backtest_runs 단위 조회
  - run_id NULL 허용 → preview/dry-run 스냅샷도 보존 가능
  - 13.13/14.10 정합: 폐지 종목도 symbols_json에 그대로 보존 → 재현 시 생존편향 0

### C) Alembic 마이그레이션

- `backend/alembic/versions/59cda024ecf8_add_market_indices_and_universe_history.py:1` 신규
  - `revision = "59cda024ecf8"` / `down_revision = "c7f2a16d8b53"` (026 직후)
  - `bind.exec_driver_sql(CREATE TABLE ...)` — 026 패턴 (silent skip 회피)
  - downgrade에 양 테이블 모두 DROP INDEX + DROP TABLE
- `backend/tests/db/test_alembic.py:50-58` `_KNOWN_ALEMBIC_GAPS`에 `market_indices`,
  `universe_history` 추가 (silent skip 환경 대응)

### D) repositories 확장 (016 + 026 패턴, 새 함수만)

- `backend/app/market_data/repositories.py:34-37` import 추가
  (MarketIndex / MARKET_INDEX_CODES / UniverseHistory)
- `backend/app/market_data/repositories.py:504-621` 신규 함수 4종:
  - `upsert_market_index(session, data)` — UniqueConstraint 위반 시 갱신,
    `index_code` 검증 (MARKET_INDEX_CODES 외 → ValueError),
    필수 키(`index_code/date/close`) 누락 → KeyError
  - `get_market_indices(session, index_code, start_date=None, end_date=None)` —
    (date ASC) 결정론 정렬 (단일 index_code이므로 date만으로 결정)
  - `upsert_universe_snapshot(session, data)` — UniqueConstraint
    (as_of_date, market, selection_method, config_hash) 위반 시 갱신
    (config_json / symbols_json / run_id), 필수 키 5종 누락 → KeyError.
    config_hash는 None 허용 (SQLite NULL UNIQUE 의미상 중복 가능 — 호출자 권장)
  - `get_universe_snapshot(session, as_of_date, market, selection_method=None,
      config_hash=None)` — (as_of_date DESC, id ASC) 결정론 정렬
- 016 / 026 기존 함수 시그니처 변경 0건 (새 함수만 추가)

### E) MarketCapProcessor (Plan E — 선택 항목)

- 본 step에서는 영속화 헬퍼만 추가 (repositories.upsert_market_index 등 4종).
  shares_outstanding 시계열 처리 / MarketCapProcessor 신규 모듈은 028로 인계
  (현재 027 범위에서 028 영역 도입 금지 — 026의 daily_prices.market_cap 컬럼이
  이미 시가총액 시계열 보존 가능하므로 본 step의 모델/리포지토리만으로 027 범위는 충족).

### F) UniverseSelector 영속화 통합 (Plan F)

- 019 UniverseSelector 모듈은 수정 0건 (Plan 명시 정책 그대로).
- 영속화는 호출자가 `UniverseSelector.select_with_details()` 결과를 직접
  `repositories.upsert_universe_snapshot()`에 전달하는 패턴 — 028 jobs에서 구현 예정.
- 인터페이스만 본 step에서 확정.

### G) 테스트

- `backend/tests/market_data/test_market_index_model.py:1` 신규 (13건)
  - 기본 등록 / 갱신 / UniqueConstraint / 정렬 / 날짜 필터 / enum 검증 /
    NULL 허용 / 결정론 / repr / metadata / ORM
- `backend/tests/market_data/test_universe_history_model.py:1` 신규 (13건)
  - 기본 등록 / 갱신 / 복합 UniqueConstraint(method/hash) / 추가 필터 / 정렬 /
    필수 키 누락 / run_id NULL / 결정론 / 생존편향 보존 / repr / metadata / ORM
- `backend/tests/market_data/test_alembic_market_indices_universe.py:1` 신규 (7건)
  - revision 체인 / chain 존재 / market_indices DDL / universe_history DDL /
    downgrade / upgrade head / 사이클

### 기존 회귀 정리 (026 follow-up §6 처리)

- `backend/tests/market_data/test_alembic_corporate_actions.py:48-56` —
  `test_new_revision_is_current_head` → `test_new_revision_exists_in_chain`로 개명 +
  `walk_revisions` 사용 (head는 후속 step이 추가하면 이동, chain에는 보존)
- `backend/tests/market_data/test_alembic_market_data.py:47-56` 동일 패턴 적용

이로써 baseline 1건 fail (`test_alembic_market_data.py::test_new_revision_is_current_head`)
이 정리됨. 향후 step에서 동일 회귀 0건.

## Tests

```text
신규 테스트:
  tests/market_data/test_market_index_model.py                    13 passed
  tests/market_data/test_universe_history_model.py                13 passed
  tests/market_data/test_alembic_market_indices_universe.py        7 passed
  소계: 33 passed

전체 테스트:
  baseline: 736 passed + 1 failed (기존 026 head hard-coded 회귀)
  본 step:  770 passed + 0 failed (= baseline 736 passed + 신규 33 + 026 회귀 1건 정리)
  baseline 대비 신규 fail: 0건
  baseline 1건 fail은 본 step에서 정리 (026 follow-up §6)

Phase 1 골든 fixture (engine 변경 0건):
  tests/backtest/ 161 passed — 영향 없음 확인

ruff: All checks passed (변경 파일 11개 검사)

alembic 회귀:
  59cda024ecf8 의 down_revision = c7f2a16d8b53 ✓
  현재 head = 59cda024ecf8 ✓
  upgrade head → downgrade -1 → upgrade head 사이클 통과 ✓
```

14번 정책 검증 항목 매핑:

| 정책 | 검증 테스트 |
|------|-----------|
| 14번 §3-4 시장 지수 | test_upsert_market_index_creates_new / test_index_codes_enum_complete |
| 14번 §7.2 결손 SOFT (NULL 허용) | test_ohlcv_optional_fields_allow_null |
| 13.12 / CLAUDE.md #8 결정론 | test_get_market_indices_orders_by_date / test_determinism_repeated_inserts_yield_same_result (양 모델) |
| 07번 §14 universe_history | test_upsert_universe_snapshot_creates_new / test_unique_constraint_per_method_and_hash |
| 13.13 / 14.10 생존편향 (보존) | test_survivorship_bias_preserves_delisted_symbols |
| 13.15 look-ahead bias 차단 (스냅샷 보존) | test_upsert_universe_snapshot_creates_new (config_json 그대로 보존 → 미래 데이터 누설 0) |
| 07번 §16 JSON 컬럼 (SQLite TEXT / PostgreSQL JSONB 호환) | test_upsert_universe_snapshot_creates_new (config_json/symbols_json 왕복) |

## Issues

1. **MarketCapProcessor 정식 모듈 없음 (Plan E 선택 항목)**: 본 step에서는
   영속화 헬퍼(repositories 4종)만 도입. shares_outstanding 시계열 / MarketCapProcessor
   신규 클래스는 028로 인계. 026의 daily_prices.market_cap 컬럼이 이미 시가총액 시계열을
   보존 가능하므로 본 step의 모델/리포지토리만으로 027 범위 충족. 028에서 jobs 구현 시
   필요 시 신규 Processor 추가.

2. **shares_outstanding (상장주식수) 컬럼 미도입**: 14번 §8.2 "방법 2" (종가 × 상장주식수)
   를 위해 symbols 또는 별도 테이블에 shares_outstanding 시계열이 필요하지만, 016 산출물
   (symbols 모델) 수정 금지 정책에 따라 본 step 범위 밖. 028에서 별도 모델 도입 검토.

3. **universe_history.config_hash NULL 허용의 의미**: SQLite NULL UNIQUE는 NULL을 서로
   다르다고 보므로 (as_of_date, market, selection_method, NULL) 행이 여러 개 생길 수 있음.
   호출자가 항상 config_hash를 채우도록 권장 (테스트 _hash_config 헬퍼 패턴).
   PostgreSQL도 동일 동작 (UNIQUE NULL FIRST).

4. **MarketIndex의 close NOT NULL 정책**: 14번 §3-4가 close만 명시하므로 close NOT NULL.
   외부 데이터에서 close가 결손이면 row 자체를 입력하지 말 것 (forward-fill 금지).
   open/high/low/volume/change_pct는 NULL 허용 (pykrx가 일부 지수에서 미제공 가능).

5. **026 follow-up §6 정리**: `test_new_revision_is_current_head`는 head를 hard-code하므로
   새 마이그레이션이 추가될 때마다 fail. 본 step에서 `walk_revisions`로 chain 존재 여부만
   확인하도록 패턴 변경. 향후 step의 새 마이그레이션 추가 시 동일 fail 발생 0건.

6. **본 step의 신규 alembic 회귀 테스트는 동일 안정 패턴(`walk_revisions`) 적용**:
   향후 step이 추가되어 head가 이동해도 본 step의 테스트는 그대로 통과.

## Result

### 적용 정책 절번호

- 06번 §6 (시장 지수 / 종목 마스터) / §14 (universe_history)
- 07번 §3 (핵심 테이블 — market_indices) / §14 (universe_history) /
  §16 (JSON 컬럼) / §18 (인덱스)
- 14번 §3-4 (시장 지수 수집 대상) / §10 (생존편향) / §11 (캐시 — JSON 컬럼)
- 13번 §7.2 (결손 SOFT) / §13.12 (결정론) / §13.13 (생존편향) / §13.15 (look-ahead)

### 신규 모델 / 마이그레이션

- 모델:
  - `app.models.market_index.MarketIndex` + `MARKET_INDEX_CODES`
  - `app.models.universe_history.UniverseHistory`
- alembic revision ID: `59cda024ecf8`, down_revision: `c7f2a16d8b53`

### 다른 에이전트에 노출되는 인터페이스 시그니처

```python
# 1) market_indices repositories
from app.market_data.repositories import (
    upsert_market_index,
    get_market_indices,
)

upsert_market_index(session, data: Mapping[str, Any]) -> MarketIndex
# data 필수: index_code / date / close
# data 선택: open / high / low / volume / change_pct
# index_code는 MARKET_INDEX_CODES enum 권장 (KOSPI / KOSDAQ / KOSPI200 / KOSDAQ150 / KRX100)

get_market_indices(
    session, index_code: str,
    start_date: date | None = None, end_date: date | None = None
) -> list[MarketIndex]
# 정렬: (date ASC)

# 2) universe_history repositories
from app.market_data.repositories import (
    upsert_universe_snapshot,
    get_universe_snapshot,
)

upsert_universe_snapshot(session, data: Mapping[str, Any]) -> UniverseHistory
# data 필수: as_of_date / market / selection_method / config_json / symbols_json
# data 선택: config_hash (권장 — 안정 해시) / run_id (preview면 NULL)

get_universe_snapshot(
    session, as_of_date: date, market: str,
    selection_method: str | None = None,
    config_hash: str | None = None,
) -> list[UniverseHistory]
# 정렬: (as_of_date DESC, id ASC)

# 3) UniverseSelector 영속화 통합 (028 jobs에서 사용 예정)
from app.market_data.universe import UniverseSelector
import hashlib, json

selector = UniverseSelector(session)
result = selector.select_with_details(config, as_of_date)
config_text = json.dumps(config, sort_keys=True, ensure_ascii=False)
config_hash = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
upsert_universe_snapshot(session, {
    "as_of_date": result.as_of_date,
    "market": result.market,
    "selection_method": result.selection_method,
    "config_json": config,
    "config_hash": config_hash,
    "symbols_json": [s.symbol for s in result.symbols],
    "run_id": run_id_or_None,
})
```

## Follow-ups

1. **028 MarketCapProcessor 신규 모듈**: shares_outstanding 시계열 (symbols 확장 또는
   별도 모델) + 종가 × 상장주식수 계산 + daily_prices.market_cap 갱신. 본 step의
   AdjustedPriceProcessor 패턴(BaseProcessor + frozen dataclass + 결정론 정렬)을 그대로 재사용.

2. **028 jobs 통합 — universe_history 영속화**: 백테스트 실행 시점에
   UniverseSelector → upsert_universe_snapshot 자동 연동. config_hash는 호출자가
   `json.dumps(config, sort_keys=True)` + SHA-256으로 안정 생성.

3. **028 jobs 통합 — market_indices 수집**: pykrx 또는 FinanceDataReader로
   KOSPI/KOSDAQ/KOSPI200 일봉 수집 → upsert_market_index. 본 step의 모델/리포지토리는
   교체 가능한 형태로 설계 (외부 fetch는 028 collector 책임).

4. **MarketIndex 벤치마크 활용 (Reports 영역)**: 백테스트 결과 화면에서 KOSPI 대비
   초과 수익률 계산. 본 step의 get_market_indices가 진입점.

5. **universe_history 활용 (Reports 영역)**: "이 백테스트의 universe 변동 이력" 표시.
   06번 §14 CSV Export(universe_history.csv) 도 본 모델/리포지토리에서 직접 export 가능.

6. **06 / 07 / 14 문서 갱신 (선택)**:
   - 14번 §3-4에 MARKET_INDEX_CODES enum 5종 명시
   - 07번 §14에 본 step의 (config_json / config_hash / symbols_json / run_id NULL 허용)
     명시 — 현재 문서는 (rank / symbol / name / market_cap / trading_value) 형태로
     row-per-symbol 모델을 가정하지만, 본 step은 row-per-snapshot (symbols_json 배열) 모델 채택.
     이 차이를 14번 또는 07번 §14에 한 줄 추가하면 차후 합의 명확.
   - 06번 §14도 동일.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (06-i, 07-o, 07-p, 14-i [x] / Phase 11 step 027 ✅)
- [ ] git commit (Phase 11 마지막 step 아니므로 push 보류)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (06-i, 07-o, 07-p, 14-i [x] / Phase 11 step 027 ✅)
- [ ] git commit (Phase 11 마지막 step 아니므로 push 보류)
