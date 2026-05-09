"""호가 단위 테스트 — 정확성 정책 13.5."""

import pytest

from app.backtest.tick import round_to_tick, tick_size_for

# === tick_size_for ===


@pytest.mark.parametrize(
    "price,expected",
    [
        (1, 1),
        (1_999, 1),
        (2_000, 5),
        (4_999, 5),
        (5_000, 10),
        (19_999, 10),
        (20_000, 50),
        (49_999, 50),
        (50_000, 100),
        (199_999, 100),
        (200_000, 500),
        (499_999, 500),
        (500_000, 1_000),
        (1_000_000, 1_000),
    ],
)
def test_tick_size_thresholds(price, expected):
    assert tick_size_for(price) == expected


def test_tick_size_negative_price_raises():
    with pytest.raises(ValueError):
        tick_size_for(-100)


def test_tick_size_unknown_market_raises():
    with pytest.raises(ValueError):
        tick_size_for(10_000, market="NASDAQ")


# === round_to_tick: nearest mode ===


def test_round_nearest_below_2000_unit_1():
    assert round_to_tick(1234.7, mode="nearest") == 1235


def test_round_nearest_unit_50():
    # 가격대 20,000~50,000 → 호가 50원
    assert round_to_tick(25_120, mode="nearest") == 25_100
    assert round_to_tick(25_125, mode="nearest") == 25_100  # 반올림 (banker's)
    assert round_to_tick(25_175, mode="nearest") == 25_200


def test_round_nearest_unit_100():
    assert round_to_tick(75_350, mode="nearest") == 75_400
    assert round_to_tick(75_349, mode="nearest") == 75_300


# === round_to_tick: buy_up_sell_down mode ===


def test_round_buy_up_at_unit_100():
    """매수는 위로 (불리). 75,310 → 75,400."""
    assert round_to_tick(75_310, side="buy", mode="buy_up_sell_down") == 75_400


def test_round_sell_down_at_unit_100():
    """매도는 아래로 (불리). 75,390 → 75,300."""
    assert round_to_tick(75_390, side="sell", mode="buy_up_sell_down") == 75_300


def test_round_exact_tick_unchanged():
    """정확히 호가에 떨어지면 변동 없음."""
    assert round_to_tick(75_300, side="buy", mode="buy_up_sell_down") == 75_300
    assert round_to_tick(75_300, side="sell", mode="buy_up_sell_down") == 75_300


def test_round_invalid_side_raises():
    with pytest.raises(ValueError):
        round_to_tick(10_000, side="hold", mode="buy_up_sell_down")


def test_round_invalid_mode_raises():
    with pytest.raises(ValueError):
        round_to_tick(10_000, side="buy", mode="aggressive")
