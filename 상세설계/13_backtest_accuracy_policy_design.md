# 13. 백테스트 정확성 정책 설계서

## 1. 목적

이 문서는 백테스트 결과의 신뢰성과 재현성을 보장하기 위한 정책을 모아둡니다.

같은 전략과 같은 데이터로 누가 실행해도 항상 동일한 결과가 나와야 하며, 결과가 실제 시장에서 가능한 체결을 반영해야 합니다.

이 문서에 명시되지 않은 정책은 다른 설계 문서에서 임의로 결정하지 않고, 본 문서를 우선 갱신한 후 참조해야 합니다.

---

## 2. 핵심 원칙

```text
같은 입력은 항상 같은 출력을 보장한다 (결정론).
look-ahead bias를 절대 허용하지 않는다.
체결은 실제 시장에서 가능한 조건에서만 발생한다.
정책 분기점은 명시적으로 문서화하고, 코드 if/else에 숨기지 않는다.
모호한 엣지 케이스는 보수적으로 (불리한 쪽으로) 처리한다.
```

---

## 3. 일중 익절/손절 처리 정책

### 3.1 기본 정책

일봉 데이터로 백테스트하지만, 일중 high/low로 익절/손절 도달 여부를 판단합니다.

```text
손절 도달 판정:
당일 low <= 매수가 × (1 - stop_loss_pct/100)
→ 손절가에 정확히 체결된 것으로 가정

익절 도달 판정:
당일 high >= 매수가 × (1 + take_profit_pct/100)
→ 익절가에 정확히 체결된 것으로 가정
```

종가 기준이 아닌 일중 도달 기준을 사용하는 이유:
종가만 보면 장중에 -10% 떨어졌다가 -1%로 마감한 경우 손절이 발생하지 않은 것으로 처리되어 백테스트가 비현실적으로 좋게 나옵니다.

### 3.2 동일 봉에서 익절·손절 동시 도달 시

당일 high와 low 모두가 익절/손절선을 동시에 침범한 경우:

```text
보수적 정책: 손절을 우선 처리한다.
```

이유:
일봉 데이터로는 일중 시계열을 알 수 없습니다. 손절 우선 정책은 결과를 불리한 쪽으로 편향시켜 사용자를 보호합니다.

향후 분봉 데이터를 도입하면 시계열 순서대로 처리할 수 있습니다.

### 3.3 시가가 이미 손절선을 돌파한 경우 (갭 다운)

```text
당일 open <= 매수가 × (1 - stop_loss_pct/100)
→ 시가에 체결 (손절가가 아닌 시가, 즉 추가 손실)
exit_reason = "gap_down_stop_loss"
```

### 3.4 시가가 이미 익절선을 돌파한 경우 (갭 업)

```text
당일 open >= 매수가 × (1 + take_profit_pct/100)
→ 시가에 체결 (익절가가 아닌 시가, 즉 추가 수익)
exit_reason = "gap_up_take_profit"
```

### 3.5 트레일링 스탑

```text
보유 기간 동안 매일 종가 갱신:
peak_price = max(peak_price, 당일 high)

다음날부터 적용:
손절선 = peak_price × (1 - trailing_pct/100)

당일 low <= 손절선 → 손절선 가격에 체결
```

look-ahead bias 방지를 위해 peak_price 갱신은 전일까지의 high만 사용합니다.

---

## 4. 갭 / 거래정지 / 상한가 / 하한가 처리

### 4.1 갭 매수 처리

매수 신호가 발생한 다음 거래일 시가가 신호일 종가 대비 큰 갭으로 출발한 경우:

```text
설정 옵션:
"max_gap_pct_for_entry": 5.0

다음날 시가가 신호일 종가 대비 +5% 초과 갭상승 →
매수 건너뜀 (skip)
event_log에 "buy_skipped_gap_up" 기록
```

기본값: `5.0` (한국 주식 변동성 기준 보수적 값)

### 4.2 거래정지 종목

