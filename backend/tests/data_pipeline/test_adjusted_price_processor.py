"""AdjustedPriceProcessor 단위 테스트 (14번 §9 / 13번 §7).

검증 항목:
    - 1:N 액면분할 → 분할 이전 가격 1/N, 거래량 N배
    - 액면병합 → 반대 방향
    - 무상증자 → 1/(1+N) 가격, (1+N) 거래량
    - 현금 배당 → (1 - 배당금/price_before) 가격, 거래량 보존
    - 미래 이벤트 → look-ahead 차단 (skip)
    - 음수 ratio / 누락 dividend_amount → HARD (raise)
    - 미지원 이벤트 (rights/merger/spinoff) → SOFT skip
    - close 보존 (원 가격 변경 0)
    - corporate_actions 없는 종목 → 입력 그대로 통과
    - 결정론: 5회 반복 동일 출력
    - 시간 역순 누적: 분할 + 배당 동시 → 두 factor 모두 적용
    - cash_dividend price_before 결손 → SOFT skip
    - 결과 정렬 (symbol ASC, date ASC)
    - validation 실패 시 raise_on_hard_fail=False 동작
"""

from __future__ import annotations

from datetime import date

import pytest

from app.data_pipeline.collectors.base import RawDailyPriceRow, RawDailyPricesData
from app.data_pipeline.exceptions import DataValidationError
from app.data_pipeline.processors.adjusted_price import (
    AdjustedPriceInput,
    AdjustedPriceProcessor,
    CorporateActionEvent,
)

# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------


def _row(symbol="005930", d=date(2024, 1, 2), price=100.0, vol=1000.0):
    return RawDailyPriceRow(
        symbol=symbol,
        date=d,
        open=price,
        high=price * 1.02,
        low=price * 0.98,
        close=price,
        volume=vol,
        adj_open=price,
        adj_high=price * 1.02,
        adj_low=price * 0.98,
        adj_close=price,
        adj_volume=vol,
        market_cap=price * vol,
    )


def _prices(rows, start=date(2024, 1, 2), end=date(2024, 12, 31)):
    return RawDailyPricesData(
        rows=tuple(rows),
        start_date=start,
        end_date=end,
        source="test",
    )


# ---------------------------------------------------------------------------
# 1) 액면분할
# ---------------------------------------------------------------------------


def test_split_halves_pre_event_prices_and_doubles_volume():
    """1:2 분할 (ratio=2.0) — 분할 이전 가격 ×0.5, 거래량 ×2."""
    rows = [
        _row(d=date(2024, 1, 2), price=200.0, vol=1000.0),
        _row(d=date(2024, 1, 3), price=210.0, vol=1100.0),
        _row(d=date(2024, 5, 1), price=110.0, vol=2000.0),  # 권리락 당일
        _row(d=date(2024, 5, 2), price=115.0, vol=2100.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="split",
            ratio=2.0,
        ),
    )

    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))

    output = result.output
    # close 원 가격은 모두 보존
    assert [r.close for r in output] == [200.0, 210.0, 110.0, 115.0]
    # 분할 이전 (5/1 미만) adj_close는 ×0.5, 5/1 당일 이후는 변경 없음
    assert output[0].adj_close == pytest.approx(100.0)
    assert output[1].adj_close == pytest.approx(105.0)
    assert output[2].adj_close == pytest.approx(110.0)
    assert output[3].adj_close == pytest.approx(115.0)
    # 분할 이전 adj_volume은 ×2.0
    assert output[0].adj_volume == pytest.approx(2000.0)
    assert output[1].adj_volume == pytest.approx(2200.0)
    assert output[2].adj_volume == pytest.approx(2000.0)
    # 원 volume은 보존
    assert [r.volume for r in output] == [1000.0, 1100.0, 2000.0, 2100.0]


def test_reverse_split_doubles_pre_event_prices():
    rows = [
        _row(d=date(2024, 1, 2), price=100.0, vol=1000.0),
        _row(d=date(2024, 5, 1), price=200.0, vol=500.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="reverse_split",
            ratio=2.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))
    assert result.output[0].adj_close == pytest.approx(200.0)  # × ratio
    assert result.output[1].adj_close == pytest.approx(200.0)  # 변경 없음
    assert result.output[0].adj_volume == pytest.approx(500.0)  # × 1/ratio


