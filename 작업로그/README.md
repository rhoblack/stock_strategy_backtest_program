# 작업 로그 인덱스

이 폴더는 프로젝트 진행 중 수행한 모든 코딩 작업의 로그를 보관합니다.

**모든 새 세션은 이 파일을 가장 먼저 읽고 시작합니다.**

---

## 사용 규칙

### 새 작업 시작 시
1. 이 README.md를 읽어 현재 Phase 상태와 최근 작업을 파악
2. `_TEMPLATE.md`를 복사해 새 로그 파일 생성
   - 명명 규칙: `YYYY-MM-DD-NNN-짧은-설명.md` (예: `2026-05-09-001-rsi-condition.md`)
   - NNN은 그 날의 작업 일련번호 (001부터)
3. Plan 섹션을 먼저 작성 (체크리스트 형태)
4. 실행 (직접 또는 에이전트 호출)
5. 완료 시 본 README.md의 "최근 작업"과 "현재 Phase 상태" 갱신
6. **각 step 완료 시**: 단일 `git commit`
7. **Phase 완료 시 (의무)**: `git push origin main` 자동 실행 — push 누락 시 다음 세션이 GitHub에서 동기화 못 함

### 에이전트 호출 시
메인 세션이 에이전트를 호출할 때 작업 로그 파일 경로를 전달:
> "작업로그/2026-05-09-001-rsi-condition.md를 참고해서 작업하고, Execution/Tests/Result 섹션을 채워줘"

에이전트는 `status` 변경과 본 README.md 갱신은 하지 않습니다 (메인 세션 담당).

### 다음 세션이 참고할 정보
- 어떤 작업이 끝났는지 (completed)
- 어떤 작업이 진행 중인지 (in_progress)
- 어떤 작업이 블록되었는지 (blocked) — 이유 함께 기록
- 다음에 할 작업의 후보 (Follow-ups에 적힌 항목들)

---

## 현재 Phase 상태

설계서 (`stock_strategy_lab_program_introduction.md` 12절) 기준 MVP Phase 진행 현황.

| Phase | 내용 | 상태 |
|---:|---|---|
| 0 | 설계 문서 작성 + 리뷰 반영 | ✅ 완료 |
| 0 | CLAUDE.md + 코딩 에이전트 + 작업 로그 시스템 | ✅ 완료 |
| 1 | 백엔드 핵심 엔진 (조건 5개 + StrategyEngine + 단일종목 백테스트 + Metrics) | ✅ 완료 (9/9) |
| 2 | SQLite 저장 (users/strategies/backtest_runs/trade_groups/...) | ✅ 완료 (6/6) |
| 3 | GUI 전략 빌더 | ✅ 완료 (7/7) |
| 4 | 백테스트 실행/결과 화면 | ✅ 완료 (2/2) |
| 5 | 종목 봉차트 + 매수/매도 마커 | ✅ 완료 |
| 6 | Portfolio + CashManager (예수금 부족 시 일부 매도) | ✅ 완료 |
| 7 | CSV/ZIP Export | ✅ 완료 |
| 8 | 리뷰 011 Critical 후속 (Wave A·B·C = 010~014 완료, Critical 5/5 해소) | ✅ 완료 (5 step) |
| 9 | 정확성 잔존(015·017) + 시장데이터 1단계(016·018·019) — test-engineer ship-go | ✅ 완료 (5 step) |
| 10 | BacktestEngine 복수 종목 + priority + 한도 + event_log + 강제매도 (외부 CR-003) — test-engineer ship-go | ✅ 완료 (4 step) |
| 11 | 데이터 파이프라인 본체 (collectors / processors / jobs / scheduler / 결손 알림) — test-engineer ship-go | ✅ 완료 (5 step) |
| 12 | UI 확장 (02 schema GUI 정합화 + 차트 탭 + 종목 선택 + TanStack Table) | 🔄 다음 |

**현재 작업 중**: 없음. **데모 MVP 완료 / 상세설계 MVP 미완료** ⚠️ (리뷰 011 **Critical 5/5 모두 해소** + 외부 4.7 일괄 — 신뢰성 기반 정합화 완료. 다음 단계는 시장데이터/복수종목 트랙)

