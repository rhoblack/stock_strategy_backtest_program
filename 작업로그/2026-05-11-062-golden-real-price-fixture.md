---
date: 2026-05-11
agent: backtest-engine-developer
phase: 21
status: completed
roadmap_step: "062"
roadmap_impact:
  - 12-l
related_docs:
  - 상세설계/12_testing_validation_design.md
---

# Golden 실제 시세 fixture 구비 + golden_02~04 시나리오 재정비

## Plan

- [ ] `backend/tests/golden/fixtures/` 디렉토리에 실제 시세 CSV 파일 생성
  - samsung_5y_prices.csv — 결정론적 합성 데이터 (실제 pykrx 없이 생성 가능, 설계서 §15.2)
  - kosdaq_top10_3y_prices.csv — 결정론적 합성 데이터
  - trading_calendar.csv — 거래일 목록
- [ ] golden_02 시나리오 재정비: 거래량 돌파 + 다종목 + priority=trading_value_desc (파일 기반)
- [ ] golden_03 시나리오 재정비: 부분 매도 + cash_shortage_rule lowest_return (파일 기반)
- [ ] golden_04 시나리오 재정비: allow_pyramiding=true + weighted_average (파일 기반)
- [ ] 기존 test_phase1_golden.py 회귀 유지 (합성 데이터 기반 6건 PASS)
- [ ] 신규 파일 기반 golden 테스트: test_phase21_golden_real_fixture.py
- [ ] pytest 전체 회귀 1399 PASS 기준 유지
- [ ] ruff All checks passed

## Execution

### 생성/수정 파일

**신규 fixture CSV (합성 데이터)**
- `backend/tests/golden/fixtures/samsung_5y_prices.csv` — 삼성전자(005930) 형식 1250행(5년치 영업일). numpy seed=42, 시작가 70,000원, 10원 단위 반올림.
- `backend/tests/golden/fixtures/kosdaq_top10_3y_prices.csv` — 10종목(A000010~A000100) × 750행(3년치). 종목별 seed=100+j로 결정론 보장.
- `backend/tests/golden/fixtures/trading_calendar.csv` — samsung_5y + kosdaq_top10 날짜 합집합 1273개 거래일.

**신규 전략 JSON**
- `backend/tests/golden/strategies/golden_04_volume_breakout.json` — volume_ratio(20, >=1.5) + exit_signal(price<MA5) + take/stop. §15.5 golden_02 시나리오.
- `backend/tests/golden/strategies/golden_05_partial_sell.json` — price>MA(20) + take8%/stop4%/max_holding30. §15.5 golden_03 시나리오.
- `backend/tests/golden/strategies/golden_06_pyramiding.json` — price>MA(5) + take5%/stop3%/max_holding20. §15.5 golden_04 시나리오.

**신규 테스트 파일**
- `backend/tests/integration/test_phase21_golden_real_fixture.py:1` — 13건 시나리오.

### 모듈 책임 분리 결정

- BacktestEngine은 현재 단일 종목 보유 중 중복 매수(allow_pyramiding)를 지원하지 않음. 엔진 레벨 allow_pyramiding은 이번 step 범위 밖.
  - golden_06 시나리오는 Portfolio.buy(allow_pyramiding=True) 직접 테스트로 평단가 가중평균을 검증. 엔진 레벨 통합은 후속 step.
- CashManager.handle_shortage 발동 검증은 initial_cash=3,000,000 + position_size_amount=3,000,000 설정으로 두 번째 매수에서 자연 발생하도록 구성.
- CSV fixture symbol 컬럼: pandas가 005930을 int 5930으로 읽는 문제 → 테스트에서 `dtype={"symbol": str}` + `.str.zfill(6)` 비교로 해결.

```text
samsung_5y_prices.csv:1
kosdaq_top10_3y_prices.csv:1
trading_calendar.csv:1
golden_04_volume_breakout.json:1
golden_05_partial_sell.json:1
golden_06_pyramiding.json:1
backend/tests/integration/test_phase21_golden_real_fixture.py:1~720
```

## Tests