# ---------------------------------------------------------------------------
# 2) 무상증자
# ---------------------------------------------------------------------------


def test_bonus_issue_adjusts_prices_correctly():
    """보유 1주당 1주 무상증자 (ratio=1.0) — 가격 ×1/2, 거래량 ×2."""
    rows = [
        _row(d=date(2024, 1, 2), price=200.0, vol=1000.0),
        _row(d=date(2024, 5, 1), price=100.0, vol=2000.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="bonus_issue",
            ratio=1.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))
    assert result.output[0].adj_close == pytest.approx(100.0)
    assert result.output[1].adj_close == pytest.approx(100.0)
    assert result.output[0].adj_volume == pytest.approx(2000.0)
    assert result.output[1].adj_volume == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# 3) 현금 배당
# ---------------------------------------------------------------------------


def test_cash_dividend_applies_factor_from_price_before():
    """현금배당 1000원, 권리락전 종가 10000원 → factor = 1 - 0.1 = 0.9."""
    rows = [
        _row(d=date(2024, 1, 2), price=10000.0, vol=1000.0),
        _row(d=date(2024, 4, 30), price=10000.0, vol=1000.0),  # 권리락 직전 (price_before)
        _row(d=date(2024, 5, 1), price=9000.0, vol=1000.0),     # 권리락 당일
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="cash_dividend",
            dividend_amount=1000.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))
    # 권리락 이전: × 0.9
    assert result.output[0].adj_close == pytest.approx(9000.0)
    assert result.output[1].adj_close == pytest.approx(9000.0)
    # 권리락 당일 이후: 변경 없음
    assert result.output[2].adj_close == pytest.approx(9000.0)
    # 거래량은 보존 (배당은 거래량 영향 없음)
    assert [r.adj_volume for r in result.output] == [1000.0, 1000.0, 1000.0]
    # close 원 가격 보존
    assert [r.close for r in result.output] == [10000.0, 10000.0, 9000.0]


def test_cash_dividend_skips_when_price_before_missing():
    """배당 event_date 이전 row가 없으면 SOFT skip (raise 안 함)."""
    rows = [
        _row(d=date(2024, 5, 1), price=9000.0),  # 권리락 당일만 있음
        _row(d=date(2024, 5, 2), price=9100.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="cash_dividend",
            dividend_amount=1000.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))
    # 가격 변경 없음 (skip)
    assert result.output[0].adj_close == pytest.approx(9000.0)
    assert result.output[1].adj_close == pytest.approx(9100.0)
    # SOFT issue 누적
    codes = [i.code for i in result.validation.issues]
    assert "CORP_ACTION_MISSING_PRICE_BEFORE" in codes
    assert result.validation.passed  # SOFT만 → passed=True


def test_cash_dividend_invalid_amount_raises():
    """dividend_amount 누락 → HARD."""
    rows = [_row(d=date(2024, 1, 2)), _row(d=date(2024, 5, 1))]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="cash_dividend",
            dividend_amount=None,
        ),
    )
    proc = AdjustedPriceProcessor()
    with pytest.raises(DataValidationError, match="dividend_amount"):
        proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))


def test_cash_dividend_amount_exceeds_price_raises():
    """dividend_amount >= price_before → HARD (가격이 음수 또는 0이 됨)."""
    rows = [
        _row(d=date(2024, 4, 30), price=100.0),
        _row(d=date(2024, 5, 1), price=0.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="cash_dividend",
            dividend_amount=200.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    with pytest.raises(DataValidationError):
        proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))


# ---------------------------------------------------------------------------
# 4) look-ahead 차단
# ---------------------------------------------------------------------------


def test_future_event_is_skipped_with_soft_warning():
    """as_of_date 이후 event_date는 무시 (SOFT)."""
    rows = [
        _row(d=date(2024, 1, 2), price=200.0),
        _row(d=date(2024, 1, 3), price=210.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2025, 5, 1),  # 미래
            event_type="split",
            ratio=2.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(
        AdjustedPriceInput(
            prices=_prices(rows),
            corporate_actions=events,
            as_of_date=date(2024, 12, 31),
        )
    )
    # 가격 변경 없음
    assert result.output[0].adj_close == pytest.approx(200.0)
    assert result.output[1].adj_close == pytest.approx(210.0)
    # SOFT issue
    codes = [i.code for i in result.validation.issues]
    assert "CORP_ACTION_FUTURE" in codes
    assert result.validation.passed


def test_as_of_date_defaults_to_prices_end_date():
    """as_of_date 미지정 시 prices.end_date를 사용."""
    rows = [_row(d=date(2024, 1, 2), price=200.0)]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2025, 5, 1),  # prices.end_date(2024-12-31)보다 미래
            event_type="split",
            ratio=2.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))
    assert result.output[0].adj_close == pytest.approx(200.0)
    assert "CORP_ACTION_FUTURE" in [i.code for i in result.validation.issues]


