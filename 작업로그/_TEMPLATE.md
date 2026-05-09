---
date: YYYY-MM-DD
agent: <에이전트명 또는 main>
phase: <Phase 번호>
status: planned   # planned / in_progress / blocked / completed
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# <작업 한줄 제목>

## Plan

작업 시작 전 메인 세션이 작성. 체크리스트 형태.

- [ ] 단계 1
- [ ] 단계 2
- [ ] 단계 3

## Execution

실행 중 또는 완료 후 작성. 어떤 파일을 어떻게 수정했는지, 어떤 결정을 내렸는지.
파일 경로는 `path:line_number` 형식으로 적어 추적 가능하게 함.

```text
backend/app/strategy/conditions/rsi.py:14   RSI 조건 함수 추가
backend/app/strategy/registry.py:42         조건 등록 호출
```

## Tests

```text
pytest backend/tests/strategy/test_rsi.py
→ 4 passed

회귀 검증: 전체 47 passed
```

테스트 실패 시 실패 내용과 대응을 함께 기록.

## Issues

작업 중 발생한 문제와 해결.

```text
- pandas division by zero 경고 → fillna(0) 적용
- 메타데이터 sentence_template 한국어 어순 검토 필요 → 사용자에게 확인 후 확정
```

## Result

```text
- 추가/수정 파일: rsi.py, conditions/__init__.py, test_rsi.py
- 적용된 정책 (정확성 정책 13번 절번호): 13.7 (수정주가 사용)
- look-ahead bias 검증: rolling 14일 이전 데이터만 사용 ✓
- 결정론 검증: 동일 입력 5회 반복 동일 결과 ✓
- pytest 결과: PASS
```

## Follow-ups

다음 세션이 참고할 후속 작업 또는 인사이트.

```text
- rsi_cross 조건 추가 시 본 작업의 패턴 그대로 적용 가능
- look-ahead bias 검증 패턴은 backend/app/strategy/conditions/breakout.py 참고
- (미해결) 한국어 sentence_template 표현 통일안 확정 필요
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step이라면**: `git push origin main` 자동 실행 (의무)
