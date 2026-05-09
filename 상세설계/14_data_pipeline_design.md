# 14. 데이터 파이프라인 설계서

## 1. 목적

이 문서는 백테스트에 필요한 시장 데이터를 수집, 저장, 갱신, 검증하는 파이프라인을 설계합니다.

데이터 인프라는 사실상 MVP 작업량의 절반을 차지합니다. 데이터 정확성과 가용성이 백테스트 결과의 신뢰성을 결정합니다.

---

## 2. 핵심 원칙

```text
데이터 수집은 백테스트와 분리된 별도 파이프라인으로 동작한다.
실패는 항상 발생할 수 있다. 재시도, 결손 감지, 알림이 필수다.
데이터 소스는 추상화하여 교체 가능하게 한다.
한 번 수집한 데이터는 캐시하여 재수집 비용을 줄인다.
수정주가는 분할/배당 발생 시 전체 시계열을 재계산해야 한다.
```

---

## 3. 수집 대상 데이터

```text
1. 종목 마스터 (symbols)
   - 코스피/코스닥 전 종목 메타데이터
   - 상장일, 상장폐지일, 시장구분, 업종
   - ETF/ETN/스팩/우선주/관리종목 플래그
   
2. 일봉 시세 (daily_prices)
   - OHLCV
   - 거래대금
   - 수정주가 (adj_open, adj_high, adj_low, adj_close)
   - 수정 거래량 (adj_volume)
   - 시가총액
   
3. 거래일 캘린더 (trading_calendar)
   - KRX 공식 휴장일 반영
   
4. 시장 지수 (market_indices)
   - KOSPI, KOSDAQ, KOSPI200 일봉
   - 벤치마크 비교 및 시장 지수 필터에 사용

5. 정정 이력 (corporate_actions)
   - 액면분할/병합
   - 유무상증자
   - 배당
```

---

## 4. 데이터 소스

### 4.1 1차 소스 (MVP)

```text
pykrx:
- 코스피/코스닥 일봉, 종목 목록, 시가총액
- 무료, Python 패키지
- KRX 사이트 스크래핑 기반 → 안정성 중간

KRX 정보데이터시스템:
- 휴장일, 종목 마스터
- 정합성 가장 높음
```

### 4.2 보조 소스

```text
FinanceDataReader:
- pykrx 보완용
- 종목 마스터, 지수 데이터에 강함

KIND (한국거래소 공시):
- 상장폐지, 액면분할 같은 corporate actions
```

### 4.3 향후 확장

```text
증권사 API (키움, 한투 등):
- 실시간 데이터, 안정성 높음
- 인증 필요

유료 데이터 (DataGuide, Quantiwise):
- 가장 정합성 높음, 비용 높음
```

### 4.4 Provider 추상화

`MarketDataProvider` 인터페이스(06 문서 정의)를 통해 모든 소스를 동일 인터페이스로 다룹니다.

---

## 5. 파이프라인 구조

```text
data_pipeline/
├─ collectors/
│  ├─ pykrx_collector.py
│  ├─ krx_calendar_collector.py
│  └─ corporate_action_collector.py
│
├─ processors/
│  ├─ adjusted_price_calculator.py
│  ├─ market_cap_calculator.py
│  └─ data_validator.py
│
├─ storage/
│  ├─ symbol_repository.py
│  ├─ price_repository.py
│  └─ calendar_repository.py
│
├─ jobs/
│  ├─ daily_update_job.py
│  ├─ historical_backfill_job.py
│  └─ corporate_action_apply_job.py
│
└─ scheduler.py
```

---

## 6. 수집 시나리오

### 6.1 초기 백필 (Historical Backfill)

처음 데이터를 구축할 때:

```text
1. 종목 마스터 수집 (전 종목)
2. 거래일 캘린더 수집 (지난 10년)
3. corporate_actions 수집
4. 일봉 데이터 수집 (지난 10년, 종목별 순회)
5. 수정주가 계산 (corporate_actions 기반)
6. 시가총액 시계열 계산 (시가총액 = 종가 × 상장주식수)
7. 전체 데이터 검증
```

소요 시간 예상:
- 코스피 + 코스닥 약 2,800종목 × 10년 일봉
- pykrx rate limit 고려 시 수일 ~ 1~2주
- 단계별 체크포인트 저장 필수

### 6.2 일일 증분 수집 (Daily Update)

```text
매일 장 마감 후 (18:00 KST 권장):
1. 신규 종목 / 상장폐지 종목 점검
2. 당일 일봉 수집 (전 종목)
3. corporate_actions 수집
4. 영향받은 종목의 수정주가 재계산
5. 결손 종목 알림
6. 데이터 검증
```

