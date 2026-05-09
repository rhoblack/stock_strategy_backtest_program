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

필요 필드 (정확성 정책 13.7절에 따라 수정주가 필드를 모두 보유):

```text
symbol
date
open, high, low, close                  : 원 가격
adj_open, adj_high, adj_low, adj_close  : 수정 가격
volume                                  : 원 거래량
adj_volume                              : 수정 거래량
trading_value                           : 거래대금 (원 가격 기준)
market_cap                              : 시가총액
adjustment_factor                       : 누적 수정 계수
```

MVP 필수:

```text
open, high, low, close
adj_open, adj_high, adj_low, adj_close
volume, adj_volume
trading_value
market_cap
```

가격 기반 조건과 백테스트 체결은 기본적으로 `adj_*`를 사용합니다. 거래대금 필터는 원 가격 기준 `trading_value`를 사용합니다 (실제 시장 유동성 반영).

시가총액 상위 N종목 기능을 위해 `market_cap`이 필요합니다. 시가총액 시계열 수집 전략은 14 데이터 파이프라인 8절을 참조합니다.

---

## 8. UniverseSelector

종목군 선택을 담당합니다. 모든 선택 결과에 listing_date / delisting_date 필터를 추가 적용해 생존편향을 완화합니다 (11.1절).

```python
class UniverseSelector:
    def __init__(self, provider, symbol_master):
        self.provider = provider
        self.symbol_master = symbol_master

    def select(self, universe_config: dict, date: str) -> list[str]:
        method = universe_config["selection_method"]

        if method == "all":
            symbols = self._select_all(universe_config)
        elif method == "market_cap_top_n":
            symbols = self._select_market_cap_top_n(universe_config, date)
        elif method == "trading_value_top_n":
            symbols = self._select_trading_value_top_n(universe_config, date)
        elif method == "manual":
            symbols = universe_config["symbols"]
        elif method == "watchlist":
            symbols = universe_config["symbols"]
        else:
            raise ValueError(f"지원하지 않는 유니버스 선택 방식입니다: {method}")

        # 공통 필터: 상장일/상장폐지일/제외 옵션
        return self._apply_common_filters(symbols, date, universe_config)

    def _apply_common_filters(self, symbols, date, config):
        min_listing_age_days = config.get("min_listing_age_days", 60)
        result = []
        for s in symbols:
            meta = self.symbol_master[s]
            if meta.listing_date is None or (date - meta.listing_date).days < min_listing_age_days:
                continue
            if meta.delisting_date is not None and date >= meta.delisting_date:
                continue
            if config.get("exclude_etf") and meta.is_etf:
                continue
            if config.get("exclude_etn") and meta.is_etn:
                continue
            if config.get("exclude_spac") and meta.is_spac:
                continue
            if config.get("exclude_preferred") and meta.is_preferred:
                continue
            if config.get("exclude_managed") and meta.is_managed:
                continue
            if config.get("exclude_halted") and meta.is_halted:
                continue
            result.append(s)
        return sorted(result)  # 결정론을 위해 항상 정렬
```

`sorted()`로 종목코드 오름차순 결과를 보장합니다 (정확성 정책 13.12).

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

## 11. 생존 편향 완화

### 11.1 MVP 정책 (강화)

기존 "경고만 표시" 정책에서 다음으로 강화합니다 (정확성 정책 + 14 데이터 파이프라인 10절).

```text
1. 종목 마스터에 listing_date를 모두 채운다.
2. 백테스트 시작일 < listing_date인 종목은 listing_date 이후부터만 유니버스에 편입.
3. delisting_date가 있는 종목은 백테스트 기간 안에서 유효한 동안만 편입.
4. 상장 후 N일 미만 종목 제외 옵션 (기본 60일 권장).
5. 결과 화면에 영향 분석을 표시.
```

### 11.2 결과 화면 영향 분석

```text
이 백테스트 기간 동안:
- 신규 상장: N개 종목
- 상장폐지: M개 종목
- 상장폐지 데이터를 보유하지 않은 경우 결과가 실제보다 좋게 보일 수 있습니다.
```

### 11.3 상장폐지 종목 처리

상장폐지 데이터가 있으면:
```text
정리매매 마지막 종가에 강제 매도
exit_reason = "delisting"
```

상장폐지 데이터가 없으면 (MVP 초기):
```text
직전 거래일 종가 × 0.5로 강제 매도 (보수적 추정)
exit_reason = "delisting_estimated"
```

### 11.4 고급 확장

```text
일자별 정확한 유니버스 (날짜별 상장 종목 마스터)
관리종목/거래정지 이력 시계열 반영
업종 변경 이력 반영
상장폐지 종목의 정리매매 데이터 통합
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

상세 데이터 파이프라인 설계는 14 문서를 참조합니다.

MVP:

```text
pykrx 또는 LocalCsvProvider로 데이터 수집
SQLite daily_prices에 저장
거래일 캘린더, 종목 마스터는 메모리 상주
백테스트 시작 시 필요 종목 일봉 일괄 로드
```

v2:

```text
PostgreSQL로 마이그레이션
일별 증분 수집 cron화
수정주가 자동 재계산
```

v3:

```text
Parquet 파일로 대용량 시세 저장 (날짜별 파티션)
DB에는 메타데이터만 보관
DuckDB 또는 pandas로 Parquet 조회
```

데이터 결손, 재시도, KRX 차단 대응 등 운영 정책은 14 데이터 파이프라인 6/7절을 참조합니다.

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
