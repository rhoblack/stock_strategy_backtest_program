"""시장데이터 인프라 모듈.

본 패키지는 시장 데이터(종목 마스터, 일봉, 거래일 캘린더)의 저장/조회/공급을 담당한다.

1단계 (현재): DB 모델 + 마이그레이션 + repositories CRUD 스켈레톤.
2단계 (예정): LocalCsvProvider / PriceLoader / UniverseSelector.
3단계 (예정): PykrxProvider / data_pipeline (collectors / processors / jobs).

타 모듈 사용법:
    from app.market_data import repositories
    repositories.list_symbols(session, market="KOSPI", as_of_date=date(2024, 1, 1))
"""

from app.market_data import repositories

__all__ = ["repositories"]
