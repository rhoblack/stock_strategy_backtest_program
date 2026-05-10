"""UniverseSelector 단위 테스트.

검증 매핑:
    - 06번 §8 공통 필터 (exclude_etf / etn / spac / preferred / managed / halted +
      min_market_cap + min_avg_trading_value)
    - 06번 §9 selection_method (ALL / MARKET_CAP_TOP_N / LIQUIDITY_TOP_N)
    - 06번 §11 (생존편향 — 폐지/미래 상장 종목 처리, 016 위임)
    - 13번 §13.13 (생존편향 — 폐지 종목 시점별 필터)
    - 13번 §13.15 (look-ahead bias 차단 — 시가총액/거래대금 평균 시점)
    - 13번 §13.12 (결정론 — symbol ASC tie-breaker, 5회 반복 동일성)
    - 14번 §10 (생존편향 보존 — 폐지 종목 row 보존)
    - 14번 §10 결손 정책 (forward-fill 금지)

fixture는 `backend/tests/market_data/fixtures/csv/universe_test/`를 사용한다
(LocalCsvProvider로 적재 — 외부 fetch 0건, 합성 데이터만).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.market_data.local_csv import LocalCsvProvider
from app.market_data.universe import (
    DEFAULT_EXCLUDE_FLAGS,
    SELECTION_METHOD_ALL,
    SELECTION_METHOD_LIQUIDITY_TOP_N,
    SELECTION_METHOD_MARKET_CAP_TOP_N,
    SUPPORTED_SELECTION_METHODS,
    UniverseSelectionResult,
    UniverseSelector,
)

FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "csv" / "universe_test"
)
AS_OF_DATE = date(2024, 1, 8)
DELISTED_DATE = date(2024, 1, 4)
FUTURE_LISTED_DATE = date(2024, 1, 9)


@pytest.fixture
def loaded_session(db_session):
    """universe_test fixture를 적재한 세션."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT)
    provider.ingest_into(db_session)
    db_session.commit()
    return db_session


@pytest.fixture
def selector(loaded_session) -> UniverseSelector:
    return UniverseSelector(loaded_session)


# --------------------------------------------------------------------------
# A) 기본 ALL — 공통 필터 default 적용
# --------------------------------------------------------------------------


def test_select_all_with_default_excludes(selector):
    """ALL + default exclude_*: 6개 일반 + 폐지(2024-01-08 기준 활성) → 5개 일반.

    fixture 기준 KOSPI 종목 (000040 코스닥 제외):
        - 000001~000005: 일반 (5개)
        - 000010 ETF / 000011 ETN / 000012 SPAC / 000013 우선주 / 000014 관리 / 000015 거래정지 → 모두 default로 제외
        - 000020 폐지 (2024-01-04 폐지 → as_of=2024-01-08은 이미 폐지) → 016 동적 필터에서 제외
        - 000030 미래 상장 (2024-01-09) → 016 동적 필터에서 제외
    """
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == ["000001", "000002", "000003", "000004", "000005"]


def test_select_returns_symbol_objects(selector):
    """반환은 Symbol ORM 객체 리스트."""
    result = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=AS_OF_DATE,
    )
    assert all(hasattr(s, "symbol") and hasattr(s, "market") for s in result)
    assert {s.market for s in result} == {"KOSPI"}


def test_select_with_details_returns_excluded_counts(selector):
    """select_with_details: UniverseSelectionResult — symbols + excluded_counts + 메타."""
    detail = selector.select_with_details(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=AS_OF_DATE,
    )
    assert isinstance(detail, UniverseSelectionResult)
    assert detail.market == "KOSPI"
    assert detail.as_of_date == AS_OF_DATE
    assert detail.selection_method == SELECTION_METHOD_ALL
    assert detail.count == 5
    # 6개 플래그 + min_market_cap + min_avg_trading_value + selection_method
    for key in (
        "exclude_etf",
        "exclude_etn",
        "exclude_spac",
        "exclude_preferred",
        "exclude_managed",
        "exclude_halted",
        "min_market_cap",
        "min_avg_trading_value",
        "selection_method",
    ):
        assert key in detail.excluded_counts


# --------------------------------------------------------------------------
# B) 13.13 / 13.15 / 14.10 — 생존편향 + look-ahead
# --------------------------------------------------------------------------


def test_delisted_symbol_included_before_delisting_date(selector):
    """13.13 폐지 종목 보존: 폐지 이전 시점은 universe에 포함된다."""
    result = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=date(2024, 1, 3),  # 000020 폐지(2024-01-04) 이전
    )
    codes = [s.symbol for s in result]
    assert "000020" in codes


