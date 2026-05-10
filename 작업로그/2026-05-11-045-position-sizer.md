---
date: 2026-05-11
agent: backtest-engine-developer
phase: 15
status: completed
roadmap_step: "045"
roadmap_impact:
  - 05-i
related_docs:
  - 상세설계/05_portfolio_cash_management_design.md
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 045 — PositionSizer 추가 method (fixed_ratio / equal_weight)

## Plan

- [ ] `backend/app/portfolio/sizer.py` 신규 생성
  - PositionSizer 클래스: calculate_quantity(exec_price, portfolio, config) → int
  - fixed_amount: config.position_size_amount 그대로 (하위 호환)
  - fixed_ratio: portfolio.total_equity() × ratio → 금액 계산 → 수량
  - equal_weight: portfolio.total_equity() / max_positions → 균등 비중 → 수량
- [ ] `backend/app/backtest/config.py` BacktestConfig에 sizing 필드 추가
  - sizing_method: str = "fixed_amount" (하위 호환 default)
  - sizing_ratio: float | None = None (fixed_ratio 방식에 사용)
- [ ] `backend/app/backtest/engine.py` _maybe_buy에서 PositionSizer 사용
  - 기존 int(config.position_size_amount // exec_price) → sizer.calculate_quantity()로 대체
- [ ] `backend/tests/portfolio/test_position_sizer.py` 신규 작성
  - fixed_amount: 기존 동작 유지 (하위 호환)
  - fixed_ratio: total_equity * ratio로 수량 계산
  - equal_weight: total_equity / max_positions로 수량 계산
  - equal_weight: max_positions=None이면 ValueError
- [ ] ruff check → 0 errors / pytest backend/ -q → 기존 PASS 유지

## Execution

### 작성/수정 파일

| 파일 | 변경 종류 | 핵심 내용 |
|------|-----------|-----------|
| `backend/app/portfolio/sizer.py:1-84` | 신규 생성 | PositionSizer 클래스. calculate_quantity(exec_price, portfolio, config) → int. fixed_amount / fixed_ratio / equal_weight 3방식 지원. exec_price ≤ 0 이면 0 반환 (제로 나눗셈 방지). |
| `backend/app/backtest/config.py:82-98` | 수정 (필드 추가) | sizing_method: str = "fixed_amount" (하위 호환 default), sizing_ratio: float \| None = None. __post_init__에 sizing_method 화이트리스트 + fixed_ratio/sizing_ratio 필수/범위 검증 추가. |
| `backend/app/backtest/engine.py:94` | 수정 (import 추가) | from app.portfolio.sizer import PositionSizer |
| `backend/app/backtest/engine.py:145` | 수정 (인스턴스 생성) | self.position_sizer = PositionSizer() — __init__ 내 stateless 인스턴스. |
| `backend/app/backtest/engine.py:1113,1134` | 수정 (수량 계산 교체) | CashManager est_quantity와 본 매수 quantity 모두 int(config.position_size_amount // exec_price) → self.position_sizer.calculate_quantity(exec_price, self.portfolio, self.config)로 교체. |
| `backend/tests/portfolio/test_position_sizer.py` | 신규 생성 | 18개 테스트 케이스. |

### 모듈 책임 분리 결정 근거

- BacktestEngine은 오케스트레이터. "몇 주를 살 것인가" 계산 로직이 엔진에 직접 있으면 04번 §3 위반 → PositionSizer로 분리.
- PositionSizer는 stateless — 입력(exec_price, portfolio, config)에서만 계산하므로 결정론 보장. 인스턴스를 BacktestEngine에 1회 생성해 재사용.
- CashManager 사전 fund 확보 시 사용하던 `int(self.config.position_size_amount // max(est_price, 1))` 도 동일하게 교체 — sizing_method="fixed_ratio"일 때 est_quantity가 고정 금액 기반으로 잘못 계산되는 버그 방지.

## Tests

### 실행 명령

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/portfolio/test_position_sizer.py -v
backend/.venv/Scripts/python.exe -m pytest backend/tests/golden/test_golden_runs.py backend/tests/integration/test_phase1_golden.py -v
backend/.venv/Scripts/python.exe -m pytest backend/ -q
```

### 결과

| 테스트 스위트 | 결과 |
|---|---|
| test_position_sizer.py (18건) | 18 PASSED |
| golden + phase1_golden (11건) | 11 PASSED |
| 전체 backend/ | 1210 PASSED (기존 1192 + 신규 18) |

### 정확성 정책 13.17 매핑

| TC | 항목 | 13.17 매핑 |
|----|------|-----------|
| TC-01~02 | fixed_amount 기본/초과 | 하위 호환 (CLAUDE.md #3) |
| TC-03 | fixed_ratio 기본 | 05-i PositionSizer |
| TC-04 | fixed_ratio+ratio=None → ValueError | 설계서 05번 §8 필수 필드 |
| TC-05 | equal_weight 기본 | 05-i PositionSizer |
| TC-06 | equal_weight+max_positions=None → ValueError | 설계서 05번 §8 필수 필드 |
| TC-07 | 미지원 method → ValueError | 13.12 결정론 (화이트리스트) |
| TC-08,15 | exec_price ≤ 0 → 0 반환 | 방어적 코딩 |
| TC-09 | fixed_ratio+가격 초과 → 0 | 정상 동작 |
| TC-10 | default sizing_method="fixed_amount" | 하위 호환 (CLAUDE.md #3) |
| TC-11,12 | Config 검증 | 설계서 05번 §8 |
| TC-13a~c | BacktestEngine 통합 | 04번 §3 모듈 책임 분리 |
| TC-14 | 결정론 (state-free) | 13.12 결정론 보장 |
| TC-16 | sizing_ratio 경계값 | (0, 1] 범위 정책 |

## Issues

1. **CashManager est_quantity 불일치 잠재 버그**: 기존 코드는 `int(self.config.position_size_amount // max(est_price, 1))`로 항상 fixed_amount 방식으로 추정 수량을 계산했다. sizing_method="fixed_ratio"나 "equal_weight"이면 실제 매수 수량과 추정 수량이 달라져 CashManager가 잘못된 금액을 확보 시도하는 버그였다. 본 step에서 PositionSizer 교체로 함께 수정됨.
2. **equal_weight + max_positions=None**: PositionSizer에서 ValueError 발생. BacktestConfig __post_init__은 equal_weight에 대한 max_positions 필수 검증을 추가하지 않았다 — PositionSizer.calculate_quantity 호출 시점(런타임)에서만 차단된다. 이는 설계 의도대로다(max_positions는 포지션 한도와 sizing 양쪽에서 재사용). 문서에 명시 필요 여부는 후속 판단.

## Result

### 적용한 정확성 정책

- **05번 §8** — PositionSizer 3방식(fixed_amount / fixed_ratio / equal_weight) 구현
- **CLAUDE.md #3 하위 호환** — sizing_method default="fixed_amount", position_size_amount는 그대로 유지. 기존 호출자 변경 없음.
- **04번 §3 모듈 책임 분리** — BacktestEngine은 오케스트레이터. 수량 계산을 PositionSizer에 위임.
- **13.12 결정론** — PositionSizer stateless. sizing_method 화이트리스트 검증으로 미지원 method 사전 차단.

### 결정론 보장 방법

- PositionSizer 인스턴스는 상태(state)를 갖지 않음 → 동일 입력 → 동일 출력 항상 보장.
- dict/set 순회 없음. 분기는 if/elif 체인으로 명확한 순서 보장.
- BacktestEngine은 __init__에서 1회 인스턴스화 (재사용 — 추가 비용 없음).

### look-ahead bias 검증 결과

- PositionSizer는 exec_price / portfolio.total_equity() / config 필드만 사용.
- total_equity()는 "현재 시점"의 cash + 포지션 평가금액 → 미래 데이터 미사용.
- portfolio.update_market_price()는 당일 종가 기준으로 exec_price 계산 전에 갱신되므로 look-ahead bias 없음.
- Phase 1 골든 9지표 frozen expected 모두 변경 없음 (하위 호환 보증).

## Follow-ups

1. **equal_weight + max_positions=None 사전 차단** — BacktestConfig.__post_init__에 equal_weight일 때 max_positions 필수 검증을 추가할지 정책 결정 필요. 현재는 런타임(PositionSizer.calculate_quantity)에서 ValueError 발생. 사전 차단이 더 명확하다면 config.py 수정 후 13번 문서 갱신.
2. **daily_budget 방식** — 설계서 05번 §8에 "daily_budget: 1일 매수 예산" 방식이 명시되어 있으나 config에 이미 daily_buy_budget이 BacktestEngine에서 직접 처리 중. PositionSizer에 통합할지 별도 검토 필요 (현재 구현 범위 밖).
3. **JSON 전략 스키마 연동** — position_sizing 섹션(02번 §5)에서 sizing_method를 JSON으로 전달하는 경로 (BacktestConfig 생성 시 strategy JSON → config 매핑) 추가 필요. 서비스 레이어(services/backtest_service.py) step으로 분리.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] PM 에이전트 호출 → 로드맵.md 갱신 — "step 045 마무리" 지시
- [ ] git commit (단일 커밋)
