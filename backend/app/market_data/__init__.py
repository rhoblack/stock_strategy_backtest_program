"""시장데이터 인프라 모듈.

본 패키지는 시장 데이터(종목 마스터, 일봉, 거래일 캘린더)의 저장/조회/공급을 담당한다.

1단계 (016): DB 모델 + 마이그레이션 + repositories CRUD 스켈레톤.
2단계 (018): BaseProvider + LocalCsvProvider + PriceLoader.
3단계 (019, 현재): UniverseSelector (06번 §8 공통 필터 + 06번 §9 selection_method).
4단계 (Phase 11 예정): PykrxProvider / data_pipeline (collectors / processors / jobs).

타 모듈 사용법:
    from app.market_data import repositories
    repositories.list_symbols(session, market="KOSPI", as_of_date=date(2024, 1, 1))

    from app.market_data.local_csv import LocalCsvProvider
    LocalCsvProvider(root="data/sample").ingest_into(session)

    from app.market_data.price_loader import PriceLoader
    df = PriceLoader(session).load("005930", start_date, end_date)
    backtest_engine.run(df)

    from app.market_data.universe import UniverseSelector
    symbols = UniverseSelector(session).select(
        config={"market": "KOSPI", "selection_method": "ALL"},
        as_of_date=date(2024, 1, 8),
    )
"""

from app.market_data import repositories

__all__ = ["repositories"]