def test_delisted_symbol_excluded_after_delisting_date(selector):
    """13.13 폐지 종목: 폐지 이후 시점은 universe에서 제외 (016 동적 필터)."""
    result = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=date(2024, 1, 5),  # 폐지 후
    )
    codes = [s.symbol for s in result]
    assert "000020" not in codes


def test_future_listed_symbol_excluded(selector):
    """13.15 look-ahead: 미래 상장 종목은 현 시점 universe에서 제외."""
    result = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=AS_OF_DATE,  # 000030 상장(2024-01-09) 이전
    )
    codes = [s.symbol for s in result]
    assert "000030" not in codes


def test_future_listed_symbol_included_after_listing(selector):
    """000030이 2024-01-09 상장 이후는 universe에 포함."""
    result = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=date(2024, 1, 9),
    )
    codes = [s.symbol for s in result]
    assert "000030" in codes


# --------------------------------------------------------------------------
# C) 06번 §8 — 종목 마스터 플래그 필터
# --------------------------------------------------------------------------


def test_exclude_etf_default_true(selector):
    """default exclude_etf=True: ETF는 제외."""
    result = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert "000010" not in codes


def test_exclude_etf_false_includes_etf(selector):
    """exclude_etf=False: ETF 포함."""
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "exclude_etf": False,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert "000010" in codes


def test_exclude_etn_toggle(selector):
    """exclude_etn=False: ETN 포함."""
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "exclude_etn": False,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert "000011" in codes


def test_exclude_spac_toggle(selector):
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "exclude_spac": False,
        },
        as_of_date=AS_OF_DATE,
    )
    assert "000012" in [s.symbol for s in result]


def test_exclude_preferred_toggle(selector):
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "exclude_preferred": False,
        },
        as_of_date=AS_OF_DATE,
    )
    assert "000013" in [s.symbol for s in result]


def test_exclude_managed_toggle(selector):
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "exclude_managed": False,
        },
        as_of_date=AS_OF_DATE,
    )
    assert "000014" in [s.symbol for s in result]


def test_exclude_halted_toggle(selector):
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "exclude_halted": False,
        },
        as_of_date=AS_OF_DATE,
    )
    assert "000015" in [s.symbol for s in result]