# ---------------------------------------------------------------------------
# 5) HARD 검증
# ---------------------------------------------------------------------------


def test_split_zero_ratio_raises_hard():
    rows = [_row(d=date(2024, 1, 2)), _row(d=date(2024, 5, 1))]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="split",
            ratio=0.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    with pytest.raises(DataValidationError, match="ratio"):
        proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))


def test_split_negative_ratio_raises_hard():
    rows = [_row(d=date(2024, 1, 2)), _row(d=date(2024, 5, 1))]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="split",
            ratio=-2.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    with pytest.raises(DataValidationError):
        proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))


def test_raise_on_hard_fail_false_collects_without_raise():
    """raise_on_hard_fail=False면 HARD를 issues에만 누적."""
    rows = [_row(d=date(2024, 1, 2)), _row(d=date(2024, 5, 1))]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="split",
            ratio=0.0,
        ),
    )
    proc = AdjustedPriceProcessor(raise_on_hard_fail=False)
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))
    assert not result.validation.passed
    assert result.validation.hard_fail_count >= 1


# ---------------------------------------------------------------------------
# 6) 미지원 이벤트
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("event_type", ["rights_issue", "merger", "spinoff"])
def test_simplified_events_skip_with_soft_warning(event_type):
    rows = [_row(d=date(2024, 1, 2)), _row(d=date(2024, 5, 1))]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type=event_type,
            ratio=1.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))
    # 가격 변경 없음
    assert result.output[0].adj_close == pytest.approx(100.0)
    codes = [i.code for i in result.validation.issues]
    assert "CORP_ACTION_UNSUPPORTED" in codes
    assert result.validation.passed


def test_delisting_event_no_price_impact():
    rows = [_row(d=date(2024, 1, 2), price=100.0)]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="delisting",
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))
    # 가격 변경 없음 + UNSUPPORTED 경고도 없음
    assert result.output[0].adj_close == pytest.approx(100.0)
    codes = [i.code for i in result.validation.issues]
    assert "CORP_ACTION_UNSUPPORTED" not in codes


# ---------------------------------------------------------------------------
# 7) 누적 적용 (시간 역순)
# ---------------------------------------------------------------------------


def test_multiple_events_accumulate_in_time_reversed_order():
    """분할(2024-05-01, 2.0) + 배당(2024-03-01, 100원, price_before=1000) 순차 적용.

    예상:
        - 2024-01-02: 가격 1000, 1차 배당 적용 → 900, 2차 분할 적용 → 450
        - 2024-02-28: 가격 1000, 1차 배당 적용 → 900, 2차 분할 적용 → 450
        - 2024-03-01: 권리락(배당), 분할 적용 → ×0.5
        - 2024-05-01: 권리락(분할), 변경 없음
    """
    rows = [
        _row(d=date(2024, 1, 2), price=1000.0, vol=1000.0),
        _row(d=date(2024, 2, 28), price=1000.0, vol=1000.0),  # price_before
        _row(d=date(2024, 3, 1), price=900.0, vol=1000.0),    # 권리락(배당)
        _row(d=date(2024, 5, 1), price=450.0, vol=2000.0),    # 권리락(분할)
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 3, 1),
            event_type="cash_dividend",
            dividend_amount=100.0,
        ),
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="split",
            ratio=2.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(AdjustedPriceInput(prices=_prices(rows), corporate_actions=events))

    # 1/2: 두 이벤트 모두 영향 → 1000 × 0.9 × 0.5 = 450
    assert result.output[0].adj_close == pytest.approx(450.0)
    # 2/28: 동일
    assert result.output[1].adj_close == pytest.approx(450.0)
    # 3/1: 분할만 영향 → 900 × 0.5 = 450
    assert result.output[2].adj_close == pytest.approx(450.0)
    # 5/1: 변경 없음
    assert result.output[3].adj_close == pytest.approx(450.0)


