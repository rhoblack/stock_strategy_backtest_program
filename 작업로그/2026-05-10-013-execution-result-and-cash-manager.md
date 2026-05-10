---
date: 2026-05-10
agent: backtest-engine-developer
phase: 8 (리뷰 011 후속 — Wave C)
status: completed
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/05_portfolio_cash_management_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 리뷰/2026-05-10-011-설계서기반-PM주관-코드리뷰.md
---

# ExecutionResult dataclass + cash_manager의 ExecutionModel 통합 (C2 + H1 + M2 + M4)

리뷰 011 Critical 마지막 1건. 현재 `ExecutionModel`은 fee/tax를 계산하지만 단일 float만 반환 → portfolio·service 어디에서도 fee/tax 분해를 영속화하지 못함. 동시에 `CashManager`가 `price_provider`의 raw price로 `Portfolio.sell_symbol_fifo`를 직접 호출 → 슬리피지·호가·세금이 모두 0이라 강제 매도가 백테스트 수익을 비현실적으로 좋게 만듦.

본 작업에서 두 문제를 한 번에 해소: ExecutionResult dataclass(price/gross/fee/tax/net)를 도입해 ExecutionModel이 분해 결과를 반환하고, CashManager는 ExecutionModel을 주입받아 강제 매도도 동일 경로로 처리.

## Plan

### A) ExecutionResult dataclass 도입 (H1 + M4)
- [ ] `상세설계/13_backtest_accuracy_policy_design.md` §5(호가) §6(세율) §7(수정주가) 정독
- [ ] `상세설계/04_backtest_engine_design.md` ExecutionModel 절 정독
- [ ] `backend/app/backtest/execution.py`에 `ExecutionResult` dataclass:
  - `price: float` (슬리피지+호가 적용 후 체결가)
  - `quantity: int`
  - `gross_amount: float` (price × quantity, 비용 차감 전)
  - `fee: float`
  - `tax: float` (BUY=0, SELL=on_date 세율 적용)
  - `net_amount: float` (BUY는 cost = gross + fee, SELL은 proceeds = gross - fee - tax)
  - `side: str` ("buy" | "sell")
  - `slippage_applied: float` (감사용 — gross_amount과 raw price * qty 차이)
- [ ] `ExecutionModel.calculate_buy_cost(price, quantity)` → `ExecutionResult` 반환
- [ ] `ExecutionModel.calculate_sell_proceeds(price, quantity, on_date)` → `ExecutionResult` 반환
- [ ] 호환성: 기존 호출자가 `.cost`/`.proceeds` 또는 float을 기대하면 `ExecutionResult.net_amount` 사용

### B) Portfolio가 ExecutionResult 수용 (H1 + M2)
- [ ] `backend/app/portfolio/portfolio.py:buy / sell_symbol_fifo` 시그니처 갱신:
  - `cost_override: float | None` → `execution: ExecutionResult | None` (호환 위해 둘 다 지원하거나 일괄 변경 후 호출자 수정)
  - 권장: 일괄 변경 — `execution: ExecutionResult` 필수, BacktestEngine·CashManager 모두 ExecutionResult 전달
- [ ] `Portfolio.trade_logs`에 fee/tax 분해 컬럼 포함 (dict 또는 dataclass) — service의 014 step에서 영속화 매핑
- [ ] `Position.sell_trade_group`에서 realized_profit_rate 계산 시 ExecutionResult.net_amount 기반 (M2 — 슬리피지 반영)

### C) BacktestEngine 어댑팅 (C1 회귀 없게)
- [ ] `backend/app/backtest/engine.py:_maybe_buy / _process_sell_at_price`:
  - ExecutionModel 호출 결과(ExecutionResult)를 portfolio에 그대로 전달
  - 기존 `cost > self.portfolio.cash` 분기는 `execution.net_amount > self.portfolio.cash`로
  - cash_manager 사전 fund 확보 시도 시에도 `est_execution.net_amount` 사용
- [ ] 골든 fixture (Phase 1 9지표 frozen expected)는 fee=0/tax=0 default라 동일 결과 보장 — 테스트로 강제