def test_market_kosdaq_returns_only_kosdaq_symbols(selector):
    """market=KOSDAQ: 코스닥 종목만 (000040)."""
    result = selector.select(
        config={"market": "KOSDAQ", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == ["000040"]


# --------------------------------------------------------------------------
# D) 06번 §8 — min_market_cap (시가총액 필터)
# --------------------------------------------------------------------------


def test_min_market_cap_filter_includes_above_threshold(selector):
    """min_market_cap=300_000_000_000 (3000억): 1조 이상 통과.

    as_of=2024-01-08 시가총액:
        - 000001: 1.04조  → 통과
        - 000002: 5200억 → 통과 (>3000억)
        - 000003: 3.04조  → 통과
        - 000004: 2040억 → 제외 (<3000억)
        - 000005: NULL   → 제외 (보수)
    """
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "min_market_cap": 300_000_000_000,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == ["000001", "000002", "000003"]


def test_min_market_cap_filter_excludes_missing_market_cap(selector):
    """000005는 market_cap이 모두 NULL → min_market_cap 필터 시 제외."""
    detail = selector.select_with_details(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "min_market_cap": 1,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in detail.symbols]
    assert "000005" not in codes
    # 결손 1건 + 임계값 미만 0건 = 1건 제외
    assert detail.excluded_counts["min_market_cap"] >= 1


def test_min_market_cap_zero_threshold_keeps_all_with_market_cap(selector):
    """min_market_cap=0이면 market_cap이 있는 모든 종목 통과 (000005만 제외)."""
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "min_market_cap": 0,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == ["000001", "000002", "000003", "000004"]
    assert "000005" not in codes


# --------------------------------------------------------------------------
# E) 13.15 look-ahead — 시가총액 미래 데이터 차단
# --------------------------------------------------------------------------


def test_min_market_cap_does_not_use_future_data(selector):
    """13.15: as_of_date 이후 데이터(2024-01-09 시가총액=99조)를 사용하지 않는다.

    000001의 2024-01-09 market_cap=99,999,999,999,999 (99조)지만 as_of=2024-01-08 기준
    조회는 2024-01-08의 1.04조만 사용해야 함. 임계값 50조로 두면 000001 제외돼야 함.
    """
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "min_market_cap": 50_000_000_000_000,  # 50조
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    # 어떤 종목도 50조 이상이 아니므로 빈 결과
    assert codes == []


# --------------------------------------------------------------------------
# F) 06번 §8 — min_avg_trading_value (거래대금 평균 N일)
# --------------------------------------------------------------------------


def test_min_avg_trading_value_filter(selector):
    """거래대금 평균 N일(default 20) 필터.

    as_of=2024-01-08 직전 거래일 1/2~1/5 (4건) 평균:
        - 000001: 11,685,000,000  → 통과 (>10B)
        - 000002: 10,682,000,000  → 통과 (>10B)
        - 000003:  9,498,500,000  → 제외 (<10B)
        - 000004:  8,633,500,000  → 제외 (<10B)
        - 000005:  근사값 = (50000*100000+50000*110000+50100*120000+50100*130000)/4
                  = (5000000000+5500000000+6012000000+6513000000)/4 = 5,756,250,000 → 제외
    """
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "min_avg_trading_value": 10_000_000_000,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == ["000001", "000002"]


def test_min_avg_trading_value_excludes_when_no_history(selector):
    """as_of_date 직전에 거래 이력 없는 종목은 제외."""
    # 000030은 미래 상장이라 universe에 들어오지 않음 → 다른 케이스 필요.
    # as_of=2024-01-02로 두면 000001 등도 직전 거래일 없음 → 모두 제외돼야 함.
    detail = selector.select_with_details(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "min_avg_trading_value": 1,
        },
        as_of_date=date(2024, 1, 2),
    )
    # 직전(2024-01-01 이전)에는 데이터 없음 → 모두 제외
    assert detail.symbols == []
    assert detail.excluded_counts["min_avg_trading_value"] >= 1


# --------------------------------------------------------------------------
# G) 13.15 look-ahead — 거래대금 평균은 당일 미포함
# --------------------------------------------------------------------------


def test_avg_trading_value_excludes_as_of_date_itself(selector):
    """13.15: 거래대금 평균은 as_of_date 직전(당일 미포함).

    000001은 as_of=2024-01-08 당일 close*volume = 10400 * 1400000 = 14,560,000,000.
    당일 포함 평균은 (4 직전 + 14.56B)/5 = (46.74B + 14.56B)/5 = 12.26B.
    당일 미포함 평균은 46.74B / 4 = 11.685B.

    임계값 12B로 설정:
        - 당일 포함하면 통과 (12.26B > 12B)
        - 당일 미포함 (정책)하면 제외 (11.685B < 12B)
    """
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "min_avg_trading_value": 12_000_000_000,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert "000001" not in codes


# --------------------------------------------------------------------------
# H) 결정론 (CLAUDE.md #8 / 13.12)
# --------------------------------------------------------------------------


def test_select_deterministic_across_repeat(selector):
    """5회 반복 호출 시 동일 결과."""
    config = {
        "market": "KOSPI",
        "selection_method": SELECTION_METHOD_ALL,
        "exclude_etf": False,
        "exclude_etn": False,
    }
    runs = []
    for _ in range(5):
        result = selector.select(config=config, as_of_date=AS_OF_DATE)
        runs.append(tuple(s.symbol for s in result))
    assert len({tuple(r) for r in runs}) == 1


def test_select_sorted_by_symbol_asc(selector):
    """결과는 symbol ASC (13.12)."""
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
            "exclude_etf": False,
            "exclude_etn": False,
            "exclude_spac": False,
            "exclude_preferred": False,
            "exclude_managed": False,
            "exclude_halted": False,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == sorted(codes)


# --------------------------------------------------------------------------
# I) selection_method — MARKET_CAP_TOP_N (부분 구현 — 016 daily_prices.market_cap 사용)
# --------------------------------------------------------------------------


def test_market_cap_top_n_returns_top_n_by_market_cap(selector):
    """MARKET_CAP_TOP_N: as_of=2024-01-08 시가총액 상위 2개.

    000003: 3.04조 → 1위
    000001: 1.04조 → 2위
    000002: 5200억 → 3위 (제외)
    000004: 2040억 → 4위 (제외)
    000005: NULL → 결손 (제외)
    """
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_MARKET_CAP_TOP_N,
            "top_n": 2,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == ["000001", "000003"]
    # 결정론: select_with_details로 봐도 동일
    detail = selector.select_with_details(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_MARKET_CAP_TOP_N,
            "top_n": 2,
        },
        as_of_date=AS_OF_DATE,
    )
    assert [s.symbol for s in detail.symbols] == ["000001", "000003"]


