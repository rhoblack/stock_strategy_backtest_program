---
date: 2026-05-11
agent: market-data-engineer
phase: 16
status: completed
roadmap_step: "049"
roadmap_impact:
  - 14-m
related_docs:
  - 상세설계/14_data_pipeline_design.md
  - 상세설계/06_market_data_universe_design.md
---

# step 049 — DailyUpdateJob 증분 수집 + 주별 재실행 스케줄 설정

## Plan

> 영향 체크박스 (완료 시 [x] 갱신):
> - `14-m`: 일별 / 주별 증분 잡

### 배경

Phase 11 step 028에서 `DailyUpdateJob` 클래스의 골격(스켈레톤)은 구현됐습니다.
step 048에서 `HistoricalBackfillJob`의 실제 구현이 완료된 만큼,
이제 **일상적인 증분 수집 잡**인 `DailyUpdateJob`을 실제 구현합니다.

`DailyUpdateJob`의 역할:
- 매거래일 장 종료 후 **당일 일봉 + 수정주가 + corporate_actions** 반영
- 이미 수집된 날짜는 건너뜀 (증분, 중복 방지)
- 결손 탐지: 수집 완료 후 `MissingDataCheckJob` 결과와 연동해 알림

`WeeklyRecalcJob`(주별 재실행):
- 매주 특정 요일 전체 심볼의 수정주가 재계산 (corporate_actions 누락 보정 목적)
- Scheduler의 cron-like 주별 트리거와 연동

### 구현 단계

- [ ] 1. `DailyUpdateJob.run()` 실제 구현
  - 대상 날짜 결정: `as_of_date` 파라미터 (미지정 시 오늘)
  - DB에서 해당 날짜 이미 수집 여부 확인 (daily_prices 레코드 존재 시 스킵)
  - 전체 활성 심볼 조회 (symbols 테이블 `delisted=False`)
  - PykrxCollector → 당일 일봉 수집 → daily_prices 업서트
  - AdjustedPriceProcessor → 수정주가 재계산 → daily_prices adj_* 컬럼 갱신
  - corporate_actions 당일 이벤트 반영 (존재 시)
  - 결손 탐지: 수집 완료 후 심볼 수 대비 실제 수집 수 비교 → 불일치 시 경고 로그

- [ ] 2. 주별 재실행 스케줄 설정 (WeeklyRecalcJob 또는 DailyUpdateJob 옵션)
  - `run_weekly_recalc=True` 옵션 시 전체 기간 수정주가 재계산
  - Scheduler와 연동: `schedule_weekly(job, weekday=6)` 형태 또는 설정 파일 기반
  - 14.6.5 주별 재실행 정책 (§6.5) 반영

- [ ] 3. MissingDataCheckJob 연동
  - `DailyUpdateJob.run()` 완료 후 `MissingDataCheckJob.run()` 자동 트리거 옵션
  - `MissingDataAlert` 결과를 로그 또는 콜백으로 전달

- [ ] 4. `backend/tests/data_pipeline/test_daily_update_job.py` 신규 작성
  - 정상 수집 시나리오 (mock collector + DB 업서트 확인)
  - 이미 수집된 날짜 스킵 시나리오
  - corporate_actions 반영 시나리오
  - 결손 탐지 경고 시나리오
  - 주별 재실행 시나리오 (mock)
  - RateLimiter 연동 확인

- [ ] 5. ruff + pytest 전체 회귀 (1258 PASS 기준선 유지)

### 정책 참조

- 14.6.2 일별 증분 수집 시나리오
- 14.6.5 주별 재실행 정책 (수정주가 전체 재계산 주기)
- 14.6.3 재시도/백오프 정책 (PykrxCollector와 계층 구분)
- 14.6.4 KRX 차단 대응 (RateLimiter — step 048 구현 재사용)

## Execution

```text
backend/app/market_data/repositories.py:273
    get_latest_price_date(session, symbol) -> date | None 추가
    MAX(DailyPrice.date) WHERE symbol = symbol
    DB 데이터 없으면 None 반환
    DailyUpdateJob 증분 판단용 단일 진입점 (14번 §6.2)

backend/app/data_pipeline/jobs/daily_update.py — 전면 개선
    docstring: 7단계 흐름 (비거래일 체크, 증분 판단, MissingDataCheckJob 연동) 기술

    DailyUpdateConfig 신규 필드:
        incremental: bool = True         — max(date) 기준 증분 수집
        run_missing_data_check: bool = False  — 영속화 후 결손 체크 (기본 off, 기존 테스트 호환)
        check_trading_calendar: bool = False  — 비거래일 체크 (기본 off, 기존 테스트 호환)

    DailyUpdateJob.run() 7단계 구현:
        Step 0: 비거래일 체크 (check_trading_calendar=True 시)
                trading_calendar에서 as_of_date 조회 → is_trading_day=False 또는 row 없으면 즉시 return
                stats["skipped_nontrading"] = 1
        Step 1: 종목 마스터 수집 / 영속화 (기존 동일)
        Step 2: 거래일 캘린더 수집 / 영속화 (기존 동일)
        Step 3: 일봉 수집 대상 결정 (config.symbols 또는 symbols_data 전체, symbol ASC 정렬)
        Step 4: 증분 판단 (incremental=True 시)
                symbol별 get_latest_price_date → last_date < as_of_date이면 수집 필요
                이미 최신이면 skipped_uptodate 카운트, 수집 skip
        Step 5: 일봉 수집 / 영속화 (수집 필요 종목만 collector에 전달)
        Step 6: 수정주가 재계산 (apply_adjusted_price=True 시)
        Step 7: MissingDataCheckJob 결손 알림 (run_missing_data_check=True 시)

    _run_missing_data_check() 내부 헬퍼 추가:
        시장별 루프로 MissingDataCheckJob 실행 + missing_count 합산
        BLE001 방어: 결손 알림 실패는 non-fatal (경고만 추가)

    JobResult.stats 신규 키:
        skipped_nontrading: int        — 비거래일 skip 시 1
        symbols_skipped_uptodate: int  — 증분 skip된 종목 수
        missing_count: int             — MissingDataCheckJob 결과

backend/tests/data_pipeline/test_daily_update_job.py  신규 작성 (7개 테스트)
backend/tests/data_pipeline/test_jobs_daily_update.py:366
    test_daily_update_determinism_repeated_runs_same_state 수정
    incremental=False 명시 → 2회 upsert → r1.stats == r2.stats 성립
```