```text
당일 거래정지 종목:
- 매수 신호 발생 → 매수 건너뜀
- 매도 조건 충족 → 다음 거래 가능일까지 매도 보류
- 평가금액은 마지막 종가로 유지

거래정지가 N일 이상 지속되면:
- 평가금액을 0으로 처리할지 옵션 제공 (기본: false, 마지막 종가 유지)
```

### 4.3 상한가 / 하한가

한국 주식 가격 제한폭은 ±30%입니다.

```text
매수 신호일 종가가 상한가:
"allow_buy_limit_up": false (기본)
→ 매수 건너뜀, 이유: 상한가 매수 비현실

매도 조건 충족일 종가가 하한가:
"allow_sell_limit_down": false (기본)
→ 매도 보류, 다음 거래일 재시도
```

### 4.4 거래량 0인 날

```text
당일 거래량이 0인 종목:
- 매수/매도 모두 건너뜀
- event_log에 "no_volume" 기록
```

### 4.5 상장폐지 발생

보유 중 상장폐지된 종목:

```text
정리매매 마지막 종가에 강제 매도
exit_reason = "delisting"

정리매매 데이터가 없으면:
직전 거래일 종가 × 0.5로 강제 매도 (보수적 추정)
exit_reason = "delisting_estimated"
```

---

## 5. 호가 단위 (Tick Size) 정책

### 5.1 한국 주식 호가 단위 (2025년 기준)

```text
가격 < 2,000원       : 1원
2,000원 ≤ 가격 < 5,000원   : 5원
5,000원 ≤ 가격 < 20,000원  : 10원
20,000원 ≤ 가격 < 50,000원 : 50원
50,000원 ≤ 가격 < 200,000원 : 100원
200,000원 ≤ 가격 < 500,000원 : 500원
500,000원 ≤ 가격            : 1,000원
```

코스닥은 별도 호가 단위가 있으므로 코드 상수로 분리해 관리합니다.

### 5.2 체결가 보정

체결 시 ExecutionModel은 호가 단위로 가격을 반올림합니다.

```python
def round_to_tick(price: float, market: str = "KOSPI") -> int:
    tick = get_tick_size(price, market)
    return int(round(price / tick) * tick)
```

슬리피지를 적용한 후 호가 단위로 반올림한 값이 최종 체결가입니다.

```text
slippage_applied = price × (1 + slippage)
final_price = round_to_tick(slippage_applied)
```

매수는 위쪽으로, 매도는 아래쪽으로 보수 반올림하는 옵션도 제공합니다.

---

## 6. 거래세 시계열 정책

### 6.1 한국 거래세 변동 이력

```text
~2022-12-31: 0.23%
2023-01-01 ~ 2023-12-31: 0.20%
2024-01-01 ~ 2024-12-31: 0.18%
2025-01-01 ~ : 0.15%
```

코스닥 농어촌특별세 등 상세는 별도 표로 관리합니다.

### 6.2 schema 표현

전략 JSON의 `execution.tax_rate`는 단일 값 또는 시계열을 받습니다.

```json
{
  "execution": {
    "tax_rate": [
      { "from": "2020-01-01", "rate": 0.0023 },
      { "from": "2023-01-01", "rate": 0.0020 },
      { "from": "2024-01-01", "rate": 0.0018 },
      { "from": "2025-01-01", "rate": 0.0015 }
    ]
  }
}
```

단일 값을 주면 백테스트 전체 기간에 동일하게 적용 (간단한 사용성 유지).

### 6.3 ExecutionModel 동작

매도 체결 시 해당 거래일에 해당하는 세율을 검색하여 적용합니다.

```python
def get_tax_rate(self, date) -> float:
    if isinstance(self.tax_rate, float):
        return self.tax_rate
    for entry in reversed(self.tax_rate):
        if date >= entry["from"]:
            return entry["rate"]
    return 0.0
```

---

## 7. 수정주가 정책

### 7.1 원칙

