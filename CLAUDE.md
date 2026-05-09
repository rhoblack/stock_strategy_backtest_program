# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

이 저장소는 **설계 단계** 프로젝트입니다. 현재 코드는 0줄, 한국어 설계 문서 17개만 있습니다. 모든 구현 작업은 `상세설계/` 폴더의 설계서를 단일 출처로 삼아 진행합니다.

문서/코드/커밋 메시지는 모두 **한국어**로 작성합니다.

## 프로젝트 정의

**한국 주식 시장 대상, GUI에서 매매 전략을 레고 블록처럼 조립하고 JSON으로 저장하면 Python 엔진이 그 JSON을 실행해 백테스트하는 전략 연구 플랫폼.**

차별화 포인트는 단순 신호 백테스트가 아닌 **현실적 자금 운용 시뮬레이션**입니다 (예수금 부족 시 보유 종목 일부 매도 등).

## 설계서 우선순위와 참조 규칙

`상세설계/00_index.md`가 전체 인덱스입니다. 작업 전 반드시 인덱스로 관련 문서를 확인하세요.

**13, 14번 문서는 정책 문서로, 다른 모든 문서를 우선합니다:**

- `13_backtest_accuracy_policy_design.md` — 일중 익절/손절, 갭/거래정지/한가, 호가 단위, 거래세 시계열, 수정주가, priority 결정론, look-ahead bias
- `14_data_pipeline_design.md` — pykrx 수집/캐싱/재시도, 시가총액 시계열, 수정주가 계산, corporate_actions, 생존편향 완화

다른 문서와 정책이 충돌하면 13/14를 우선 적용하고, 정책을 바꿔야 한다면 13/14를 먼저 갱신한 뒤 다른 문서가 참조하도록 동기화합니다.

## 절대로 어기면 안 되는 핵심 설계 원칙

구현 시 다음을 위반하면 즉시 중단하고 사용자에게 확인하세요.

1. **전략은 JSON 데이터, Python 코드가 아님.** JSON 안에 코드 문자열을 절대 넣지 않습니다 (eval 금지).
2. **조건은 ConditionRegistry에 `requires_position` 메타로 등록.** 시계열 조건은 `entry`/`exit_signal`/`filters`에, 포지션 조건은 `exit_position`에만. 라우팅 분기는 `requires_position` 플래그로 결정합니다.
3. **`exit`는 `exit_signal`(StrategyEngine 처리)과 `exit_position`(BacktestEngine 처리)으로 분리.** 단일 `exit` 키를 다시 만들지 마세요.
4. **부분매도는 `trade_groups + trade_executions` 1:N 모델.** 매수마다 `trade_group_id`를 발급하고, 매도는 항상 trade_group의 `remaining_quantity`만 줄입니다. trades를 1:1로 만들지 마세요.
5. **모든 가격 조건/체결은 수정주가(`adj_*`) 기본 사용.** `close`는 거래대금 필터 등 시장 유동성 평가에만 사용합니다.
6. **익절/손절은 일중 high/low로 평가**, 동일 봉 동시 도달 시 손절 우선 (보수적). 종가 기준만 보면 백테스트가 비현실적으로 좋아집니다.
7. **거래세는 시계열(`[{from, rate}]` 배열)로 처리.** 한국 거래세는 2022~2025년 사이 0.23%→0.15%로 변동되었습니다.
8. **동시 매수 신호는 `priority` 알고리즘 + `symbol_asc` tie-breaker.** Python dict/set 순서에 의존하면 결정론이 깨집니다.
9. **백테스트 실행 시 `strategy_snapshot_json` + 거래세/priority/random_seed/tick_rounding을 모두 `backtest_runs`에 저장.** 전략이 나중에 수정되어도 과거 결과가 재현되어야 합니다.
10. **유니버스는 `listing_date`/`delisting_date` 동적 필터 적용.** 현재 상장 종목만으로 과거 백테스트하면 생존편향으로 결과가 30~50% 좋게 보입니다.

## look-ahead bias 체크리스트

새 조건/지표를 추가할 때 매번 확인합니다:

- rolling 계산이 당일 값을 포함하지 않는지 (필요 시 `shift(1)`)
- 신고가 돌파 같은 조건은 전일까지의 high만 사용하는지
- 트레일링 스탑의 peak가 전일까지의 high인지
- 시가총액 상위 N종목 선정에 미래 데이터가 들어가지 않는지
- 신호일 종가로 신호, 다음날 시가로 체결인지

## 추천 기술 스택 및 디렉토리 (구현 시작 시)