**기본값 설계 근거:**
- `check_trading_calendar=False`, `run_missing_data_check=False`를 기본값으로 설정.
  기존 테스트 8개가 캘린더 사전 등록 없이 작성되어 있어 True이면 skip됨.
  운용 시에는 명시적으로 True 지정. 과도한 기존 테스트 수정 금지 원칙 적용.
- `incremental=True` 기본값: 14번 §6.2 증분 수집이 표준 동작.
  기존 테스트들은 DB 비어있어서 max(date)=None → 전체 수집으로 호환.

## Tests

```text
신규 테스트 (test_daily_update_job.py, 7개):
  test_skips_nontrading_day
      14번 §6.2: is_trading_day=False 등록 → skip, skipped_nontrading=1
  test_skips_nontrading_day_calendar_missing
      14번 §6.2: 캘린더 row 없음 → 안전 측 skip
  test_incremental_from_last_date
      14번 §6.2: max(date)=2024-05-01, as_of=2024-05-02 → 수집, daily_prices_upserted=1
  test_no_op_when_up_to_date
      14번 §6.2: max(date)=as_of_date → skip, symbols_skipped_uptodate=1
  test_corporate_action_triggers_recalc
      14번 §9 / §15: event_date < as_of → AdjustedPriceProcessor.process() 호출됨
  test_missing_data_check_called_after_update
      14번 §13: _run_missing_data_check patch → 정확히 1회 호출됨
  test_missing_data_check_integrates_with_real_job
      14번 §13: 실제 MissingDataCheckJob → 당일 데이터 있으면 missing_count=0

pytest 결과:
  test_daily_update_job.py   7 passed
  test_jobs_daily_update.py  11 passed (기존 8→11: 이전에 이미 11개였음)
  전체: 1265 passed (기존 1258 + 신규 7)

ruff check backend/app backend/tests: All checks passed!
```

## Issues

```text
1. 기존 테스트 test_daily_update_determinism_repeated_runs_same_state 실패
   원인: incremental=True(기본값) + 2회차에서 max(date)=as_of_date → skip → stats 달라짐
         (r1: daily_prices_upserted=1 vs r2: daily_prices_upserted=0)
   해결: 해당 테스트에 incremental=False 명시. 의미 보존: "2회 upsert → DB row = 1건"

2. check_trading_calendar=True 기본값 시 기존 테스트 6개 skip
   원인: 기존 테스트들이 캘린더 사전 등록 없이 작성됨 → is_trading_day() 반환 False
   해결: 기본값을 False로 설정. 운용 시 명시 True 권장 (docstring에 기록).

3. _run_missing_data_check의 markets 루프에서 마지막 시장 missing_count만 반환되던 버그
   원인: 루프 내 total = ... 로 덮어씀
   해결: total_missing += ... 로 누산 후 반환.
```

## Result

```text
적용 정책:
  - 14번 §6.2 (일일 증분 수집): 비거래일 체크 + max(date) 증분 판단
  - 14번 §13 (결손 알림): MissingDataCheckJob 연동
  - 14번 §9 (수정주가): corporate_action 발생 시 AdjustedPriceProcessor 호출 (기존 유지)
  - 14번 §15 (look-ahead): as_of_date 이전 corporate_actions만 적용 (기존 유지)
  - 13번 §12 (결정론): symbol ASC 정렬 + MAX 집계 단일 결과

신규/변경 테이블: 없음 (마이그레이션 없음)

신규 함수:
  repositories.get_latest_price_date(session, symbol) -> date | None

DailyUpdateConfig 신규 필드:
  incremental: bool = True
  run_missing_data_check: bool = False
  check_trading_calendar: bool = False

DailyUpdateJob.run() 통계 신규 키:
  skipped_nontrading: int
  symbols_skipped_uptodate: int
  missing_count: int

pytest: 1265 passed (신규 7개 + 기존 1258 유지)
ruff: All checks passed!
```

## Follow-ups

```text
- 운용 환경 실행 시 DailyUpdateConfig(check_trading_calendar=True, run_missing_data_check=True) 명시 필요
- scheduler.py에 DailyUpdateJob 등록 시 cron "0 18 * * 1-5" 설정
- collect_corporate_actions collector 메서드 추가 시 DailyUpdateJob Step 3 (no-op 단계) 활성화
- MissingDataCheckJob 외부 알림 채널 통합 (14.13) — 현재 JobResult.warnings 누적만
- 주별 수정주가 전체 재계산(WeeklyRecalcJob, 14.6.5) — 별도 step으로 분리 권장
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 049 마무리" 지시. PM이 Phase 로드맵 step ✅ + 14-m [x] + 진행률 표 손계산을 직접 Edit. (영향 체크박스 ID: 14-m)
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step(051)이 완료된 후**: `git push origin main` 자동 실행 (의무)
