---
date: 2026-05-11
agent: market-data-engineer
phase: 16
status: completed
roadmap_step: "048"
roadmap_impact:
  - 14-l
related_docs:
  - 상세설계/14_data_pipeline_design.md
  - 상세설계/06_market_data_universe_design.md
---

# step 048 — HistoricalBackfillJob 실제 구현 (체크포인트 저장 + rate-limit 대응)

## Plan

> 영향 체크박스 (완료 시 [x] 갱신):
> - `14-l`: historical_backfill_job (체크포인트 + rate-limit 대응 포함)

### 배경

Phase 11 step 028에서 `HistoricalBackfillJob` 클래스의 **골격(스켈레톤)**은 이미 구현됐습니다.
그러나 실제 운영에 필요한 다음 기능이 미구현 상태입니다:

- **체크포인트 저장**: 2,800 종목 × 10년치 수집 도중 중단 시 처음부터 재수집하지 않도록 진행 상황을 DB 또는 파일에 기록해야 합니다.
- **rate-limit 대응**: pykrx는 KRX 스크래핑 기반이므로 연속 요청 시 차단될 수 있습니다. 요청 간격 제어 + 차단 감지 + 자동 일시정지 로직이 필요합니다.
- **단계별 실행**: 14.6.1 설계서의 수집 시나리오 순서 (종목 마스터 → 캘린더 → corporate_actions → 일봉 → 수정주가 → 시가총액 → 검증) 를 단계별로 실행하고 단계 완료 상태도 체크포인트에 기록합니다.

### 구현 단계

- [ ] 1. 체크포인트 모델 설계
  - `BackfillCheckpoint` 데이터클래스 또는 DB 테이블 결정
  - 저장할 정보: 작업 ID, 시작/종료 날짜, 처리 완료 종목 목록, 현재 단계, 마지막 성공 종목
  - MVP는 JSON 파일 체크포인트 (`data/backfill_checkpoint.json`) 방식 채택 (DB 스키마 추가 없이)

- [ ] 2. rate-limit 제어 유틸리티 구현
  - `RateLimiter` 클래스: 요청 간 최소 대기 시간 적용 (기본 0.5초)
  - 차단 감지: HTTP 에러 코드 / 빈 응답 / 연속 실패 N회
  - 자동 일시정지: 차단 감지 시 configurable 대기 (기본 30분) 후 재개
  - 설계서 §6.3 재시도 정책 (1s→5s→30s) 과 연동 — 기존 `PykrxCollector` retry와 중복 않도록 계층 구분

- [ ] 3. `HistoricalBackfillJob.run()` 실제 구현
  - 체크포인트 로드 → 이어서 실행 (또는 신규 시작)
  - 단계별 루프: symbols / calendar / corporate_actions / daily_prices / adj_price / market_cap / validation
  - 종목별 완료 후 체크포인트 즉시 저장 (중단 안전성)
  - rate-limit 대응 적용 (요청 간격 sleep + 차단 시 일시정지)
  - 진행 로그 출력 (종목 N/M, 경과 시간, 예상 잔여 시간)

- [ ] 4. 체크포인트 재개 로직 검증
  - 특정 종목 처리 완료 후 강제 중단 → 재실행 시 해당 종목 이후부터 이어받는지 확인

- [ ] 5. 단위 테스트 작성
  - 체크포인트 저장/로드 테스트
  - rate-limit 대기 적용 확인 (mock sleep)
  - 차단 감지 → 일시정지 → 재개 시나리오 (mock)
  - 부분 완료 상태에서 이어받기 시나리오

- [ ] 6. 전체 회귀 pytest 통과 확인 (1232 PASS 기준선 유지)

### 정책 참조

- 14.6.1 초기 백필 수집 시나리오 (7단계)
- 14.6.3 재시도/백오프 정책 (PykrxCollector와 계층 구분 필요)
- 14.6.4 KRX 차단 대응 (0.5초 간격 / 30분 자동 일시정지)
- 체크포인트 파일 경로: `data/backfill_checkpoint.json`

## Execution

### 신규 작성 파일

