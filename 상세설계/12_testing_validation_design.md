# 12. 테스트 및 검증 상세 설계서

## 1. 목적

이 프로그램은 금융 계산과 백테스트 결과를 다루므로 테스트가 매우 중요합니다.

잘못된 백테스트 결과는 사용자에게 잘못된 투자 판단을 유도할 수 있습니다.

따라서 전략 조건, 체결, 수수료, 손익, MDD, 예수금 관리, CSV Export를 반드시 검증해야 합니다.

---

## 2. 테스트 범위

```text
전략 조건 테스트
전략 JSON 검증 테스트
StrategyEngine 테스트
BacktestEngine 테스트
Portfolio 테스트
CashManager 테스트
Metrics 테스트
MarketData 테스트
API 테스트
Frontend 테스트
CSV Export 테스트
```

---

## 3. 백엔드 테스트 구조

```text
tests/
├─ strategy/
│  ├─ test_price_conditions.py
│  ├─ test_ma_conditions.py
│  ├─ test_volume_conditions.py
│  ├─ test_rsi_conditions.py
│  └─ test_strategy_engine.py
│
├─ backtest/
│  ├─ test_execution.py
│  ├─ test_backtest_engine.py
│  ├─ test_metrics.py
│  └─ test_event_log.py
│
├─ portfolio/
│  ├─ test_portfolio.py
│  ├─ test_position_sizer.py
│  └─ test_cash_manager.py
│
├─ market_data/
│  ├─ test_universe_selector.py
│  └─ test_price_loader.py
│
├─ exporters/
│  └─ test_csv_exporter.py
│
├─ api/
│  ├─ test_strategies_api.py
│  ├─ test_backtests_api.py
│  └─ test_market_api.py
│
└─ fixtures/
   ├─ sample_prices.csv
   ├─ sample_strategy.json
   └─ sample_market_cap.csv
```

---

## 4. 전략 조건 테스트

### price_vs_ma

검증:

```text
종가가 이동평균선보다 높은 날짜에 True
낮은 날짜에 False
rolling 초기 NaN 구간 처리
```

### ma_cross

검증:

```text
전일 단기선 <= 전일 장기선
당일 단기선 > 당일 장기선
이 경우에만 golden_cross True
```

### new_high_breakout

검증:

```text
오늘 값을 포함하지 않고 전일까지의 최고가를 기준으로 판단
look-ahead bias 방지
```

---

## 5. StrategyEngine 테스트

검증:

```text
AND 조건 조합
OR 조건 조합
필터 조건 조합
조건이 없는 경우 처리
등록되지 않은 조건 타입 오류
```

예:

```text
조건 A True, 조건 B False
AND 결과 False
OR 결과 True
```

---

## 6. Portfolio 테스트

검증:

```text
초기 현금 설정
매수 후 현금 감소
매수 후 포지션 생성
매도 후 현금 증가
부분 매도 후 수량 감소
전량 매도 후 포지션 삭제
평가금액 계산
총자산 계산
```

---

## 7. CashManager 테스트

검증:

```text
예수금 충분 시 실행 안 함
예수금 부족 시 일부 매도 실행
lowest_return 종목 선택
highest_return 종목 선택
largest_value 종목 선택
sell_fraction 계산
repeat_until_cash_sufficient 동작
cash_events 생성
```

---

## 8. ExecutionModel 테스트

검증:

```text
next_open 체결 가격
close 체결 가격
매수 수수료 계산
매도 수수료 계산
거래세 계산
슬리피지 반영
```

---

## 9. BacktestEngine 테스트

검증:

```text
매수 신호 발생 시 매수
매도 조건 발생 시 매도
익절 처리
손절 처리
최대 보유일 처리
예수금 부족 시 매수 제한
예수금 부족 시 CashManager 실행
일별 자산 기록
거래 내역 생성
```

---

## 10. Metrics 테스트

검증:

```text
총 수익률
연평균 수익률
MDD
승률
평균 보유일
평균 수익률
평균 손실률
Profit Factor
```

MDD는 특히 별도 fixture로 검증합니다.

---

## 11. MarketData 테스트

검증:

```text
코스피 전체 종목 조회
코스닥 전체 종목 조회
ETF 제외 필터
시가총액 상위 N종목 선정
거래대금 상위 N종목 선정
유니버스 Preview 결과
```

---

## 12. CSV Export 테스트

검증:

```text
summary.csv 생성
trades.csv 생성
daily_equity.csv 생성
cash_events.csv 생성
universe_history.csv 생성
strategy_snapshot.json 포함
ZIP 파일 생성
한글 인코딩 확인
빈 데이터 처리
```

---

## 13. API 테스트

검증:

```text
전략 생성
전략 조회
전략 수정
전략 삭제
조건 목록 조회
백테스트 실행 요청
백테스트 결과 조회
거래 내역 조회
차트 데이터 조회
CSV 다운로드
```

---

## 14. 프론트엔드 테스트

### StrategyBuilder

```text
조건 목록 표시
조건 검색
조건 추가
조건 삭제
조건 파라미터 수정
전략 자연어 설명 표시
전략 검증 경고 표시
저장 버튼 동작
```

### BacktestResult

```text
요약 카드 표시
거래 내역 표시
차트 컴포넌트 렌더링
CSV 다운로드 버튼 표시
종목 선택 시 차트 변경
거래 클릭 시 차트 이동
```

---

## 15. 회귀 테스트

새 조건이나 기능 추가 시 반드시 확인합니다.

```text
기존 조건 결과가 바뀌지 않았는지
기존 백테스트 fixture 결과가 동일한지
CSV 컬럼이 깨지지 않았는지
API 응답 구조가 깨지지 않았는지
```

---

## 16. 샘플 fixture 전략

테스트용 전략:

```json
{
  "entry": {
    "logic": "AND",
    "conditions": [
      {
        "type": "price_vs_ma",
        "price_field": "close",
        "ma_period": 5,
        "operator": ">"
      }
    ]
  },
  "exit": {
    "logic": "OR",
    "conditions": [
      {
        "type": "take_profit",
        "percent": 5
      },
      {
        "type": "stop_loss",
        "percent": 3
      }
    ]
  }
}
```

---

## 17. 품질 기준

MVP 기준 최소 품질 기준:

```text
핵심 조건 함수 테스트 통과
StrategyEngine 테스트 통과
BacktestEngine 테스트 통과
Portfolio/CashManager 테스트 통과
CSV Export 테스트 통과
API 테스트 통과
프론트엔드 주요 플로우 테스트 통과
```

---

## 18. 수동 검증 시나리오

```text
1. 새 전략 생성
2. 조건 3개 추가
3. 전략 저장
4. 백테스트 실행
5. 결과 요약 확인
6. 종목 봉차트에서 매수/매도 마커 확인
7. 거래 내역 클릭 시 차트 이동 확인
8. CSV 다운로드
9. 전략 복사 후 조건 변경
10. 다시 백테스트
11. 결과 비교
```
