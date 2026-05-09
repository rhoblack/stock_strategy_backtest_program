# 09. CSV 및 ZIP Export 상세 설계서

## 1. 목적

CSV Export 기능은 백테스트 결과를 사용자가 엑셀, Python, 외부 분석 도구에서 활용할 수 있게 하는 기능입니다.

DB는 내부 저장소이고, CSV는 사용자 다운로드용 내보내기 파일입니다.

---

## 2. Export 원칙

```text
백테스트 결과는 DB에 저장한다.
CSV는 사용자가 원할 때 생성한다.
개별 CSV 다운로드와 ZIP 전체 다운로드를 모두 지원한다.
실행 당시 전략 JSON도 함께 내보낼 수 있어야 한다.
```

---

## 3. Export 파일 목록

```text
summary.csv
trades.csv
daily_equity.csv
symbol_performance.csv
cash_events.csv
universe_history.csv
strategy_snapshot.json
```

ZIP 전체 다운로드 시:

```text
backtest_{strategy_name}_{run_id}.zip
```

---

## 4. summary.csv

백테스트 요약 결과입니다.

컬럼:

```text
strategy_name
run_name
start_date
end_date
universe
initial_cash
final_equity
total_return
annual_return
mdd
win_rate
trade_count
avg_holding_days
profit_factor
sharpe_ratio
created_at
```

예시:

```csv
strategy_name,run_name,start_date,end_date,initial_cash,final_equity,total_return,mdd,win_rate,trade_count
거래량돌파전략,코스닥_2020_2025,2020-01-01,2025-12-31,10000000,18420000,84.2,-18.5,47.8,312
```

---

## 5. trades.csv

매수/매도 거래 내역입니다.

컬럼:

```text
symbol
name
entry_date
entry_price
entry_quantity
entry_amount
exit_date
exit_price
exit_quantity
exit_amount
profit
profit_rate
holding_days
exit_reason
```

예시:

```csv
symbol,name,entry_date,entry_price,entry_quantity,exit_date,exit_price,profit_rate,holding_days,exit_reason
005930,삼성전자,2024-03-12,72000,13,2024-04-05,78200,8.61,17,take_profit
035420,NAVER,2024-05-10,182000,5,2024-05-17,174000,-4.39,5,stop_loss
```

---

## 6. daily_equity.csv

일별 자산 변화입니다.

컬럼:

```text
date
cash
stock_value
total_equity
daily_return
cumulative_return
drawdown
positions_count
```

예시:

```csv
date,cash,stock_value,total_equity,cumulative_return,drawdown,positions_count
2024-03-12,9064000,936000,10000000,0.0,0.0,1
2024-03-13,9064000,954200,10018200,0.18,0.0,1
```

---

## 7. symbol_performance.csv

종목별 성과입니다.

컬럼:

```text
symbol
name
trade_count
win_rate
total_profit
avg_profit_rate
max_profit_rate
max_loss_rate
avg_holding_days
```

예시:

```csv
symbol,name,trade_count,win_rate,total_profit,avg_profit_rate,max_profit_rate,max_loss_rate
005930,삼성전자,18,55.6,820000,2.8,11.3,-4.2
035420,NAVER,12,41.7,-230000,-0.9,6.1,-5.3
```

---

## 8. cash_events.csv

예수금 부족, 일부 매도 이벤트입니다.

컬럼:

```text
date
event_type
cash_before
required_cash
action
symbol
sell_quantity
sell_amount
cash_after
reason
```

예시:

```csv
date,event_type,cash_before,required_cash,action,symbol,sell_quantity,sell_amount,cash_after,reason
2024-06-11,cash_shortage,620000,1000000,partial_sell,005930,5,410000,1030000,cash_shortage_partial_sell
```

---

## 9. universe_history.csv

시가총액 상위 N종목처럼 유니버스가 있는 경우 저장합니다.

컬럼:

```text
date
market
selection_method
rank
symbol
name
market_cap
trading_value
```

예시:

```csv
date,market,selection_method,rank,symbol,name,market_cap
2020-01-02,KOSPI,market_cap_top_n,1,005930,삼성전자,300000000000000
```

---

## 10. strategy_snapshot.json

백테스트 실행 당시 전략 JSON입니다.

필수 포함 이유:

```text
전략은 이후 수정될 수 있다.
과거 백테스트 결과를 재현하려면 실행 당시 전략 JSON이 필요하다.
```

---

## 11. Export API

```text
GET /api/backtests/{run_id}/export/summary
GET /api/backtests/{run_id}/export/trades
GET /api/backtests/{run_id}/export/daily-equity
GET /api/backtests/{run_id}/export/symbol-performance
GET /api/backtests/{run_id}/export/cash-events
GET /api/backtests/{run_id}/export/universe-history
GET /api/backtests/{run_id}/export/strategy-snapshot
GET /api/backtests/{run_id}/export/zip
```

---

## 12. CsvExporter 구조

```python
class CsvExporter:
    def export_summary(self, run_id: int) -> bytes:
        pass

    def export_trades(self, run_id: int) -> bytes:
        pass

    def export_daily_equity(self, run_id: int) -> bytes:
        pass

    def export_cash_events(self, run_id: int) -> bytes:
        pass

    def export_zip(self, run_id: int) -> bytes:
        pass
```

---

## 13. 한글 CSV 인코딩

엑셀 호환성을 위해 옵션을 제공합니다.

```text
UTF-8
UTF-8 with BOM
CP949
```

기본값:

```text
UTF-8 with BOM
```

---

## 14. 프론트엔드 UI

```text
[CSV 다운로드]

☑ 요약 결과
☑ 거래 내역
☑ 일별 자산 변화
☑ 종목별 성과
☑ 예수금 이벤트
☑ 유니버스 이력
☑ 전략 JSON

[개별 다운로드] [ZIP으로 전체 다운로드]
```

---

## 15. 테스트 항목

```text
summary.csv 컬럼 확인
trades.csv 거래 수 확인
daily_equity.csv 날짜 순서 확인
cash_events.csv 이벤트 수 확인
ZIP 파일 내 모든 파일 포함 여부
한글 파일명/내용 인코딩 확인
전략 스냅샷 JSON 포함 여부
빈 데이터 처리
```