> 위 Phase 1~7 표는 **자체 정의한 step 기준** 완료 표시입니다. **상세설계서 14개 문서 기준으로는 데모 수준**이며 핵심 미구현 다수가 있습니다.
> 상세 비교는 [`리뷰/2026-05-10-010-외부코드리뷰.md`](../리뷰/2026-05-10-010-외부코드리뷰.md) 참조 (외부 리뷰 + 메인 세션 검증 완료).
>
> 주요 미구현/버그 (2026-05-10 Wave A·B·C 후 갱신):
> - 백테스트가 실데이터 아닌 합성 데이터(synthetic_data)로만 동작 — 시장데이터 계층(`backend/app/market_data/`) 비어 있음
> - BacktestEngine은 단일 종목 한정 (복수 종목/priority/유니버스 미구현)
> - DB에 symbols/daily_prices/trading_calendar 등 시장데이터 테이블 없음
> - next_open 체결인데 체결일을 신호일(today)로 기록 (holding_days/CSV 1일 시프트)
> - ~~전략 JSON validator 부재~~ → ✅ **C4 해소** (010-011, 55건 신규 테스트)
> - ~~API user_id scope 누락~~ → ✅ **C3 해소** (010-011, 16개 라우트 매트릭스 점검)
> - ~~error envelope 불일치 / X-Request-ID 부재~~ → ✅ **H7 해소** (010-011)
> - ~~exit_position 라우팅이 ConditionRegistry 우회~~ → ✅ **C1 해소** (010-012, 4종 모두 evaluate_position 경유)
> - ~~peak_price를 adj_close로 즉시 갱신 (look-ahead)~~ → ✅ **C5 해소** (010-012, prev-high + 평가 후 갱신)
> - ~~CashManager가 ExecutionModel 우회 (강제 매도 슬리피지/세금 0)~~ → ✅ **C2 해소** (010-013, ExecutionResult dataclass 도입)
> - ~~fee/tax가 항상 0.0으로 영속화 (gross=net 의미 어긋남)~~ → ✅ **H1·M2·M4 + 외부 4.7 일괄 해소** (010-014, TradeExecution 분해 매핑)
> - ~~DailyEquity.daily_return/cumulative_return 미계산 영속화~~ → ✅ **M5 해소** (010-014, 시퀀스 계산 + drawdown과 일관 % 단위)
> - 등록 조건 5 → **8개** (stop_loss / max_holding_days / trailing_stop 추가, 010-010)

**환경 셋업 완료**: `backend/.venv/` 활성화 후 `./.venv/Scripts/python.exe -m pytest` 로 검증 가능. **418/418 통과** (baseline 300 → 010-010 +35 → 010-011 +55 → 010-012 +7 → 010-013 +15 → 010-014 +6) + ruff All checks passed. Node v24 + npm 11 사용 가능.

**다음 작업 권고 순서**: 단일 출처는 [`로드맵.md`](../로드맵.md)의 "Phase 로드맵" 섹션.
현재 진행 중: Phase 9 (015·016 완료, 다음은 step 017 — signal_date 영속화). Phase 9~13 전체 step 목록과 각 step이 영향 줄 체크박스는 로드맵 참조.

UI 탭/차트 확장은 위 6개 이후 (데이터 계층 흔들리면 UI 갈아엎어야 함).

**MVP end-to-end 백엔드 동작**: 전략 생성 → (합성 데이터) 백테스트 실행 → 영속화 → 요약 조회까지 데모 동작. Alembic 마이그레이션으로 운영 환경 준비.

**에이전트 시스템 메모**: `.claude/agents/` 정의가 현재 세션에 hot reload되지 않음. 새 세션 시작 시 정상 인식 여부 확인 필요. 안 되면 메인 세션이 에이전트의 system prompt를 따라 직접 작업 가능.

---

## 최근 작업 (최신 순)