```text
모든 가격 기반 조건과 백테스트 체결은 기본적으로 수정주가를 사용한다.
거래량도 액면분할 비율을 적용한 수정 거래량을 사용한다.
```

### 7.2 데이터 필드

`daily_prices` 테이블에는 다음을 모두 저장합니다.

```text
open, high, low, close                  : 원 가격
adj_open, adj_high, adj_low, adj_close  : 수정 가격
volume                                  : 원 거래량
adj_volume                              : 수정 거래량
adjustment_factor                       : 누적 조정 계수
```

### 7.3 사용 정책

```text
조건 평가 (StrategyEngine):
adj_close, adj_open, adj_high, adj_low 사용

체결 가격 (ExecutionModel):
adj_close, adj_open 사용

차트 표시:
사용자 선택 옵션 (기본: 수정 가격)

거래대금 필터:
원 거래대금 사용 (실제 시장 유동성)
```

### 7.4 수정주가가 없는 종목

수정주가 데이터가 없거나 결손인 경우:

```text
백테스트 시작 시 경고 표시
영향 종목 목록을 universe_history에 함께 기록
```

---

## 8. 동시 매수 신호 우선순위 알고리즘

### 8.1 문제

코스피 전체 백테스트에서 한 날짜에 50개 종목이 매수 신호를 낼 수 있습니다. 매수 가능 한도가 1종목이면 어느 종목을 살지 결정해야 합니다.

### 8.2 priority schema

전략 JSON의 신규 섹션 `priority`로 명시합니다.

```json
{
  "priority": {
    "method": "trading_value_desc",
    "tie_breaker": "symbol_asc"
  }
}
```

### 8.3 지원 method

```text
trading_value_desc:  20일 평균 거래대금 큰 순 (기본)
market_cap_desc:     시가총액 큰 순
market_cap_asc:      시가총액 작은 순
volume_ratio_desc:   거래량 급증 비율 큰 순
price_change_desc:   당일 등락률 큰 순
score_desc:          사용자 정의 score (향후 확장)
random:              결정론 시드를 받아 무작위
```

### 8.4 tie-breaker

같은 우선순위 값을 가진 종목들 사이의 순서:

```text
symbol_asc:  종목코드 오름차순 (기본, 결정론 보장)
symbol_desc: 종목코드 내림차순
```

종목코드 정렬을 기본 tie-breaker로 두는 이유는 Python dict/set 순서나 DB 정렬에 의존하지 않고 항상 동일한 결과를 보장하기 위해서입니다.

### 8.5 적용 흐름

```text
1. 당일 final_entry_signal = True인 종목 추출
2. 이미 보유 중인 종목 제외 (또는 추가매수 허용 정책에 따라)
3. priority.method로 정렬
4. 동순위는 tie_breaker로 정렬
5. max_daily_entries만큼 상위 추출
6. 예수금 범위 내에서 차례로 매수
```

---

## 9. 추가매수 정책

### 9.1 기본 정책

MVP 기본값은 추가매수 비활성화입니다.

```json
{
  "position_sizing": {
    "allow_pyramiding": false
  }
}
```

이미 보유 중인 종목에서 매수 신호가 발생해도 매수하지 않습니다.

### 9.2 추가매수 활성화 시 평단가 처리

```json
{
  "position_sizing": {
    "allow_pyramiding": true,
    "pyramiding_method": "weighted_average",
    "max_pyramiding_count": 3
  }
}
```

```text
weighted_average:
새 평균단가 = (기존 수량 × 기존 평단가 + 신규 수량 × 신규 가격) / 총 수량

별도 trade_group:
추가매수마다 새 trade_group 생성 (FIFO 매도 시 유용)
```

MVP에서는 `weighted_average`만 지원합니다.

### 9.3 부분 매도 후 평단가

부분 매도가 발생해도 평균단가는 유지됩니다 (남은 포지션의 평단가는 변하지 않음).

---

## 10. 배당 / 권리락 처리