# ---------------------------------------------------------------------------
# 8) close 보존 / corporate_actions 없는 종목 통과
# ---------------------------------------------------------------------------


def test_close_volume_preserved_after_processing():
    rows = [
        _row(d=date(2024, 1, 2), price=200.0, vol=1000.0),
        _row(d=date(2024, 5, 1), price=110.0, vol=2000.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="split",
            ratio=2.0,
        ),
    )
    result = AdjustedPriceProcessor().process(
        AdjustedPriceInput(prices=_prices(rows), corporate_actions=events)
    )
    # 원 가격 / 원 거래량은 일절 변경 없음
    assert [r.open for r in result.output] == [200.0, 110.0]
    assert [r.high for r in result.output] == [200.0 * 1.02, 110.0 * 1.02]
    assert [r.low for r in result.output] == [200.0 * 0.98, 110.0 * 0.98]
    assert [r.close for r in result.output] == [200.0, 110.0]
    assert [r.volume for r in result.output] == [1000.0, 2000.0]


def test_symbol_without_events_passes_through_unchanged():
    rows = [
        _row(symbol="000660", d=date(2024, 1, 2), price=120.0, vol=500.0),
        _row(symbol="000660", d=date(2024, 5, 1), price=130.0, vol=600.0),
    ]
    events = ()
    result = AdjustedPriceProcessor().process(
        AdjustedPriceInput(prices=_prices(rows), corporate_actions=events)
    )
    assert len(result.output) == 2
    for orig, out in zip(rows, result.output, strict=True):
        assert orig == out  # frozen dataclass equality


# ---------------------------------------------------------------------------
# 9) 결정론
# ---------------------------------------------------------------------------


def test_determinism_repeated_5_times_yields_identical_output():
    rows = [
        _row(symbol="000660", d=date(2024, 1, 2), price=120.0, vol=500.0),
        _row(symbol="005930", d=date(2024, 1, 2), price=200.0, vol=1000.0),
        _row(symbol="005930", d=date(2024, 5, 1), price=110.0, vol=2000.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="split",
            ratio=2.0,
        ),
    )

    outputs = []
    for _ in range(5):
        proc = AdjustedPriceProcessor()
        result = proc.process(
            AdjustedPriceInput(prices=_prices(rows), corporate_actions=events)
        )
        outputs.append(result.output)
    # 모두 동일 (tuple of frozen dataclass → hash/equality 안정)
    for o in outputs[1:]:
        assert o == outputs[0]


def test_output_sorted_by_symbol_then_date():
    rows = [
        _row(symbol="005930", d=date(2024, 5, 2), price=100.0),
        _row(symbol="000660", d=date(2024, 5, 2), price=200.0),
        _row(symbol="000660", d=date(2024, 5, 1), price=210.0),
        _row(symbol="005930", d=date(2024, 5, 1), price=110.0),
    ]
    result = AdjustedPriceProcessor().process(
        AdjustedPriceInput(prices=_prices(rows), corporate_actions=())
    )
    keys = [(r.symbol, r.date) for r in result.output]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# 10) stats / validation 메타
# ---------------------------------------------------------------------------


def test_stats_reports_counts():
    rows = [
        _row(d=date(2024, 1, 2), price=200.0),
        _row(d=date(2024, 5, 1), price=100.0),
    ]
    events = (
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2024, 5, 1),
            event_type="split",
            ratio=2.0,
        ),
        CorporateActionEvent(
            symbol="005930",
            event_date=date(2025, 1, 1),  # 미래
            event_type="split",
            ratio=2.0,
        ),
    )
    proc = AdjustedPriceProcessor()
    result = proc.process(
        AdjustedPriceInput(
            prices=_prices(rows),
            corporate_actions=events,
            as_of_date=date(2024, 12, 31),
        )
    )
    stats_dict = dict(result.stats)
    assert stats_dict["events_total"] == 2
    assert stats_dict["events_applied"] == 1
    assert stats_dict["events_skipped_future"] == 1
    assert stats_dict["rows_processed"] == 2


def test_processor_name_default():
    proc = AdjustedPriceProcessor()
    assert proc.name == "adjusted_price"


def test_processor_name_custom():
    proc = AdjustedPriceProcessor(name="custom_adj")
    assert proc.name == "custom_adj"
