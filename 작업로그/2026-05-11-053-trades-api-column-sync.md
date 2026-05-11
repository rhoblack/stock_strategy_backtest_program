---
date: 2026-05-11
agent: backend-api-developer
phase: 17
status: completed
roadmap_step: "053"
roadmap_impact:
  - 10-t
related_docs:
  - 상세설계/10_api_design.md
  - 상세설계/07_database_design.md
---

# trades API 응답에 신규 컬럼 5개 추가 (10-t)

## Plan

- [x] 기존 코드 파악 (routes_backtests.py, schemas/backtest.py, services/csv_exporter.py, 10_api_design.md)
- [x] 10_api_design.md §trades 응답 스펙에 5개 필드 추가 (문서 먼저)
- [x] TradeGroupOut 스키마에 entry_amount / exit_quantity / exit_amount / holding_days / signal_date 추가
- [x] list_trades 라우트 매핑 로직 갱신 (csv_exporter 계산 로직 재사용)
- [x] 테스트 4개 추가 (새 컬럼 존재 / entry_amount 계산 / open 포지션 None / signal_date 포함)
- [x] ruff check + pytest 통과 확인

## Execution

```text
상세설계/10_api_design.md:286-308           trades 응답 예시 JSON에 5개 필드 추가
backend/app/schemas/backtest.py:182-196     TradeGroupOut에 entry_amount/exit_quantity/exit_amount/holding_days/signal_date 추가
backend/app/api/routes_backtests.py:296-335 list_trades 매핑에 5개 필드 계산 로직 추가
backend/tests/api/test_trades_pagination.py (하단 테스트 4개 추가)
```

## Tests

```text
pytest backend/tests/api/test_trades_pagination.py -v
→ 17 passed (기존 13 + 신규 4)

pytest backend/ -q
→ 1360 passed, 10 warnings (기존 1356 + 신규 4, 회귀 없음)
```

테스트 매핑:
- test_trades_response_has_new_columns → 5개 필드 존재 확인 (10-t)
- test_entry_amount_calculation → entry_amount = entry_price × entry_quantity 정확성
- test_holding_days_null_for_open_position → 미청산 포지션 holding_days=None / 청산 포지션 int
- test_signal_date_present → signal_date 필드 존재 + ISO 형식 검증

## Issues

- 10번 문서 trades 응답 예시에 5개 필드가 누락되어 있어 먼저 추가
- signal_date는 SELL execution에서 취하는 것이 아니라 BUY execution에서 취하도록 csv_exporter 방식과 동일하게 적용 (진입 신호일)

## Result

```text
- 작성/수정 파일:
    상세설계/10_api_design.md:286-330      trades 응답 예시 + 필드 설명 테이블 추가
    backend/app/schemas/backtest.py:182-210  TradeGroupOut 5개 필드 추가
    backend/app/api/routes_backtests.py:296-390  list_trades 매핑 로직 갱신 (신규 5필드 계산)
    backend/tests/api/test_trades_pagination.py  신규 테스트 4개 추가
- 적용 정책 절번호: 10-t (trades 응답 스키마 동기화), 10.9 (user_id scope 유지)
- 신규/변경 라우트: GET /api/backtests/{run_id}/trades (TradeGroupOut 필드 추가, 하위 호환 유지)
- 영속화 스냅샷: 해당 없음 (조회 전용)
- pytest 결과: 1360 passed (기존 1356 + 신규 4, 회귀 없음)
- 10번 문서 갱신: trades 응답 예시 JSON + 필드 설명 테이블 추가
```

## Follow-ups

```text
- entry_amount / holding_days 집계가 프론트 trades 테이블에서 활용 예정
- 10번 문서 trades 응답 예시에 executions 내부 필드도 상세화 필요 시 추가 가능
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 053 마무리" 지시
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step이라면**: `git push origin main` 자동 실행 (의무)