### D) CashManager가 ExecutionModel 주입 (C2 핵심)
- [ ] `backend/app/portfolio/cash_manager.py`:
  - 생성자에 `execution_model: ExecutionModel` 파라미터 추가 (옵셔널 → 기본값 None은 deprecated 경로로, 점진 변경 또는 일괄 변경)
  - `handle_shortage` 내부의 강제 매도 호출 시:
    - 기존: `portfolio.sell_symbol_fifo(price=raw_price)`
    - 변경: ExecutionModel.apply_slippage_and_tick + calculate_sell_proceeds → ExecutionResult → `portfolio.sell_symbol_fifo(execution=...)` 형태
- [ ] `backend/app/services/backtest_service.py`에서 CashManager 생성 시 ExecutionModel 주입 한 줄 변경
- [ ] cash_events 영속화는 014 step에서 fee/tax/net 분해 매핑 — 본 작업은 ExecutionResult를 cash_events 시그니처에 흘려보내기만

### 공통
- [ ] pytest:
  - **Phase 1 골든 fixture 회귀 필수** — fee/tax=0이라 9지표 frozen expected 동일 유지
  - ExecutionResult dataclass 단위 테스트 (BUY: net=gross+fee, SELL: net=gross-fee-tax 검증)
  - cash_manager가 ExecutionModel을 거치는지 spy/mock 검증 (tax_rate>0 시 강제 매도 net이 raw price*qty보다 작아야 함)
  - Portfolio.trade_logs에 fee/tax 키 존재 + cash_manager 강제 매도 trade도 포함
  - realized_profit_rate가 슬리피지·세금 반영된 net_amount 기반인지 (M2 회귀)
- [ ] 회귀: 전체 397건 + 신규 통과 + ruff
- [ ] 014 step에서 영속화 매핑할 수 있도록 trade_logs 형식·키 이름·타입을 명확히 문서화 (Result 섹션)