설계서 (`상세설계/stock_strategy_lab_software_architecture.md` 2절)에서 정한 구조:

```text
backend/   FastAPI + Python (pandas/numpy)
frontend/  React + TypeScript + TanStack Query/Table
           + TradingView Lightweight Charts + ECharts
data/      raw/ cache/ exports/
docs/
```

DB는 SQLite로 시작해 PostgreSQL로 전환. 시세 대용량은 향후 Parquet.

백엔드 모듈 분리(architecture 문서 3절):
`strategy/` `backtest/` `portfolio/` `market_data/` `reports/` `exporters/` `api/` — 한 모듈에 책임을 몰지 말고 항상 분리합니다. 특히 BacktestEngine은 오케스트레이터이며 로직을 직접 갖지 않습니다.

## MVP 개발 단계

`stock_strategy_lab_program_introduction.md` 12절과 `architecture.md` 19절에 정의된 순서를 따릅니다.

```text
Phase 1. 백엔드 핵심 엔진 (조건 5개 + StrategyEngine + 단일종목 백테스트 + Metrics)
Phase 2. SQLite 저장 (users/strategies/backtest_runs/trade_groups/trade_executions/...)
Phase 3. GUI 전략 빌더
Phase 4. 백테스트 실행/결과 화면
Phase 5. 종목 봉차트 + 매수/매도 마커
Phase 6. Portfolio + CashManager (예수금 부족 시 일부 매도)
Phase 7. CSV/ZIP Export
```

각 Phase 시작 전 해당하는 상세설계 문서를 다시 읽고, 변경이 필요하면 문서를 먼저 갱신한 뒤 코드를 작성합니다.

## 작업 흐름 시 주의

- 정책/스키마 변경은 항상 **문서 먼저, 코드는 나중**. 13/14 정책 문서 또는 02 schema 문서를 먼저 갱신.
- 백테스트 결과의 재현성을 깨는 변경(priority, 일중 처리, 세율, 호가 단위 등)은 Golden test fixture(12 testing 15절)로 회귀 검증.
- Git 커밋 메시지는 한국어. 기존 커밋 메시지 스타일 참고.

## 작업 로그 시스템 (필수)

이 프로젝트는 세션 간 컨텍스트 인계를 위해 `작업로그/` 폴더에 모든 코딩 작업의 로그를 남깁니다.

### 새 세션 시작 시

**가장 먼저 `작업로그/README.md`를 읽으세요.** 다음 정보를 확인:
- 현재 Phase 상태 표
- 최근 작업 표 (최신 5~10개)
- 진행 중인 작업 (status: in_progress)
- 블록된 작업 (status: blocked, 이유 함께 확인)
- Phase 1 다음 작업 후보 (Phase 1 진행 중일 때)

이미 진행 중인 작업이 있으면 그 로그 파일을 먼저 읽어 이어서 진행합니다.

### 새 작업 시작 시

1. `작업로그/_TEMPLATE.md`를 복사해 새 로그 파일 생성
   - 명명 규칙: `YYYY-MM-DD-NNN-짧은-설명.md`
   - 예: `작업로그/2026-05-09-001-rsi-condition.md`
2. frontmatter (date, agent, phase, status, related_docs) 작성
3. **Plan 섹션을 체크리스트로 먼저 작성** — 실행 전 무엇을 할지 명확히
4. status를 `in_progress`로 변경
5. 실행 시작

### 에이전트 호출 시

메인 세션이 에이전트를 호출할 때 작업 로그 파일 경로를 함께 전달합니다.

> "작업로그/2026-05-09-001-rsi-condition.md를 참고해서 RSI 조건을 추가해줘. 작업 후 Execution / Tests / Result 섹션을 채워줘."

에이전트는 Execution / Tests / Result / Issues 섹션을 채우지만, **status 변경과 README.md 갱신은 메인 세션이 담당**합니다.

### 작업 완료 시 (메인 세션 책임)

`_TEMPLATE.md` 하단의 "메인 세션 마무리 체크" 항목을 모두 수행:

1. 로그 파일의 `status: completed`로 변경
2. `작업로그/README.md` "최근 작업" 표에 1행 추가
3. Phase 상태가 변경됐으면 Phase 표 갱신
4. Follow-ups 중 다음 작업 후보로 승격할 항목을 README의 "Phase N 다음 작업 후보"에 옮김

### 블록 / 중단 시

작업이 블록되거나 일시 중단되면:
- status를 `blocked` 또는 `in_progress`로 유지
- 블록 사유와 해소 조건을 Issues 섹션에 명시
- README.md "블록된 작업" 섹션에 항목 추가
