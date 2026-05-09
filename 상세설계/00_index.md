# 기능별 상세 설계서 목록

이 폴더는 레고형 주식 매매 전략 생성 및 백테스트 프로그램의 기능별 상세 설계서를 분리한 문서 모음입니다.

## 문서 목록

| 번호 | 파일명 | 내용 |
|---:|---|---|
| 01 | `01_strategy_builder_gui_design.md` | 레고형 전략 생성 GUI 상세 설계 |
| 02 | `02_strategy_json_schema_design.md` | 전략 JSON 스키마 상세 설계 |
| 03 | `03_condition_registry_engine_design.md` | 조건 Registry 및 전략 실행 엔진 설계 |
| 04 | `04_backtest_engine_design.md` | 백테스트 엔진 상세 설계 |
| 05 | `05_portfolio_cash_management_design.md` | 포트폴리오 및 예수금 관리 설계 |
| 06 | `06_market_data_universe_design.md` | 시장 데이터 및 종목군 유니버스 설계 |
| 07 | `07_database_design.md` | DB 테이블 및 저장 구조 설계 |
| 08 | `08_backtest_result_chart_design.md` | 백테스트 결과 차트/리포트 UI 설계 |
| 09 | `09_csv_export_design.md` | CSV/ZIP Export 상세 설계 |
| 10 | `10_api_design.md` | 백엔드 API 상세 설계 |
| 11 | `11_frontend_architecture_design.md` | 프론트엔드 구조 및 컴포넌트 설계 |
| 12 | `12_testing_validation_design.md` | 테스트 및 검증 설계 |
| 13 | `13_backtest_accuracy_policy_design.md` | **백테스트 정확성 정책 (정합성 / 결정론)** |
| 14 | `14_data_pipeline_design.md` | **시장 데이터 수집·갱신 파이프라인** |

13, 14는 다른 모든 문서가 참조하는 정책 문서입니다. 정책 변경 시 본 두 문서를 먼저 갱신해야 합니다.

## 전체 설계 원칙

```text
전략은 JSON 데이터로 저장한다.
Python 엔진은 JSON을 해석하여 실행한다.
전략 조건은 Registry 방식으로 확장한다.
조건은 시계열 조건과 포지션 조건으로 분리한다 (requires_position 메타).
백테스트 엔진은 오케스트레이터 역할만 한다.
포트폴리오, 체결, 예수금, 데이터, 리포트 기능은 분리한다.
포트폴리오는 trade_group 단위로 관리한다 (부분매도 핵심).
GUI는 사람이 읽는 문장형 블록 중심으로 만든다.
백테스트 결과는 DB에 저장하고 CSV는 Export 기능으로 제공한다.
백테스트는 항상 비동기로 실행하고 진행률을 폴링한다.
정합성 / 결정론 / 데이터 정책은 13, 14 문서를 단일 출처로 한다.
실행 당시 전략 JSON, 거래세 시계열, priority 알고리즘, random_seed를 모두 스냅샷에 저장한다.
```

## 핵심 정책 요약 (정확성 정책 13 문서 기준)

```text
일중 익절/손절: high/low로 평가, 동시 도달 시 손절 우선
갭 다운/업: 시가 체결 (다른 exit_reason)
거래세: 시계열 ([{from, rate}] 배열) 적용
호가 단위: 가격대별 반올림 (buy_up_sell_down 기본)
수정주가: 모든 가격 조건/체결의 기본값
priority: trading_value_desc + symbol_asc tie-breaker (기본)
생존편향: listing_date / delisting_date 기반 동적 유니버스
random_seed: random method 사용 시 결정론 보장
```

## 데이터 모델 핵심 (07 DB 문서 기준)

```text
users (멀티유저 대비 user_id FK 구조)
strategies / strategy_versions
backtest_runs (snapshot + 정책 필드 모두 저장)
trade_groups (매수 lot 1개)
trade_executions (매수/매도 1행, 부분매도 N행)
daily_equity / cash_events / universe_history
symbols / daily_prices (수정주가 + 시가총액 시계열)
trading_calendar / corporate_actions
```