### 10.1 MVP 정책

```text
배당:
보유 중 배당 발생 시 권리락일에 종가가 자동 조정됨 → 수정주가로 흡수.
별도 현금 유입 처리 없음 (단순화).

유상증자 / 무상증자 / 액면분할:
모두 수정주가로 가격을 통합 관리.
```

### 10.2 향후 확장

```text
실현 배당금 cash_events에 별도 기록
배당 재투자 옵션
```

---

## 11. 거래일 캘린더

### 11.1 기준

```text
KRX 공식 거래일 기준 (휴장일 반영).
거래일 목록은 별도 trading_calendar 테이블에 저장.
```

### 11.2 거래일 데이터 소스

```text
1순위: KRX 휴장일 공식 데이터
2순위: pykrx의 거래일 기준
3순위: 일봉 데이터에 존재하는 날짜 집합
```

거래일 캘린더 결손 시 백테스트 시작 전에 명시적으로 에러를 발생시킵니다.

---

## 12. 결정론 보장

### 12.1 결정론 깨짐 방지 규칙

```text
Python set / dict 순서에 의존 금지 → 종목코드 정렬 후 순회
랭덤 함수 사용 시 시드 고정 (random_seed 파라미터)
부동소수 비교는 항상 호가 단위 반올림 후
DB 쿼리는 항상 ORDER BY 명시
```

### 12.2 random_seed

전략 JSON의 metadata에 random_seed를 두어 무작위 우선순위 method 사용 시 결정론을 보장합니다.

```json
{
  "metadata": {
    "random_seed": 42
  }
}
```

---

## 13. 시간대 (Timezone)

```text
모든 거래 일자는 KST (Asia/Seoul) 기준
DB의 timestamp 컬럼은 UTC로 저장하고 표시 시 KST로 변환
거래일은 timezone 없는 date 타입으로 통일
```

---

## 14. 통화

```text
모든 금액은 KRW (한국 원화)
소수점 없는 정수로 처리 (cash, equity 등)
수익률은 float, 백분율 단위
```

---

## 15. look-ahead bias 방지 체크리스트

새 조건/지표 추가 시 반드시 확인합니다.

```text
[ ] rolling 계산이 당일 값을 포함하지 않는가? (필요 시 shift(1))
[ ] 거래량/거래대금 평균이 전일까지의 데이터인가?
[ ] 시가총액 상위 N종목 선정에 미래 데이터가 들어가지 않는가?
[ ] 신호일 종가로 신호 발생, 다음날 시가로 체결인가?
[ ] 트레일링 스탑의 peak가 전일까지의 high인가?
```

---

## 16. 정책 우선순위 충돌 시

여러 정책이 동시에 적용되어 충돌하는 경우의 우선순위:

```text
1. 거래정지 / 상한가 / 하한가 (체결 자체 불가능)
2. 갭 처리 (체결 가격 보정)
3. 익절/손절 (포지션 기반 매도)
4. 지표 기반 매도
5. 신규 매수
6. 자금 관리 일부 매도
```

같은 날짜에 여러 이벤트가 동시에 발생할 때 위 순서로 처리합니다.

---

## 17. 정확성 정책 검증 항목

```text
일중 손절 도달 정확성
일중 익절 도달 정확성
동일 봉 익절·손절 동시 도달 시 손절 우선
갭 다운 손절 시 시가 체결
거래정지 종목 매수/매도 차단
상한가 매수 차단
호가 단위 반올림
거래세 시계열 적용
수정주가 사용 일관성
동시 신호 우선순위 결정론
random_seed 동일 시 동일 결과
```

각 항목은 12 testing 문서의 golden test fixture로 검증합니다.

---

## 18. 향후 확장

```text
분봉 데이터 도입 시 일중 시계열 순서대로 처리
체결 슬리피지 모델 고도화 (거래량 기반 동적 슬리피지)
호가창 모델 (limit order book)
실제 체결 가능성 모델 (참여율 기반)
```