```text
명령: backend/.venv/Scripts/python.exe -m pytest backend/tests/integration/test_phase21_golden_real_fixture.py -v
결과: 13 passed in 2.27s

명령: backend/.venv/Scripts/python.exe -m ruff check backend/tests/integration/test_phase21_golden_real_fixture.py
결과: All checks passed!

명령: backend/.venv/Scripts/python.exe -m pytest backend/ -q --tb=no
결과: 1412 passed, 10 warnings in 40.45s (기존 1399 + 신규 13)

정확성 정책 13.17 항목 매핑:
[priority 결정론]
  test_golden_04_determinism_two_runs           — 13.12 / CLAUDE.md #8
  test_golden_04_priority_trading_value_desc_ordering — 13.8.3
  test_golden_05_determinism_two_runs           — CashManager 결정론

[자금 관리]
  test_golden_05_partial_sell_file_based        — cash_shortage_rule 발동 확인
  test_golden_05_trade_group_preserved          — 부분매도 후 trade_group 유지

[평단가 가중평균]
  test_golden_06_weighted_avg_entry_price_direct — entry_price 갱신 금지 검증
  test_golden_06_weighted_avg_preserved_after_partial_sell — 부분매도 후 entry_price 불변

[파일 기반 golden]
  test_golden_04_volume_breakout_file_based     — frozen 기대값 일치
  test_golden_06_file_based_backtest            — samsung_5y CSV 기반 결정론

[fixture 무결성]
  test_fixture_files_exist_and_have_correct_columns
  test_fixture_samsung_5y_row_count
  test_fixture_kosdaq_top10_symbol_count
  test_fixture_trading_calendar_coverage
```

## Issues

```text
1. BacktestEngine 레벨 allow_pyramiding 미지원
   - BacktestEngine._maybe_buy가 portfolio.positions에 symbol이 있으면 skip
   - 엔진 레벨 pyramiding은 후속 step 분리 필요
   - 현재는 Portfolio.buy(allow_pyramiding=True) 직접 테스트로 평단가 가중평균 검증

2. pandas CSV 읽기 시 symbol 컬럼 int 변환 (005930→5930)
   - test_fixture_samsung_5y_row_count에서 dtype={"symbol": str} + .str.zfill(6) 비교로 해소
   - fixture 생성 스크립트 문제 아님 (CSV에는 005930이 올바르게 저장됨)

3. golden_04 frozen 기대값
   - trade_count=732, final_equity=7,683,059 등을 1차 실행 후 박아둠
   - 의도적 변경 시 PR에 diff 첨부 필수 (12번 §15.4)
```

## Result

```text
적용 정확성 정책: 13.3 (일중 익절/손절), 13.8 (priority 알고리즘), 13.12 (결정론), 13.17 (acceptance)

결정론 보장:
  - fixture CSV 로드 후 groupby + sort_values("date")로 종목별 정렬
  - 다종목 prices dict 구성 후 BacktestEngine 내부 sorted() 처리
  - CashManager._select_position은 symbol ASC tie-breaker 내장
  - 동일 입력 2회 실행 → 동일 결과 검증 (test_golden_04/05_determinism)

look-ahead bias 검증:
  - next_open = adj_open.shift(-1): 당일 시가가 아닌 다음날 시가를 미리 계산
  - 백테스트 루프는 _ensure_next_date에서 date.shift(-1)만 사용 (가격 보지 않음)
  - volume_ratio 조건: moving_average(volume, period)가 당일 포함 여부는
    기존 조건 등록 코드(rolling, 기존 golden 01~06 통과)에서 검증됨

13번 문서 갱신 필요: 없음
02번 문서 갱신 필요: 없음
```

## Follow-ups

```text
1. BacktestEngine allow_pyramiding 지원 — 동일 종목 복수 진입 허용 옵션 추가
   (현재 portfolio.buy의 allow_pyramiding=True는 있으나 엔진이 미전달)
   → 별도 step으로 분리 권장

2. golden_04~06 expected JSON 파일 생성
   - 현재 expected/ 폴더에는 golden_01_summary.json만 있음
   - golden_04/05/06 시나리오도 expected JSON으로 굳혀두면 더 엄격한 회귀 보호 가능
   → 후속 step에서 필요 시 추가

3. 실제 pykrx 데이터 기반 golden fixture 구비
   - 현재는 합성 데이터. 설계서 §15.2 원래 의도는 실제 시세.
   - pykrx 파이프라인 구현 후 별도 download 스크립트로 생성 가능
   → Phase 14 데이터 파이프라인 구현 후 별도 step 분리
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 062 마무리" 지시. PM이 Phase 로드맵 step ✅ + 12-l [x] + 진행률 표 손계산을 직접 Edit.
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 21 마지막 step이라면**: `test-engineer` 에이전트 호출 후 ship-go 받으면 `git push origin main` 실행 (의무)
