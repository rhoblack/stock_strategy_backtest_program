---
date: 2026-05-11
agent: frontend-developer
phase: 22
status: completed
roadmap_step: "067"
roadmap_impact:
  - 01-l
related_docs:
  - 상세설계/01_strategy_builder_gui_design.md
---

# step 067: BlockPalette 검색/즐겨찾기 (01-l)

## Plan

- [ ] BlockPalette.tsx에 검색 입력란 추가 (조건 이름/설명 필터링)
- [ ] 즐겨찾기 토글 기능 추가 (localStorage 영속화)
- [ ] 즐겨찾기 필터 UI 추가 (전체/즐겨찾기만 탭 또는 토글)
- [ ] BlockPalette.test.tsx에 검색/즐겨찾기 테스트 추가 (최소 5건)
- [ ] vitest 전체 회귀 통과 확인

## Execution

```text
frontend/src/features/strategy-builder/components/BlockPalette.tsx
  - useState(searchQuery, showFavoritesOnly, favorites) 추가
  - loadFavorites() / saveFavorites() — localStorage 영속화 헬퍼
  - toggleFavorite() — useCallback + Set 불변 갱신
  - 검색 입력란 <input type="search" aria-label="조건 검색">
  - 필터 탭 <div role="tablist" aria-label="블록 팔레트 필터"> (전체 / 즐겨찾기만)
  - 즐겨찾기 토글 버튼 (별 아이콘, aria-label 충족)
  - 결과 없음 분기 메시지 (검색 결과 없음 / 즐겨찾기한 조건 없음)
  - aria-label="필터" → "블록 팔레트 필터" 변경 (StrategyBuilderPage 기존 테스트 충돌 방지)

frontend/src/features/strategy-builder/components/BlockPalette.test.tsx
  - 기존 3건 유지 (beforeEach에 localStorage.clear() 추가)
  - 신규 9건: 검색 입력란 렌더, 이름 필터, description 필터, 결과 없음,
    즐겨찾기 버튼 렌더, 토글 클릭, 즐겨찾기 탭, 빈 즐겨찾기 안내, localStorage 영속화
```

## Tests

```text
vitest run (frontend)
  BlockPalette.test.tsx: 12/12 PASS (기존 3 + 신규 9)
  전체: 258 passed / 0 failed (32 test files)
```

## Issues

```text
- aria-label="필터" 충돌: BlockPalette tablist와 StrategyCanvas의 필터 섹션이
  getByLabelText("필터")에서 복수 매칭 → "블록 팔레트 필터"로 변경하여 해결
```

## Result

```text
- 추가/수정 파일:
  frontend/src/features/strategy-builder/components/BlockPalette.tsx
  frontend/src/features/strategy-builder/components/BlockPalette.test.tsx
- 01-l 체크박스 해소 (BlockPalette 검색/즐겨찾기)
- 검색: 이름+description 필터링 (대소문자 무관)
- 즐겨찾기: localStorage 영속화, 별 아이콘 토글, 즐겨찾기 탭 필터
- vitest 258 PASS / 0 FAIL
```

## Follow-ups

```text
- 즐겨찾기 아이콘을 SVG로 교체 시 더 나은 UX 제공 가능 (현재 Unicode 별표 사용)
- 검색어 하이라이팅 기능 추가 가능 (향후 UX 개선)
```
