# 06. 시장 데이터 및 종목군 유니버스 상세 설계서

## 1. 목적

시장 데이터 및 유니버스 모듈은 백테스트 대상 종목과 시세 데이터를 공급합니다.

이 모듈은 다음을 담당합니다.

```text
코스피/코스닥 종목 목록 수집
일봉 OHLCV 데이터 로드
거래대금, 시가총액 데이터 로드
시가총액 상위 N종목 선정
관심종목/직접선택 종목군 생성
백테스트 날짜별 유니버스 구성
```

---

## 2. 핵심 설계 원칙

```text
백테스트 엔진은 데이터 공급자를 직접 알면 안 된다.
MarketDataProvider 인터페이스를 통해 데이터를 요청한다.
데이터 공급원은 교체 가능해야 한다.
유니버스 선택은 UniverseSelector가 담당한다.
MVP는 현재 상장 종목 기준으로 시작하되, 향후 날짜별 유니버스로 확장한다.
```

---

## 3. 주요 모듈

```text
market_data/
├─ provider.py
├─ krx_provider.py
├─ cache.py
├─ universe.py
└─ price_loader.py
```

역할:

```text
provider.py:
공통 데이터 인터페이스

krx_provider.py:
한국 주식 데이터 공급자

cache.py:
시세 데이터 캐시

universe.py:
종목군 선택 로직

price_loader.py:
백테스트용 가격 데이터 로드
```

---

## 4. MarketDataProvider 인터페이스

```python
from abc import ABC, abstractmethod
import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    def get_symbols(self, market: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_daily_prices(self, symbols: list[str], start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
        pass

    @abstractmethod
    def get_market_cap(self, date: str, market: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_trading_value_rank(self, date: str, market: str) -> pd.DataFrame:
        pass
```

---

## 5. 데이터 공급자 종류

향후 교체 가능하도록 여러 provider를 둘 수 있습니다.

```text
KRXProvider
PublicDataProvider
PykrxProvider
FinanceDataReaderProvider
LocalCsvProvider
ParquetProvider
BrokerApiProvider
```

MVP에서는 `LocalCsvProvider` 또는 `PykrxProvider`로 시작할 수 있습니다.

---

## 6. 종목 마스터 데이터

필요 필드:

```text
symbol
name
market
sector
listing_date
delisting_date
is_etf
is_etn
is_spac
is_preferred
is_active
is_managed
is_halted
```

시장 구분:

```text
KOSPI
KOSDAQ
KONEX
```

MVP에서는 KOSPI, KOSDAQ만 우선 지원합니다.

---

## 7. 일봉 데이터

필요 필드:

```text
symbol
date
open
high
low
close
volume
trading_value
adjusted_close
market_cap
```

MVP 필수:

```text
open
high
low
close
volume
trading_value
```

시가총액 상위 N종목 기능을 위해 `market_cap`이 필요합니다.

---

## 8. UniverseSelector

종목군 선택을 담당합니다.

```python
class UniverseSelector:
    def __init__(self, provider):
        self.provider = provider

    def select(self, universe_config: dict, date: str) -> list[str]:
        method = universe_config["selection_method"]

        if method == "all":
            return self._select_all(universe_config)

        if method == "market_cap_top_n":
            return self._select_market_cap_top_n(universe_config, date)

        if method == "trading_value_top_n":
            return self._select_trading_value_top_n(universe_config, date)

        if method == "manual":
            return universe_config["symbols"]

        if method == "watchlist":
            return universe_config["symbols"]

        raise ValueError(f"지원하지 않는 유니버스 선택 방식입니다: {method}")
```

---

## 9. 지원 유니버스

```text
all:
코스피 전체, 코스닥 전체, 코스피+코스닥 전체

manual:
사용자가 직접 종목 선택

watchlist:
저장된 관심종목

market_cap_top_n:
시가총액 상위 N종목

trading_value_top_n:
거래대금 상위 N종목
```

---

## 10. 시가총액 상위 N종목

설정 예시:

```json
{
  "market": "KOSPI",
  "selection_method": "market_cap_top_n",
  "top_n": 10,
  "selection_timing": "backtest_start_date",
  "rebalance_frequency": "none"
}
```

지원 방식:

```text
current:
현재 기준 상위 N종목

backtest_start_date:
백테스트 시작일 기준 상위 N종목

periodic:
월별/분기별/연별 재선정
```

MVP:

```text
현재 기준 상위 N종목
백테스트 시작일 기준 상위 N종목
```

향후:

```text
매월 재선정
매분기 재선정
매년 재선정
```

---

## 11. 생존 편향 관리

주의할 점:

```text
현재 상장 종목만으로 과거 백테스트를 하면 상장폐지 종목이 제외되어 결과가 좋아 보일 수 있다.
```

MVP에서는 현재 상장 종목 기준으로 시작하되 경고를 표시합니다.

```text
주의:
현재 상장 종목 기준 백테스트입니다.
상장폐지 종목이 제외되어 결과가 실제보다 좋게 보일 수 있습니다.
```

고급 버전에서는 다음을 지원합니다.

```text
상장일/상장폐지일 반영
날짜별 유니버스
관리종목 이력
거래정지 이력
상장 후 N일 미만 제외
```

---

## 12. 기본 제외 옵션

백테스트 실행 화면에서 제공할 필터:

```text
ETF 제외
ETN 제외
스팩 제외
우선주 제외
관리종목 제외
거래정지 종목 제외
정리매매 종목 제외
```

실전 가능성 필터:

```text
20일 평균 거래대금 N억 이상
상장 후 N일 이상
종가 N원 이상
시가총액 N억 이상
```

---

## 13. 유니버스 Preview API

백테스트 실행 전 대상 종목을 미리 보여줍니다.

```text
POST /api/market/universe/preview
```

요청 예시:

```json
{
  "market": "KOSPI",
  "selection_method": "market_cap_top_n",
  "top_n": 10,
  "selection_timing": "backtest_start_date",
  "date": "2020-01-02"
}
```

응답 예시:

```json
{
  "count": 10,
  "symbols": [
    {
      "rank": 1,
      "symbol": "005930",
      "name": "삼성전자",
      "market_cap": 300000000000000
    }
  ]
}
```

---

## 14. universe_history

시가총액 상위 N종목처럼 시간이 지나며 유니버스가 바뀌는 경우 이력을 저장합니다.

필드:

```text
run_id
date
market
rank
symbol
name
market_cap
selection_method
```

CSV Export:

```text
universe_history.csv
```

---

## 15. 캐시 전략

MVP:

```text
외부 API 또는 CSV에서 데이터 로드
필요시 메모리 캐시
```

v2:

```text
DB daily_prices에 일봉 저장
```

v3:

```text
Parquet 파일로 대용량 시세 저장
DB에는 메타데이터 저장
```

---

## 16. 테스트 항목

```text
코스피 전체 종목 목록 로드
코스닥 전체 종목 목록 로드
ETF/ETN/스팩 제외 필터
시가총액 상위 N종목 선정
거래대금 상위 N종목 선정
유니버스 Preview 결과
백테스트 시작일 기준 유니버스 선정
상장일 이후 종목만 포함
거래정지 종목 제외
```