| 날짜 | 파일 | Phase | 에이전트 | 상태 | 한줄 요약 |
|---|---|---|---|---|---|
| 2026-05-10 | [030-strategy-header-and-templates](./2026-05-10-030-strategy-header-and-templates.md) | 12 | frontend-developer | ✅ | **01-j + 01-k 해소**: StrategyHeader(복사/JSON 보기/백테스트 실행) + 4 템플릿(빈/골든크로스/RSI/모멘텀) + APPLY_TEMPLATE reducer + useBuilderMode(초보/전문 토글 + localStorage) + 신규 vitest 34건 (전체 111 PASS) — **01 카테고리 100% 완료** ✅, **70% 돌파** 🎉 |
| 2026-05-10 | [029-strategy-schema-gui](./2026-05-10-029-strategy-schema-gui.md) | 12 | frontend-developer | ✅ | **01-h·i + 02-f·g·h·i·j·k 해소 (8 항목) / Phase 12 첫 step**: StrategyDraft 6섹션 + StrategyConfigPanel 6 폼(탭) + serializeDraft 6섹션 + GROUP 1단계 + tax_rate 시계열 GUI + 신규 vitest 34건 (전체 77 PASS) — **02 schema 100% 완료** ✅ — 69% |
| 2026-05-10 | [phase11-test-engineer-verification](./2026-05-10-phase11-test-engineer-verification.md) | 11 | test-engineer | ✅ | **Phase 11 완료 검증 🟢 ship-go**: 통합 회귀 825 PASS (+209) / 13.x·14.x 9개 정책 모두 통과 / 골든 9지표 유지 / e2e 5건 신규 |
| 2026-05-10 | [028-jobs-scheduler-and-alerts](./2026-05-10-028-jobs-scheduler-and-alerts.md) | 11 | market-data-engineer | ✅ | **14-j·k 해소 / Phase 11 마지막 step**: 5 jobs(DailyUpdate/HistoricalBackfill/CorporateActionApply/MarketIndex/UniverseSnapshot) + Scheduler busy-set 락 + LockError + MissingDataCheckJob(forward-fill 금지) + 50건 신규 / 820 PASS — **65% (test-engineer 검증 대기)** |
| 2026-05-10 | [027-market-indices-and-universe-history](./2026-05-10-027-market-indices-and-universe-history.md) | 11 | market-data-engineer | ✅ | **06-i + 07-o·p + 14-i 해소**: market_indices(KOSPI/KOSDAQ/KOSPI200/KOSDAQ150/KRX100) + universe_history(config_json/symbols_json/run_id) + alembic 59cda024ecf8 + 33건 신규 / 770 PASS / **0 fail** (016 head 가드 정리) — 64% |
| 2026-05-10 | [026-corporate-actions-and-adjusted-price](./2026-05-10-026-corporate-actions-and-adjusted-price.md) | 11 | market-data-engineer | ✅ | **06-h + 07-n + 14-h + 13-r 해소**: corporate_actions 모델(8 event_type) + AdjustedPriceProcessor(시간 역순 적용, close 보존) + alembic c7f2a16d8b53 + 43건 신규 / 736 PASS — 62% |
| 2026-05-10 | [025-pykrx-collector](./2026-05-10-025-pykrx-collector.md) | 11 | market-data-engineer | ✅ | **14-e·f·g 해소**: PykrxCollector(_fetch_* 격리, lazy import) + retry(1s→5s→30s, jitter 없음) + validators(HARD/SOFT 매핑) + RetryableCollectorError 다중상속 + 51건 신규 / 693 PASS — **60% 돌파** 🎉 |
| 2026-05-10 | [024-data-pipeline-skeleton](./2026-05-10-024-data-pipeline-skeleton.md) | 11 | market-data-engineer | ✅ | **14-b·c·d 해소 / Phase 11 첫 step**: data_pipeline 패키지 구조 + BaseCollector(3-메서드)/BaseProcessor(단일 process)/BaseJob/Scheduler 레지스트리 + 예외 계층 7종 + 26건 신규 / 642 PASS — 59% |
| 2026-05-10 | [phase10-test-engineer-verification](./2026-05-10-phase10-test-engineer-verification.md) | 10 | test-engineer | ✅ | **Phase 10 완료 검증 🟢 ship-go**: 통합 회귀 616 PASS / 13.17 모든 항목 통과 / 골든 9지표 유지 / e2e 시나리오 4건 신규 |
| 2026-05-10 | [023-event-log-and-forced-sell](./2026-05-10-023-event-log-and-forced-sell.md) | 10 | backtest-engine-developer | ✅ | **04-n·o + 13-p·q 해소 / Phase 10 마지막 step**: event_log 8종 사유 + 상한가/하한가 차단(default 보수) + 상장폐지 강제 매도(delisting_dates) + 25건 신규 / 612 PASS — **58% (test-engineer 검증 대기)** |
| 2026-05-10 | [022-position-limits](./2026-05-10-022-position-limits.md) | 10 | backtest-engine-developer | ✅ | **04-l + 04-m 해소**: _apply_position_limits + max_positions/max_daily_entries(사전) + daily_buy_budget(매수 루프 cumulative 동적) + 22건 신규 / 587 PASS / 골든 frozen — 56% |
| 2026-05-10 | [021-priority-and-random-seed](./2026-05-10-021-priority-and-random-seed.md) | 10 | backtest-engine-developer | ✅ | **04-k + 13-n + 13-o 해소 (M7 잔존 해소)**: priority 4종(none/trading_value_desc/market_cap_desc/random) + symbol_asc tie-breaker + random_seed 실사용 + None+random ValueError + 14건 신규 / 565 PASS / 골든 frozen — 55% |
| 2026-05-10 | [020-backtest-engine-multi-symbol](./2026-05-10-020-backtest-engine-multi-symbol.md) | 10 | backtest-engine-developer | ✅ | **04-i·j 해소 / Phase 10 첫 step**: BacktestEngine dict[symbol, df] 입력 + 단일 df 자동 wrap 호환 + held_at_open_set 가드(015 의미 보존) + 15건 신규 / 551 PASS / 골든 9지표 frozen 유지 — 53% |
| 2026-05-10 | [phase9-test-engineer-verification](./2026-05-10-phase9-test-engineer-verification.md) | 9 | test-engineer | ✅ | **Phase 9 완료 검증 🟢 ship-go**: 통합 회귀 536 PASS / 13.17 acceptance 모두 통과 / 골든 9지표 유지 / e2e 시나리오 5건 신규 |
| 2026-05-10 | [019-universe-selector](./2026-05-10-019-universe-selector.md) | 9 | market-data-engineer | ✅ | **06-f·g + 13-m 해소 / Phase 9 마지막 step**: UniverseSelector + 06번 §8 공통 필터(8개) + 13.15 look-ahead 차단(시가총액 ≤ as_of_date / 거래대금 평균 < as_of_date) + selection_method 3종 + 35건 신규 / 531 collected — **52% (test-engineer 검증 대기)** |
| 2026-05-10 | [018-local-csv-provider-and-price-loader](./2026-05-10-018-local-csv-provider-and-price-loader.md) | 9 | market-data-engineer | ✅ | **06-c·d·e 해소**: BaseProvider(ABC) + LocalCsvProvider(CSV ingest) + PriceLoader(BacktestEngine 호환 next_* DataFrame) + 31건 신규 / 497 collected — **50% 돌파** 🎉 |
| 2026-05-10 | [017-signal-date-persistence](./2026-05-10-017-signal-date-persistence.md) | 9 | backend-api-engineer | ✅ | **07-m 해소**: TradeExecution.signal_date 컬럼 + alembic + service 매핑 + env.py 부수 픽스(silent-skip 정상화) + 466 collected/465 passed (1 fail은 016 자기-소유 head 가드) |
| 2026-05-10 | [016-market-data-models-skeleton](./2026-05-10-016-market-data-models-skeleton.md) | 9 | market-data-engineer | ✅ | **시장데이터 트랙 1단계**: symbols/daily_prices/trading_calendar 모델 + alembic + repositories CRUD 9종 + 35건 신규 (LocalCsvProvider/PriceLoader/UniverseSelector는 016b 후속) |
| 2026-05-10 | [015-execution-date-separation](./2026-05-10-015-execution-date-separation.md) | 9 | backtest-engine-developer | ✅ | **체결일 정합성 (외부 4.13)**: signal_date vs execution_date 분리 + next_date NaN skip + 골든 갱신 (avg_holding_days 7.5→6.5, 첫 거래 +1일) + 10건 신규 |
| 2026-05-10 | [014-execution-persistence-and-daily-return](./2026-05-10-014-execution-persistence-and-daily-return.md) | 8 | backend-api-engineer | ✅ | **Phase 8 완료** ✅ (Critical 5/5): TradeExecution fee/tax + DailyEquity daily/cumulative + cash_events 분해 영속화 + alembic + 418 PASS |
| 2026-05-10 | [013-execution-result-and-cash-manager](./2026-05-10-013-execution-result-and-cash-manager.md) | 8 | backtest-engine-developer | ✅ | **C2+H1+M2+M4 해소**: ExecutionResult dataclass + cash_manager가 ExecutionModel 주입 + 골든 회귀 + 412 PASS |
| 2026-05-10 | [012-exit-routing-and-peak-price](./2026-05-10-012-exit-routing-and-peak-price.md) | 8 | backtest-engine-developer | ✅ | **C1+C5 해소**: exit_position 4종 Registry 라우팅 + peak_price prev-high (13.3.5) + 골든 회귀 + 397 PASS |
| 2026-05-10 | [011-validator-userscope-envelope](./2026-05-10-011-validator-userscope-envelope.md) | 8 | backend-api-engineer | ✅ | **C4+C3+H7 해소**: strategy_json validator + user_id scope 16개 라우트 + 표준 envelope + X-Request-ID + 55건 신규 |
| 2026-05-10 | [010-exit-position-conditions-registry](./2026-05-10-010-exit-position-conditions-registry.md) | 8 | condition-author | ✅ | **C1 선결**: stop_loss / max_holding_days / trailing_stop Registry 등록 + 35건 신규 (8개 조건 보유) |
| 2026-05-10 | [009-csv-export](./2026-05-10-009-csv-export.md) | 7 | main | ✅ | **Phase 7 완료 + MVP 완성** ✅: CSV/ZIP Export + 다운로드 버튼 + 8건 |
| 2026-05-10 | [008-cash-manager](./2026-05-10-008-cash-manager.md) | 6 | main | ✅ | **Phase 6 완료**: CashManager + cash_events 영속화 + 7건 |
| 2026-05-10 | [007-chart-data](./2026-05-10-007-chart-data.md) | 5 | main | ✅ | **Phase 5 완료**: chart-data API + CandleTradeChart + EquityCurveChart |
| 2026-05-10 | [006-backtest-run-page](./2026-05-10-006-backtest-run-page.md) | 4 | main | ✅ | **Phase 4 완료**: BacktestRunPage + ResultPage + 폴링 + 4건 |
| 2026-05-10 | [005-backtest-api](./2026-05-10-005-backtest-api.md) | 4 | main | ✅ | Backtest API + 합성 데이터 dev 모드 + 6건 |
| 2026-05-10 | [004-strategy-save](./2026-05-10-004-strategy-save.md) | 3 | main | ✅ | **Phase 3 완료**: Strategy CRUD API + serialize + Save+redirect + 9건 |
| 2026-05-10 | [003-preview-validation](./2026-05-10-003-preview-validation.md) | 3 | main | ✅ | StrategyPreviewPanel + StrategyValidationPanel + 10건 |
| 2026-05-10 | [002-condition-editor-panel](./2026-05-10-002-condition-editor-panel.md) | 3 | main | ✅ | ConditionEditorPanel parameters 자동 폼 + 즉시 반영 + 4건 |
| 2026-05-10 | [001-strategy-draft-state](./2026-05-10-001-strategy-draft-state.md) | 3 | main | ✅ | StrategyDraft reducer + Canvas 카드 + 추가/삭제 인터랙션 + 19건 |
| 2026-05-09 | [018-strategy-builder-page-skeleton](./2026-05-09-018-strategy-builder-page-skeleton.md) | 3 | main | ✅ | StrategyBuilderPage 3열 레이아웃 + Router + BlockPalette(실제 데이터) + 6건 |
| 2026-05-09 | [017-frontend-skeleton](./2026-05-09-017-frontend-skeleton.md) | 3 | main | ✅ | 프론트엔드 골격 (Vite + React + TS + TanStack Query) + 빌드/테스트 통과 |
| 2026-05-09 | [016-fastapi-conditions-api](./2026-05-09-016-fastapi-conditions-api.md) | 3 | main | ✅ | FastAPI 도입 + GET /api/conditions (메타데이터 자동 노출) + 6건 |
| 2026-05-09 | [015-alembic](./2026-05-09-015-alembic.md) | 2 | main | ✅ | **Phase 2 완료**: Alembic 도입 + baseline 마이그레이션 + 회귀 검증 3건 |
| 2026-05-09 | [014-services-layer](./2026-05-09-014-services-layer.md) | 2 | main | ✅ | strategy_service + backtest_service (Phase 1↔Phase 2 통합 + end-to-end 영속화) + 15건 |
| 2026-05-09 | [013-daily-equity-model](./2026-05-09-013-daily-equity-model.md) | 2 | main | ✅ | DailyEquity 모델 (UniqueConstraint + 복합 인덱스) + 5건 |
| 2026-05-09 | [012-trade-models](./2026-05-09-012-trade-models.md) | 2 | main | ✅ | TradeGroup + TradeExecution 모델 + SQLite PRAGMA foreign_keys 자동화 + 7건 |
| 2026-05-09 | [011-backtest-run-result-models](./2026-05-09-011-backtest-run-result-models.md) | 2 | main | ✅ | BacktestRun + BacktestResult 모델 (정확성 정책 스냅샷 모두 영속화) + 9건 |
| 2026-05-09 | [010-db-and-strategy-models](./2026-05-09-010-db-and-strategy-models.md) | 2 | main | ✅ | SQLAlchemy 인프라 + User/Strategy/StrategyVersion 모델 + DB 테스트 11건 |
| 2026-05-09 | [009-golden-test](./2026-05-09-009-golden-test.md) | 1 | main | ✅ | **Phase 1 완료**: Golden test fixture 4종 (frozen expected 9지표 + 결정론 10회) |
| 2026-05-09 | [008-metrics](./2026-05-09-008-metrics.md) | 1 | main | ✅ | calculate_metrics (12개 지표, trade_group 단위 집계) + 13건 테스트 |
| 2026-05-09 | [007-backtest-engine](./2026-05-09-007-backtest-engine.md) | 1 | main (backtest-engine-developer 대행) | ✅ | 단일 종목 BacktestEngine (정확성 정책 13.3/13.4/13.16 적용) + 13건 테스트 |
| 2026-05-09 | [006-execution-portfolio](./2026-05-09-006-execution-portfolio.md) | 1 | main (backtest-engine-developer 대행) | ✅ | ExecutionModel (호가/세율 시계열) + Portfolio (trade_groups 부분매도 + FIFO) + 70건 테스트 |
| 2026-05-09 | [005-strategy-engine](./2026-05-09-005-strategy-engine.md) | 1 | main | ✅ | StrategyEngine (entry/exit_signal/filters + AND/OR/GROUP) + 17건 테스트 |
| 2026-05-09 | [004-basic-conditions-5](./2026-05-09-004-basic-conditions-5.md) | 1 | main (condition-author 대행) | ✅ | 5개 기본 조건 (price_vs_ma / ma_cross / volume_ratio / rsi_level / take_profit) + 메타 카탈로그 + 44건 테스트 |
| 2026-05-09 | [003-indicators-and-compare](./2026-05-09-003-indicators-and-compare.md) | 1 | main | ✅ | venv 셋업 + indicators (MA/EMA/RSI/MACD) + compare 유틸 + 31건 테스트 |
| 2026-05-09 | [002-condition-registry](./2026-05-09-002-condition-registry.md) | 1 | main | ✅ | ConditionRegistry 코어 (라우팅 분기 + 메타데이터 + 16건 테스트) |
| 2026-05-09 | [001-project-skeleton](./2026-05-09-001-project-skeleton.md) | 1 | main | ✅ | 백엔드 패키지 골격 + 13개 모듈 디렉토리 + core (config/exceptions/logging) + smoke test 5건 |

