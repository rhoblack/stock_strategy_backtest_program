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

## 전체 설계 원칙

```text
전략은 JSON 데이터로 저장한다.
Python 엔진은 JSON을 해석하여 실행한다.
전략 조건은 Registry 방식으로 확장한다.
백테스트 엔진은 오케스트레이터 역할만 한다.
포트폴리오, 체결, 예수금, 데이터, 리포트 기능은 분리한다.
GUI는 사람이 읽는 문장형 블록 중심으로 만든다.
백테스트 결과는 DB에 저장하고 CSV는 Export 기능으로 제공한다.
```