| 파일 | 주요 내용 |
|------|----------|
| `backend/app/data_pipeline/utils/__init__.py` | utils 패키지 초기화 |
| `backend/app/data_pipeline/utils/rate_limiter.py:1-129` | `RateLimiter` dataclass — 0.5초 간격 / 연속 실패 N회 block_sleep / sleep_fn 주입 지원 |
| `backend/tests/data_pipeline/test_historical_backfill_job.py:1-700` | 신규 25개 테스트 |

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/data_pipeline/jobs/historical_backfill.py:1-450` | 전면 재작성 — `BackfillCheckpoint` dataclass + 7단계 `run()` + rate-limit |
| `backend/app/data_pipeline/jobs/__init__.py` | `BackfillCheckpoint`, stage 상수 7개 노출 |
| `backend/app/data_pipeline/__init__.py` | `RateLimiter`, `BackfillCheckpoint`, stage 상수 노출 |
| `backend/tests/data_pipeline/test_jobs_historical_backfill.py` | 모든 테스트에 `tmp_path` 격리 + 단일 종목 실패 정책 분리 테스트 추가 |

### 인터페이스 결정 근거

**14.6.1 초기 백필 7단계** 그대로 순서 실행:
```
STAGE_SYMBOLS → STAGE_CALENDAR → STAGE_CORPORATE_ACTIONS →
STAGE_DAILY_PRICES → STAGE_ADJUSTED_PRICES → STAGE_MARKET_CAP → STAGE_VALIDATE
```

**14.6.4 KRX 차단 대응**:
- `RateLimiter.wait()`: 요청 전 호출, min_interval_seconds(0.5) 보장
- `consecutive_failures >= max_consecutive_failures` → `block_sleep_seconds(1800)` 적용
- `sleep_fn`, `monotonic_fn` 주입으로 테스트 시 실제 sleep 없이 검증

**체크포인트 파일** (`data/backfill_checkpoint.json`):
- `as_of_date` 불일치 시 신규 시작 (다른 백필 범위와 혼용 방지)
- `mark_stage_done()` 호출 즉시 저장 → 단계 경계에서 중단 안전
- `update_last_symbol()` 종목별 즉시 저장 → daily_prices 루프 도중 중단 복구 가능

**단일 종목 실패 = 경고 처리** (설계 결정):
- 2,800 종목 중 1개 실패 시 전체 잡 실패로 이어지면 안 됨
- `except Exception: warnings.append(...)` + `finally: checkpoint.update_last_symbol()`
- symbols/calendar 단계 실패는 `raise RuntimeError(...)` → 잡 전체 실패로 전파

**corporate_actions 단계 no-op** (14번 §3 "027~ 후속 step에서 별도 메서드 추가 예정"):
- `BaseCollector`에 `collect_corporate_actions` 미지원
- 경고 1건 누적 후 단계 완료 표기

## Tests

```
backend/.venv/Scripts/python.exe -m pytest backend/tests/data_pipeline/test_historical_backfill_job.py -v
→ 25 passed in 4.81s

backend/.venv/Scripts/python.exe -m pytest backend/ -q
→ 1258 passed, 0 failed, 10 warnings in 30.01s
   (기준선 1232 + 신규 26개 = 1258)