---

## Phase 1 완료 ✅

모든 9단계 완료. 단일 종목 백테스트 end-to-end 동작 + Golden test 회귀 보증.

1. ✅ 프로젝트 골격 셋업 — 2026-05-09-001
2. ✅ ConditionRegistry 코어 구현 — 2026-05-09-002
3. ✅ indicators.py + compare 유틸리티 — 2026-05-09-003
4. ✅ 기본 조건 5개 — 2026-05-09-004
5. ✅ StrategyEngine 구현 — 2026-05-09-005
6. ✅ ExecutionModel + Portfolio (TradeGroup) — 2026-05-09-006
7. ✅ 단일 종목 BacktestEngine — 2026-05-09-007
8. ✅ Metrics — 2026-05-09-008
9. ✅ Golden test — 2026-05-09-009

## Phase 2 완료 ✅

모든 6단계 완료. SQLite 영속화 + 서비스 레이어 + 마이그레이션 시스템.

1. ✅ SQLAlchemy 모델 — users / strategies / strategy_versions — 2026-05-09-010
2. ✅ backtest_runs + backtest_results — 2026-05-09-011
3. ✅ trade_groups + trade_executions — 2026-05-09-012
4. ✅ daily_equity 모델 — 2026-05-09-013
5. ✅ services 레이어 (strategy_service + backtest_service) — 2026-05-09-014
6. ✅ Alembic 도입 + baseline 마이그레이션 — 2026-05-09-015

