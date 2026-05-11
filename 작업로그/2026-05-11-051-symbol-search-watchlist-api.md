---
date: 2026-05-11
agent: backend-api-engineer
phase: 16
status: completed
roadmap_step: "051"
roadmap_impact:
  - 06-k   # 종목 검색 API + 유니버스 preview API
  - 10-s   # 유니버스 preview API (Phase 9 step 019 후)
  - 07-q   # watchlists / watchlist_items DB 스키마
related_docs:
  - 상세설계/06_market_data_universe_design.md
  - 상세설계/07_database_design.md
  - 상세설계/10_api_design.md
---

# step 051 — 종목 검색 API + watchlists DB + CRUD API

## Plan

작업 완료 시 갱신할 로드맵 체크박스: 06-k, 10-s, 07-q

- [ ] `backend/app/api/routes/symbols.py` — 종목 검색 API (`GET /api/symbols?q=삼성&market=KOSPI`)
- [ ] `backend/app/db/models.py` — watchlists / watchlist_items 테이블 추가
- [ ] alembic 마이그레이션 (watchlists + watchlist_items)
- [ ] `backend/app/api/routes/watchlists.py` — CRUD API (GET / POST / PUT / DELETE)
- [ ] `backend/tests/api/test_symbols.py` — 종목 검색 API 단위/통합 테스트
- [ ] `backend/tests/api/test_watchlists.py` — watchlist CRUD 테스트
- [ ] ruff 검증 (All checks passed)
- [ ] pytest 전체 회귀 (기존 1279 PASS 유지 + 신규 추가)

## Execution

```text
backend/app/models/watchlist.py:1         신규 — Watchlist, WatchlistItem ORM 모델
backend/app/models/__init__.py:15,43      Watchlist, WatchlistItem import + __all__ 추가
backend/app/core/exceptions.py:207-223    WatchlistNotFoundError, WatchlistItemAlreadyExistsError 추가
backend/app/api/errors.py:72-73           WATCHLIST_NOT_FOUND(404), WATCHLIST_ITEM_ALREADY_EXISTS(409) 추가
backend/app/schemas/watchlist.py:1        신규 — WatchlistCreate, WatchlistOut, WatchlistDetailOut, WatchlistItemOut, SymbolAddRequest
backend/app/api/routes_market.py:48-97   GET /api/symbols 엔드포인트 추가 (기존 /search 앞에 삽입)
backend/app/api/routes_watchlists.py:1    신규 — POST/GET/DELETE watchlists CRUD 6개 엔드포인트
backend/app/main.py:19,59                 watchlists_router import + include_router
backend/alembic/versions/33e7279ce17c_add_watchlists_and_watchlist_items.py:1   마이그레이션
backend/tests/api/test_symbols.py:1       신규 — 18개 테스트
backend/tests/api/test_watchlists.py:1    신규 — 29개 테스트
backend/tests/api/test_error_catalog.py:55,85,151,189   watchlist 에러 코드 카탈로그 항목 추가

상세설계/10_api_design.md:5-s, 5-t, 7.1   신규 절 및 에러 코드 추가
```

적용 정책 절번호:
- 10.9 (user_id scope): watchlist 모든 엔드포인트에 get_current_user_id 적용
- 10.7 / 10.7.1 (에러 envelope): WatchlistNotFoundError → 404, WatchlistItemAlreadyExistsError → 409
- 10.8 (X-Request-ID): 미들웨어 공통 적용 확인
- 07번 §13 (watchlists 스키마): Watchlist + WatchlistItem 1:N 모델

신규 에러 코드 (10번 §7.1 갱신):
- WATCHLIST_NOT_FOUND (404)
- WATCHLIST_ITEM_ALREADY_EXISTS (409)

## Tests