### 6.3 재시도 / 백오프

```text
요청 실패 시:
- 1회: 1초 후 재시도
- 2회: 5초 후 재시도
- 3회: 30초 후 재시도
- 그 이후: 작업 큐에 보류, 다음 실행 주기에 재시도

연속 실패 5회:
- 알림 발송 (이메일 / Slack / 로그)
- 해당 종목/날짜를 재시도 큐에 영구 보관
```

### 6.4 KRX 차단 대응

pykrx는 KRX 사이트 스크래핑 기반이므로 rate limit 또는 차단이 발생할 수 있습니다.

```text
대응책:
1. 요청 간격 최소 0.5초 이상 (실험으로 조정)
2. User-Agent 회전
3. 차단 감지 시 자동 일시정지 + 30분 후 재개
4. fallback provider (FinanceDataReader)로 자동 전환
5. 차단 패턴 학습 후 시간대 분산
```

---

## 7. 데이터 검증

### 7.1 자동 검증 항목

```text
일봉 결손:
- 거래일에 데이터가 없는 종목 발견 시 알림
- 거래정지/관리종목인지 확인 후 정상 결손 분류

OHLC 정합성:
- low <= open, close, high
- high >= open, close, low
- 모든 값 > 0

거래량 / 거래대금 정합성:
- volume >= 0
- trading_value ≈ 평균가 × volume (오차 5% 이내)

가격 점프:
- 전일 대비 ±35% 초과 시 corporate action 가능성 확인
- corporate_action이 없으면 수동 확인 큐에 등록

수정주가 계산 정합성:
- adj_close[t] / adj_close[t-1] ≈ close[t] / close[t-1] × adjustment_factor
```

### 7.2 검증 실패 시 처리

```text
HARD FAIL (백테스트 차단):
- 거래일 캘린더 결손
- 사용자가 선택한 종목의 일봉 결손

SOFT FAIL (경고만):
- 시가총액 결손
- 거래대금 결손
- 일부 종목 일봉 결손
```

---

## 8. 시가총액 시계열

### 8.1 데이터 양 추정

```text
종목 수: 약 2,800 (코스피 + 코스닥)
거래일 수: 1년 약 245일, 10년 약 2,450일
총 row 수: 약 6.86M rows

일평균 신규 데이터: 약 2,800 rows/일
연간 신규 데이터: 약 686,000 rows/년
```

저장 부담은 크지 않으나 수집 시간이 부담입니다.

### 8.2 수집 전략

```text
방법 1: pykrx의 시가총액 일별 데이터 직접 호출
- 장점: 정확
- 단점: 종목별 × 날짜별 호출 → 시간 오래 걸림

방법 2: 종가 × 상장주식수 계산
- 장점: 빠름 (이미 일봉 데이터 보유)
- 단점: 상장주식수 시계열도 별도 수집 필요

권장: 방법 2를 기본, 정합성 검증용으로 방법 1을 표본 검증
```

### 8.3 인덱스

시가총액 상위 N종목 쿼리는 `(date, market_cap DESC)` 복합 인덱스가 필요합니다.

```sql
CREATE INDEX idx_daily_prices_date_market_cap
ON daily_prices (date, market_cap DESC);
```

---

## 9. 수정주가 계산

### 9.1 계산 방식

corporate_actions 발생 시점부터 과거 모든 가격을 역산합니다.

```text
액면분할 (1주 → N주):
adjustment_factor *= 1 / N
adj_price = price × adjustment_factor (분할 이전)

무상증자:
adj_price = price × (1 / (1 + 무상증자 비율))

배당 (현금):
adj_price = price × (1 - 배당금 / 권리락전 종가)

유상증자:
이론권리락 가격 기준 보정
```

### 9.2 계산 트리거

```text
1. 신규 corporate_action 수집 시
2. 수동 재계산 명령 시
3. 수정주가 검증 실패 시
```

전체 종목 수정주가 재계산은 비용이 크므로 영향받은 종목만 처리합니다.

---

## 10. 생존 편향 완화

### 10.1 MVP 정책

```text
1. 종목 마스터에 listing_date를 모두 채운다.
2. 백테스트 시작일 < listing_date인 종목은 그 시점 이후부터 유니버스에 편입한다.
3. delisting_date가 있는 종목도 백테스트 기간 안에서 유효한 동안만 편입한다.
4. 결과 화면에 생존 편향 영향 분석을 표시한다.
```

### 10.2 상장폐지 종목 처리

```text
정리매매 데이터 수집 (KIND):
- 상장폐지일
- 정리매매 마지막 종가

백테스트 중 상장폐지 발생:
- 정확성 정책 13.4.5 적용 (강제 매도)
```