```

### 14번 정책 검증 매핑

| 정책 | 테스트 |
|------|--------|
| 14.6.1 초기 백필 7단계 순서 | `test_backfill_job_completes_all_stages` — 7단계 모두 체크포인트 표기 확인 |
| 14.6.4 KRX 차단 대응 (0.5초 간격) | `test_rate_limiter_enforces_min_interval` — sleep_fn mock 검증 |
| 14.6.4 연속 실패 N회 → 30분 일시정지 | `test_rate_limiter_block_after_failures` — 1800초 sleep 검증 |
| 체크포인트 저장/로드 | `test_checkpoint_save_and_load` |
| 재시작 시 완료 단계 스킵 | `test_checkpoint_resume_skips_completed_stages` |
| daily_prices last_symbol 이어받기 | `test_daily_prices_resumes_from_last_symbol` |
| as_of_date 변경 시 신규 시작 | `test_checkpoint_resume_with_different_as_of_date_restarts` |
| 결정론 (14.12) | `test_backfill_job_determinism_independent_runs` — 독립 DB 두 벌 동일 stats |
| JSON 결정론 (sort_keys=True) | `test_checkpoint_json_is_sorted_keys` |

## Issues

1. **기존 `test_jobs_historical_backfill.py` 격리 문제**
   - 기존 테스트가 `checkpoint_path` 미지정 → 기본 경로 `data/backfill_checkpoint.json` 사용
   - 첫 번째 실행 시 파일 생성, 두 번째 실행 시 이미 완료로 오인 → 테스트 실패
   - 해결: 모든 기존 테스트에 `tmp_path` 추가 + `checkpoint_path` 명시

2. **`test_backfill_normalizes_collector_failure` 정책 변경**
   - 구 구현: `collect_daily_prices` 실패 → 잡 전체 실패
   - 신 구현: 단일 종목 daily_prices 실패 → 경고로만 처리 (정책 변경)
   - 해결: 테스트를 `collect_symbols` 실패 케이스로 수정 + 단일 종목 실패 경고 테스트 별도 추가

3. **RateLimiter monotonic_fn 호출 순서**
   - `wait()` 내부에서 `monotonic_fn()`을 최대 3번 호출 (wait 시작 / block 후 갱신 / last_request_time 갱신)
   - 테스트 시 mock 시퀀스를 실제 호출 순서에 맞게 설계해야 함
   - 해결: 두 번의 `wait()` 호출 시나리오로 재설계

4. **corporate_actions 단계 no-op**
   - `BaseCollector.collect_corporate_actions` 미지원 (025 주석)
   - 경고로 처리, 실제 수집은 collector에 메서드 추가 후 활성화 필요

## Result

- **적용 정책 절번호**: 14.6.1 (초기 백필 7단계), 14.6.4 (KRX 차단 대응), 14.12 (결정론)
- **신규 테이블**: 없음
- **신규 마이그레이션**: 없음

### 다른 에이전트에 노출되는 인터페이스

```python
# 체크포인트 (신규)
from app.data_pipeline.jobs.historical_backfill import BackfillCheckpoint
checkpoint = BackfillCheckpoint.load(path)   # None이면 신규 시작
checkpoint.is_stage_done("symbols")          # bool
checkpoint.mark_stage_done("symbols", path)  # 즉시 저장

# RateLimiter (신규)
from app.data_pipeline.utils.rate_limiter import RateLimiter
limiter = RateLimiter(
    min_interval_seconds=0.5,
    max_consecutive_failures=5,
    block_sleep_seconds=1800.0,
    sleep_fn=time.sleep,   # 테스트: mock 주입 가능
)
limiter.wait()              # 요청 전 호출
limiter.record_success()    # 요청 성공
limiter.record_failure()    # 요청 실패

# HistoricalBackfillJob (재구현)
from app.data_pipeline.jobs.historical_backfill import (
    HistoricalBackfillJob, HistoricalBackfillConfig,
    ALL_STAGES, STAGE_SYMBOLS, STAGE_DAILY_PRICES, ...
)
job = HistoricalBackfillJob(
    config=HistoricalBackfillConfig(
        start_date=date(2015, 1, 1),
        end_date=date(2024, 12, 31),
        checkpoint_path=Path("data/backfill_checkpoint.json"),
        rate_limiter=RateLimiter(),  # None이면 기본값
    ),
    collector=PykrxCollector(),
    session_factory=SessionLocal,
)
result = job.run()  # 체크포인트 이어받기 자동
```

## Follow-ups

- `BaseCollector.collect_corporate_actions` 메서드 추가 시 corporate_actions 단계 실제 수집으로 교체 필요
- `market_cap` 단계: 별도 집계 로직 필요 여부 확인 (현재는 pykrx daily_prices market_cap 필드 신뢰)
- 실제 운영 시 `block_sleep_seconds=1800` 대기는 매우 길므로 환경변수 오버라이드 방법 제공 권장
- `data/backfill_checkpoint.json`이 `.gitignore`에 추가되어야 함 (테스트 부산물 방지)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 048 마무리" 지시. PM이 Phase 로드맵 step ✅ + 14-l [x] + 진행률 표 손계산을 직접 Edit. (영향 체크박스 ID: 14-l)
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step(051)이 완료된 후**: `git push origin main` 자동 실행 (의무)