(cash_events는 Phase 6 CashManager 도입 시 추가)

## Phase 3 완료 ✅

1. ✅ FastAPI + GET /api/conditions — 2026-05-09-016
2. ✅ 프론트엔드 골격 (Vite + React + TS) — 2026-05-09-017
3. ✅ StrategyBuilderPage 골격 + Router — 2026-05-09-018
4. ✅ StrategyDraft 상태 + Canvas 카드 + 추가/삭제 — 2026-05-10-001
5. ✅ ConditionEditorPanel 자동 폼 — 2026-05-10-002
6. ✅ StrategyPreviewPanel + StrategyValidationPanel — 2026-05-10-003
7. ✅ 전략 저장 (Strategy CRUD + Save+redirect) — 2026-05-10-004

## Phase 4 완료 ✅

1. ✅ Backtest API + 합성 데이터 dev 모드 — 2026-05-10-005
2. ✅ BacktestRunPage + ResultPage + StrategyListPage 실데이터 — 2026-05-10-006

## Phase 5 완료 ✅

- chart-data API (candles + markers + equity_curve)
- CandleTradeChart (lightweight-charts) + EquityCurveChart
- BacktestResultPage에 차트 통합

## Phase 6 완료 ✅

설계서 05번 9~12절 적용.

1. ✅ PositionSizer + CashManager 모듈 — 2026-05-10-008
2. ✅ BacktestEngine에 cash_management 옵션 통합 — 2026-05-10-008
3. ✅ CashEvent DB 모델 + 영속화 — 2026-05-10-008