```text
pytest backend/tests/api/test_symbols.py -v
→ 18 passed

pytest backend/tests/api/test_watchlists.py -v
→ 29 passed

pytest backend/tests/api/test_error_catalog.py -v
→ 62 passed (watchlist 에러코드 2개 신규 포함)

pytest backend/ -q (전체 회귀)
→ 1330 passed (기존 1279 + 신규 51)
회귀 없음.

ruff check backend/app backend/tests
→ All checks passed!
```

테스트 매핑:
- scope 위반 (5개): test_list_watchlists_scope_excludes_other_user, test_get_watchlist_other_user_returns_404,
  test_add_symbol_other_user_watchlist_returns_404, test_remove_symbol_other_user_watchlist_returns_404,
  test_delete_watchlist_other_user_returns_404
- envelope 구조: test_error_response_envelope_structure, test_error_response_has_x_request_id
- 중복 409: test_add_symbol_duplicate_returns_409
- cascade 삭제: test_delete_watchlist_cascade_items
- idempotent 제거: test_remove_symbol_not_in_list_returns_204

## Issues

1. Alembic autogenerate 시 기존 테이블의 FK/NOT NULL 변경도 감지됨.
   → 마이그레이션 파일을 수작업으로 watchlists/watchlist_items 생성만 남기고 정리.
   기존 dev.db가 head와 다른 상태였으므로 `upgrade head` 후 autogenerate.

2. GET /api/symbols 라우트를 prefix="/api/symbols" 라우터에서 ""로 등록할 때
   기존 /search 보다 앞에 위치시킴 (FastAPI 라우트 매칭 순서 고려).

3. test_error_catalog.py의 `_CATALOG_CODES` 집합이 하드코딩되어 있어,
   새 에러 코드 추가 시 반드시 해당 테스트도 갱신해야 함.
   → 이번 작업에서 갱신 완료.

## Result

신규 라우트:
- GET  /api/symbols (limit=1~100, q, market 필터)
- POST /api/watchlists
- GET  /api/watchlists
- GET  /api/watchlists/{id}
- POST /api/watchlists/{id}/symbols
- DELETE /api/watchlists/{id}/symbols/{symbol}
- DELETE /api/watchlists/{id}

신규 스키마:
- WatchlistCreate, WatchlistOut, WatchlistDetailOut, WatchlistItemOut, SymbolAddRequest

신규 에러 코드 (10번 §7.1 + errors.py + exceptions.py 모두 갱신):
- WATCHLIST_NOT_FOUND (404)
- WATCHLIST_ITEM_ALREADY_EXISTS (409)

Alembic 마이그레이션:
- 33e7279ce17c: watchlists + watchlist_items 테이블 생성

user_id scope 매트릭스:
| 엔드포인트                          | scope 적용 |
|-------------------------------------|-----------|
| GET /api/symbols                    | 없음 (공개) |
| POST /api/watchlists                | user_id=1 |
| GET /api/watchlists                 | user_id=1 필터 |
| GET /api/watchlists/{id}            | owner 검증 404 |
| POST /api/watchlists/{id}/symbols   | owner 검증 404 |
| DELETE /api/watchlists/{id}/symbols | owner 검증 404 |
| DELETE /api/watchlists/{id}         | owner 검증 404 |

pytest 결과: 1330 passed (기존 1279 + 신규 51)

## Follow-ups

- 멀티유저 전환 시 get_current_user_id를 JWT 토큰 기반으로 교체하면
  routes_watchlists.py에서는 코드 변경 불필요 (Depends 교체만).
- PATCH /api/watchlists/{id} (이름/설명 수정) 필요 시 WatchlistUpdate 스키마가
  준비되어 있으므로 라우트만 추가하면 됨.
- GET /api/symbols?q= 와 GET /api/symbols/search?q=가 중복 존재.
  향후 /search 제거 또는 정리 가능.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 051 마무리" 지시 (영향 체크박스: 06-k, 10-s, 07-q)
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step이라면**: `git push origin main` 자동 실행