### 절대 금지
- BacktestEngine에 신호 생성 / 가격 계산 / 자금 관리 로직 직접 추가
- StrategyEngine, conditions/* 수정 (다른 에이전트 영역)
- DB 모델 / API / schemas / services 수정 (backend-api-engineer 영역) — service에서 CashManager 생성 시 ExecutionModel 주입하는 한 줄만 OK
- conditions/* 수정 (condition-author 영역)
- 시장데이터 작성 (market-data-engineer 영역)
- TradeExecution.fee/tax 영속화 코드 작성 (014 step의 backend-api-engineer 영역)
- DailyEquity.daily_return/cumulative_return 계산 (014 step 영역)
- dict/set 순회 순서 의존, 시드 없는 random — 13.12 결정론

## Execution

작성/수정 파일:

- `backend/app/backtest/execution.py:1-260` — **재작성**. `ExecutionResult` frozen dataclass 추가 (side/raw_price/price/quantity/gross_amount/fee/tax/net_amount/slippage_applied + `to_log_dict()` 메서드). `calculate_buy_cost(price, quantity, *, raw_price=None)` 및 `calculate_sell_proceeds(price, quantity, on_date, *, raw_price=None)` 모두 `ExecutionResult`를 반환하도록 시그니처 변경. fee/tax 분해 노출.
- `backend/app/portfolio/portfolio.py:1-380` — **재작성**. `buy/sell_trade_group/sell_symbol_fifo`에 `execution: ExecutionResult | None` 키워드 인자 추가. `cost_override`/`proceeds_override`는 호환 유지(우선순위: execution > override > raw). `realized_profit/_rate`를 `proceeds - entry_price * sell_qty` 기반으로 변경 — 슬리피지·세금이 ExecutionResult.net_amount 통해 반영됨 (M2 해소). `trade_logs`에 `side/gross_amount/fee/tax/net_amount` 신규 키 추가, 기존 `cost`/`proceeds` 키도 유지(서비스 호환).
- `backend/app/portfolio/cash_manager.py:1-185` — **재작성**. 생성자에 `execution_model: ExecutionModel | None = None`, `market: str = "KOSPI"` 추가. `handle_shortage` 내부에서 ExecutionModel 주입 시 `apply_slippage_and_tick` + `calculate_sell_proceeds` 거쳐 `ExecutionResult`를 sell_symbol_fifo에 전달. `cash_events` dict에 `exec_price/raw_price/gross_amount/fee/tax/net_amount` 신규 키 추가, 기존 `sell_amount`도 net_amount로 업데이트.
- `backend/app/backtest/engine.py:283-368` — `_maybe_buy`와 `_process_sell_at_price`를 ExecutionResult 경로로 갱신. `est_execution.net_amount`로 cash 비교, `portfolio.buy(execution=...)` / `sell_symbol_fifo(execution=...)`로 호출.
- `backend/app/services/backtest_service.py:148-155` — CashManager 생성 시 `execution_model=execution_model, market="KOSPI"` 주입 (한 줄 변경 영역).
- `backend/tests/backtest/test_execution.py` — 기존 float 반환 기대 테스트 3건 갱신, ExecutionResult 단위 테스트 5건 신규 추가.
- `backend/tests/portfolio/test_portfolio.py` — ExecutionResult 통합 테스트 6건 신규 추가 (fee/tax 분해 / realized_profit_rate net 기반 / FIFO 비례 분배 등).
- `backend/tests/portfolio/test_cash_manager.py` — ExecutionModel 주입 시 슬리피지+세금 적용 4건 신규 추가 (spy 검증 포함).

모듈 책임 분리 결정 근거:

- ExecutionResult는 "체결 1건의 비용 분해"라는 단일 책임 → `backtest/execution.py`에 위치. Portfolio가 이를 import해서 trade_logs에 펼쳐 넣음.
- CashManager는 강제 매도 정책(어떤 종목 얼마나)을 결정하지만 체결 비용 계산은 ExecutionModel에 위임 → 의존성 주입으로 일관 처리.
- BacktestEngine은 오케스트레이터 역할 유지 — ExecutionResult를 만들고 Portfolio/CashManager에 흘려보내기만.

## Tests

신규 15건 + 기존 397건 = **총 412건 모두 통과**.

```bash
cd backend && .venv/Scripts/python.exe -m pytest
# ====================== 412 passed, 8 warnings in 13.05s =======================
```

골든 fixture 회귀 (정확성 정책 13.17 + 12번 §15):

```bash
.venv/Scripts/python.exe -m pytest tests/integration/test_phase1_golden.py -v
# 6 passed in 0.56s
# - test_golden_01_ma_cross_take_profit_stop_loss: final_equity=10,188,570 / total_return=1.8857% / mdd=-4.9032% / trade_count=8 / win_rate=37.5% / avg_holding=7.5 / profit_factor=1.2252 모두 일치
# - test_golden_01_specific_first_trade_match: 첫 매수가 9,760원 / 2024-01-12 일치
# - test_golden_01_determinism_two_runs: 두 run dict 비교 일치
# - test_golden_03_full_determinism_10_runs: 10회 반복 일치 (fee/tax/slippage 적용 시나리오 포함)
```

신규 테스트 매핑:

- `test_execution.py::test_execution_result_buy_invariants` — H1/M4 (BUY net=gross+fee, tax=0)
- `test_execution.py::test_execution_result_sell_invariants` — H1/M4 (SELL net=gross-fee-tax)
- `test_execution.py::test_execution_result_to_log_dict_keys` — 014 영속화 인터페이스
- `test_execution.py::test_execution_result_zero_quantity_raises` — 입력 검증
- `test_execution.py::test_execution_result_immutable` — frozen dataclass 보장
- `test_portfolio.py::test_buy_with_execution_result_records_fee_breakdown` — H1
- `test_portfolio.py::test_sell_with_execution_result_records_fee_tax_breakdown` — H1
- `test_portfolio.py::test_realized_profit_uses_net_amount_when_execution_passed` — **M2** (슬리피지 반영)
- `test_portfolio.py::test_buy_with_wrong_side_execution_result_raises` — 안전성
- `test_portfolio.py::test_sell_fifo_with_execution_result_distributes_fee_proportionally` — FIFO 분해
- `test_portfolio.py::test_sell_fifo_execution_quantity_mismatch_raises` — 입력 검증
- `test_cash_manager.py::test_forced_sell_applies_slippage_and_tax_when_execution_model_injected` — **C2 핵심**
- `test_cash_manager.py::test_forced_sell_legacy_fallback_when_no_execution_model` — 호환성
- `test_cash_manager.py::test_forced_sell_records_fee_tax_in_trade_logs` — C2 + Portfolio 연동
- `test_cash_manager.py::test_cash_manager_uses_execution_model_via_spy` — C2 spy 검증

ruff:

```bash
.venv/Scripts/python.exe -m ruff check app/ tests/
# All checks passed!
```

## Issues

- `realized_profit_rate` 계산식 변경 (기존: `(price - entry_price) / entry_price * 100` → 신규: `(proceeds - entry_price * sell_qty) / (entry_price * sell_qty) * 100`). fee=tax=slippage=0인 케이스에서는 결과가 동일하므로 골든 fixture는 영향 없음. 호환 경로(`proceeds_override` 또는 미지정)에서도 기존 정의와 동일 결과를 보존함.
- `trade_logs`에 새 키(`side`, `gross_amount`, `fee`, `tax`, `net_amount`)를 추가하면서 기존 키(`cost`, `proceeds`, `realized_profit`, `is_partial`)는 그대로 유지 — 014 step에서 영속화 매핑 갱신 시 기존 키를 함께 정리할지 결정해야 함.
- `cost_override` 호환 경로에서 `fee = max(0.0, cost_override - gross)`로 추정 — 이는 슬리피지를 포함한 추정이므로 정확하지 않을 수 있음. 신규 호출자는 ExecutionResult를 사용해야 정확한 fee/tax 분해가 보장됨.
- 신규 13/04/05번 정책 변경 없음 — 기존 정책의 코드 누락(C2/H1/M2/M4) 해소만 수행.

## Result

적용한 정확성 정책 절번호:
- **13.5 (호가 단위)** — CashManager가 ExecutionModel.apply_slippage_and_tick를 거치므로 강제 매도도 호가 보정됨
- **13.6 (거래세 시계열)** — CashManager가 ExecutionModel.calculate_sell_proceeds를 호출하면서 on_date를 전달, 세율 시계열이 적용됨
- **13.7 (수정주가)** — 변경 없음 (기존 use_adjusted_price 정책 유지)
- **13.9 (가중평균 평단가)** — 부분매도 시 entry_price 갱신 금지 정책 유지, realized_profit 계산만 net 기반으로 정확화
- **13.12 (결정론)** — sell_symbol_fifo의 entry_date+trade_group_id 정렬 유지, ExecutionResult 비례 분배도 결정론적
- 04번 §7~9 (ExecutionModel 7~9절): calculate_buy_cost / calculate_sell_proceeds가 ExecutionResult로 분해 결과를 노출하면서 04번 본문 코드 예시는 단순 float 반환을 보여줌 → 04번 문서 갱신 권장 (Follow-ups 참조)
- 05번 §7.3 (비용 처리): "ExecutionModel.calculate_sell_proceeds → 순수익" 흐름은 유지되며, 분해 노출 추가됨

결정론 보장 방법:
- ExecutionResult의 비례 분배는 `take/quantity` 부동소수 비율 → FIFO 정렬(entry_date, trade_group_id)에 따라 결정론적
- CashManager의 종목 선택은 기존 `(unrealized_return_pct, symbol)` tie-breaker 유지

look-ahead bias 검증 결과: 본 작업은 비용 분해와 강제 매도 경로만 변경하므로 look-ahead bias와 무관. 기존 peak_price 정책(13.3.5/13.15) 영향 없음.

### 014 step 인계 인터페이스

backend-api-engineer가 014에서 `TradeExecution.fee/tax` 등을 영속화 매핑할 때 사용:

1. **`Portfolio.trade_logs[i]` 키 목록과 타입** (BUY/SELL 공통):
   - `date: datetime.date`
   - `symbol: str`
   - `trade_group_id: int`
   - `execution_type: "BUY" | "SELL" | "PARTIAL_SELL"`
   - `side: "buy" | "sell"` (신규)
   - `price: float | int` (호가 단위 적용 후 — int)
   - `quantity: int`
   - `gross_amount: float` (신규 — price × quantity)
   - `fee: float` (신규 — 0 가능)
   - `tax: float` (신규 — BUY=0, SELL=on_date 시계열 세율 기준)
   - `net_amount: float` (신규 — BUY: gross+fee, SELL: gross-fee-tax)
   - `cost: float` (BUY 호환 키 — = net_amount)
   - `proceeds: float` (SELL 호환 키 — = net_amount)
   - `realized_profit: float` (SELL만 — net_amount - entry_price × sell_qty, **슬리피지/세금 반영됨 M2**)
   - `realized_profit_rate: float` (SELL만 — %, net_amount 기반)
   - `reason: str`
   - `is_partial: bool` (SELL만)
   - cf. `services/backtest_service.py:_persist_trade_groups_and_executions:331-356`은 현재 `gross_amount=ex["price"]*ex["quantity"]`로 직접 계산, `fee=0.0/tax=0.0` 하드코드. 014에서 이 부분을 `ex.get("fee", 0.0)`, `ex.get("tax", 0.0)`, `ex.get("gross_amount", ex["price"]*ex["quantity"])`로 변경하면 됨. `net_amount`는 `ex.get("net_amount", ex.get("cost") or ex.get("proceeds"))`로 가져오기.

2. **`ExecutionResult` 노출 위치**: `app/backtest/execution.py:33-78`에 정의 (frozen dataclass). 014에서 영속화 코드가 `from app.backtest.execution import ExecutionResult`로 import 가능하지만, **trade_logs의 dict로 이미 펼쳐져 있어 import 불필요** — 영속화는 dict 키만 매핑하면 됨.

3. **`cash_events`에 fee/tax/net 포함 여부**: **포함됨**. `cash_manager.py:120-138`에서 다음 키 추가:
   - `exec_price: int` (호가 적용 후 매도가)
   - `raw_price: float` (입력 raw price)
   - `gross_amount: float`
   - `fee: float`
   - `tax: float`
   - `net_amount: float`
   - 기존 `sell_amount`는 net_amount와 동일한 값으로 유지 (호환)
   - cf. `services/backtest_service.py:_persist_cash_events:384-405`는 현재 `sell_amount`만 영속화. 014에서 fee/tax/net을 CashEvent DB 컬럼에 매핑하려면 07번 모델 확장 후 진행 필요. (DB 컬럼 추가는 014 step 영역)

4. **골든 fixture 회귀 결과**: **9지표 모두 frozen expected와 일치**. fee/tax=0 default라 본 변경은 결과 불변. 결정론 10회 반복 일치도 통과.

5. **fee/tax > 0 시나리오 단위 테스트 결과**: 4건 모두 통과
   - `test_forced_sell_applies_slippage_and_tax_when_execution_model_injected`: net_amount < raw_price * qty 검증
   - `test_forced_sell_legacy_fallback_when_no_execution_model`: ExecutionModel 없을 때 fee=tax=0
   - `test_forced_sell_records_fee_tax_in_trade_logs`: trade_logs의 fee>0, tax>0 + `net = gross - fee - tax` 항등성
   - `test_cash_manager_uses_execution_model_via_spy`: spy로 ExecutionModel.calculate_sell_proceeds 호출 검증

## Follow-ups

- **014 step (backend-api-engineer)**:
  - `services/backtest_service.py:_persist_trade_groups_and_executions`에서 `fee=0.0`, `tax=0.0` 하드코드를 `ex.get("fee", 0.0)`, `ex.get("tax", 0.0)`로 변경
  - `gross_amount`도 `ex.get("gross_amount", ex["price"]*ex["quantity"])`로 변경 (호환성 유지하며 분해된 값 우선)
  - `net_amount`는 `ex.get("net_amount", gross)`로
  - `_persist_cash_events`에서 fee/tax/net을 CashEvent에 매핑하려면 07번 DB 모델 확장 필요 (CashEvent에 fee/tax/net_amount 컬럼 추가). 단, 영속화 우선순위가 낮으면 trade_logs 매핑만 우선 처리.
  - DailyEquity.daily_return / cumulative_return 계산은 별도 (M5)
- **04번 문서 갱신 권장**: §7 ExecutionModel 코드 예시가 단일 float 반환으로 돼 있음 — ExecutionResult dataclass로 갱신해 코드와 일치시킬 것. 정책 변경은 아니므로 신중도 낮음.
- **05번 문서 갱신 권장**: §7.3 비용 처리 흐름 예시도 ExecutionResult 분해 노출 반영. CashManager의 ExecutionModel 주입 흐름(C2 해소)도 §9에 추가.
- **호환 cost_override/proceeds_override deprecation**: 향후 모든 호출자가 ExecutionResult로 통일되면 두 인자를 제거할 수 있음. 현재는 단위 테스트(`test_buy_with_cost_override_uses_actual_cost`, `test_sell_symbol_fifo_proceeds_override_distributed_proportionally`)에서 사용 중.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] 014의 blockedBy 해제 확인
- [ ] `git commit`