## Phase 7 완료 ✅

설계서 09번 적용.

1. ✅ CsvExporter (summary/trades/daily_equity/cash_events) — 2026-05-10-009
2. ✅ ZipExporter — 2026-05-10-009
3. ✅ /api/backtests/{id}/export/* 엔드포인트 — 2026-05-10-009
4. ✅ 결과 페이지에 다운로드 버튼 — 2026-05-10-009

## Phase 8 완료 ✅ (리뷰 011 Critical 5/5 + 외부 4.7 해소)

리뷰 011 §8 의존성·회귀 위험 분석에 따라 Wave A·B·C로 분할 — A1·A2 병렬 → B1 (A1 후) → C1·C2 (B1 후 순차).

### Wave A (병렬 2 step)
1. ✅ exit_position 조건 3종 Registry 등록 (C1 선결 + H5) — 2026-05-10-010 (condition-author)
2. ✅ strategy_json validator + user_id scope + 표준 envelope (C4 + C3 + H7) — 2026-05-10-011 (backend-api-engineer)

### Wave B (1 step)
3. ✅ exit_position 라우팅 통일 + peak_price prev-high (C1 + C5) — 2026-05-10-012 (backtest-engine-developer)

### Wave C (순차 2 step)
4. ✅ ExecutionResult dataclass + cash_manager의 ExecutionModel 주입 (C2 + H1 + M2 + M4) — 2026-05-10-013 (backtest-engine-developer)
5. ✅ TradeExecution.fee/tax + DailyEquity.daily/cumulative + cash_events 분해 영속화 + alembic 마이그레이션 (M5 + 외부 4.7) — 2026-05-10-014 (backend-api-engineer)

## Phase 11 완료 ✅ (5/5 step + test-engineer 🟢 ship-go)

### 완료 step
- ✅ 024 data_pipeline 패키지 골격 + ABC + 예외 계층
- ✅ 025 PykrxCollector + retry(jitter 없음) + validators(HARD/SOFT)
- ✅ 026 corporate_actions + AdjustedPriceProcessor (분할/배당, idempotent)
- ✅ 027 market_indices + universe_history + repositories 4종
- ✅ 028 5 jobs + Scheduler 락 + MissingDataCheckJob (forward-fill 금지)
- ✅ test-engineer 검증: 825 passed (+209) / 13.x·14.x 9개 정책 ✅ / Phase 1 골든 9지표 유지 / e2e 5건 신규

## Phase 12 다음 진입 — UI 확장

⏭ 다음: step 029 — 02 schema GUI 정합화 (position_sizing/cash_management/risk_management/execution/priority/metadata 6섹션 폼) (frontend-developer)

Phase 12~13 전체 계획은 [`로드맵.md`](../로드맵.md) "Phase 로드맵" 참조.

---

## 블록된 작업

(없음)