def test_market_cap_top_n_skips_missing_market_cap(selector):
    """시가총액 결손 종목(000005)은 MARKET_CAP_TOP_N 정렬 대상에서 제외."""
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_MARKET_CAP_TOP_N,
            "top_n": 100,  # 무제한처럼
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert "000005" not in codes


def test_market_cap_top_n_requires_top_n(selector):
    """top_n 키 누락 시 ValueError."""
    with pytest.raises(ValueError, match="top_n"):
        selector.select(
            config={
                "market": "KOSPI",
                "selection_method": SELECTION_METHOD_MARKET_CAP_TOP_N,
            },
            as_of_date=AS_OF_DATE,
        )


def test_market_cap_top_n_does_not_use_future_data(selector):
    """13.15: top_n 선정도 미래 시가총액(2024-01-09의 99조) 무시.

    만약 미래 데이터를 본다면 000001이 99조로 1위가 되겠지만,
    as_of=2024-01-08 기준 정상은 000003(3.04조)이 1위.
    """
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_MARKET_CAP_TOP_N,
            "top_n": 1,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == ["000003"]


# --------------------------------------------------------------------------
# J) selection_method — LIQUIDITY_TOP_N (부분 구현)
# --------------------------------------------------------------------------


def test_liquidity_top_n_returns_top_n_by_avg_trading_value(selector):
    """LIQUIDITY_TOP_N: as_of=2024-01-08 직전 거래대금 평균 상위 2개.

    예상 평균 (as_of_date 미포함, 1/2~1/5):
        - 000001: 11.685B
        - 000002: 10.682B
        - 000003:  9.499B
        - 000004:  8.634B
        - 000005:  5.756B
    상위 2 → 000001, 000002 (symbol ASC)
    """
    result = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_LIQUIDITY_TOP_N,
            "top_n": 2,
        },
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in result]
    assert codes == ["000001", "000002"]


def test_liquidity_top_n_requires_top_n(selector):
    with pytest.raises(ValueError, match="top_n"):
        selector.select(
            config={
                "market": "KOSPI",
                "selection_method": SELECTION_METHOD_LIQUIDITY_TOP_N,
            },
            as_of_date=AS_OF_DATE,
        )


# --------------------------------------------------------------------------
# K) 에러 처리
# --------------------------------------------------------------------------


def test_missing_market_raises(selector):
    """market 키 누락 시 ValueError."""
    with pytest.raises(ValueError, match="market"):
        selector.select(
            config={"selection_method": SELECTION_METHOD_ALL},
            as_of_date=AS_OF_DATE,
        )


def test_unsupported_selection_method_raises(selector):
    """미지원 selection_method는 ValueError (silent skip 금지)."""
    with pytest.raises(ValueError, match="selection_method"):
        selector.select(
            config={"market": "KOSPI", "selection_method": "MANUAL"},
            as_of_date=AS_OF_DATE,
        )


def test_default_exclude_flags_constants():
    """DEFAULT_EXCLUDE_FLAGS는 6개 플래그 모두 True."""
    assert set(DEFAULT_EXCLUDE_FLAGS) == {
        "exclude_etf",
        "exclude_etn",
        "exclude_spac",
        "exclude_preferred",
        "exclude_managed",
        "exclude_halted",
    }
    assert all(v is True for v in DEFAULT_EXCLUDE_FLAGS.values())


def test_supported_selection_methods_constants():
    """SUPPORTED_SELECTION_METHODS는 ALL / MARKET_CAP_TOP_N / LIQUIDITY_TOP_N."""
    assert set(SUPPORTED_SELECTION_METHODS) == {
        SELECTION_METHOD_ALL,
        SELECTION_METHOD_MARKET_CAP_TOP_N,
        SELECTION_METHOD_LIQUIDITY_TOP_N,
    }
    assert isinstance(SUPPORTED_SELECTION_METHODS, frozenset)


# --------------------------------------------------------------------------
# L) 영향 분석 — 폐지 종목 시점 차이 (생존편향 회귀)
# --------------------------------------------------------------------------


def test_universe_changes_across_dates_due_to_delisting(selector):
    """동일 config로 시점만 바꾸면 폐지 시점 전후로 universe가 다르다 (생존편향 회피 증명).

    2024-01-03: 000020 활성 → universe에 포함
    2024-01-08: 000020 폐지 (2024-01-04) → universe에서 제외
    """
    config = {"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL}
    before = selector.select(config=config, as_of_date=date(2024, 1, 3))
    after = selector.select(config=config, as_of_date=date(2024, 1, 8))
    before_codes = {s.symbol for s in before}
    after_codes = {s.symbol for s in after}
    assert "000020" in before_codes
    assert "000020" not in after_codes