### 10.3 결과 화면 표시

```text
주의:
이 백테스트 기간 동안 N개 종목이 신규 상장되었고, M개 종목이 상장폐지되었습니다.
상장폐지 종목 데이터를 보유하지 않은 경우 결과가 실제보다 좋게 보일 수 있습니다.
```

---

## 11. 캐시 / 저장 전략

### 11.1 단계별

```text
MVP (Phase 1):
- 모든 데이터를 SQLite에 저장
- 단일 파일 데이터베이스
- 약 10GB 이내 예상

웹 서비스 단계 (Phase 2):
- PostgreSQL로 마이그레이션
- 종목 마스터, 거래 결과 등 메타 데이터는 PostgreSQL
- 일봉 데이터는 그대로 또는 Parquet 분리

대용량 단계 (Phase 3):
- 일봉 데이터를 Parquet로 분리 저장 (날짜별 파티션)
- DB는 메타데이터만 보관
- DuckDB 또는 직접 pandas로 Parquet 조회
```

### 11.2 메모리 캐시

백테스트 실행 시 자주 조회되는 데이터:

```text
거래일 캘린더 → 메모리 상주
종목 마스터 → 메모리 상주
당일 사용 종목 일봉 → 백테스트 시작 시 일괄 로드
```

---

## 12. 백테스트 실행 시 데이터 로드

```text
1. 백테스트 설정 검증
2. 거래일 캘린더 로드
3. 유니버스 결정 (날짜별)
4. 필요 종목 일봉 일괄 로드
5. 수정주가 일관성 확인
6. 데이터 결손 종목 경고
7. 백테스트 시작
```

`PriceLoader`가 위 단계를 담당합니다.

```python
class PriceLoader:
    def load_for_backtest(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str,
    ) -> dict[str, pd.DataFrame]:
        ...
```

---

## 13. 데이터 결손 알림

```text
파이프라인 작업 후 자동 점검:
- 어제 일봉 수집 누락된 종목 수
- 거래일 캘린더 마지막 갱신일
- corporate_action 미반영 종목 수
- 수정주가 검증 실패 건수

알림 채널:
- 로그 파일 (필수)
- 콘솔 출력 (개발용)
- 이메일 / Slack (운영 시)
```

---

## 14. 거래일 캘린더 데이터 구조

```text
trading_calendar
├─ id
├─ date (PK)
├─ market (KOSPI, KOSDAQ)
├─ is_trading_day
└─ holiday_name
```

특수 단축 거래일도 별도 플래그로 관리할 수 있습니다.

---

## 15. corporate_actions 데이터 구조

```text
corporate_actions
├─ id
├─ symbol
├─ event_date
├─ event_type (split, reverse_split, bonus_issue, rights_issue, dividend, delisting)
├─ ratio                  (분할/병합 비율)
├─ dividend_amount        (배당금)
├─ price_before           (권리락 직전 종가)
├─ price_after            (권리락 직후 기준가)
├─ adjustment_factor
└─ source                 (KRX, KIND, manual)
```

---

## 16. 데이터 파이프라인 운영 체크리스트

### 16.1 일일 점검

```text
[ ] 어제 일봉 수집 성공
[ ] 휴장일 갱신 확인
[ ] 신규 상장 종목 마스터 갱신
[ ] 상장폐지 종목 마스터 갱신
[ ] corporate_actions 갱신
[ ] 수정주가 재계산 (필요 시)
[ ] 데이터 검증 통과
```

### 16.2 주간 점검

```text
[ ] 데이터 결손 종목 추적
[ ] 시가총액 정합성 표본 검증
[ ] 캐시 사용량 확인
```

---

## 17. MVP 범위

```text
1. pykrx 기반 종목 마스터 / 일봉 수집
2. 거래일 캘린더 수집
3. 기본 데이터 검증
4. 수동 백필 스크립트
5. 일일 증분 수집 cron 또는 수동 실행
6. SQLite 저장
7. 결손 종목 콘솔 알림
```

향후 단계:

```text
시가총액 시계열 자동 계산
수정주가 자동 계산
corporate_actions 자동 적용
다중 provider fallback
스케줄러 자동화
PostgreSQL / Parquet 마이그레이션
```

---

## 18. 테스트 항목

```text
종목 마스터 수집 결과
거래일 캘린더 수집 결과
일봉 수집 결과
OHLC 정합성 검증
거래량 정합성 검증
수정주가 계산 정확성
시가총액 계산 정확성
재시도 로직
fallback provider 전환
결손 종목 감지
```
