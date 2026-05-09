"""호가 단위 (Tick Size) 처리.

정확성 정책 13.5절에 따라 한국 주식의 가격대별 호가 단위를 적용해
체결가를 보수적으로 반올림한다.

기준: 2025년 한국 코스피/코스닥 (코드 상수로 분리, 향후 시기·시장별 분기 가능).
"""

from __future__ import annotations

# (가격 임계값, 호가 단위)
# 가격이 thresholds[i][0] 미만이면 thresholds[i][1] 호가 사용.
# 마지막 항목은 무한대 → 1,000원.
_KOSPI_TICKS: tuple[tuple[float, int], ...] = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
    (float("inf"), 1_000),
)

_TICKS_BY_MARKET: dict[str, tuple[tuple[float, int], ...]] = {
    "KOSPI": _KOSPI_TICKS,
    "KOSDAQ": _KOSPI_TICKS,  # MVP는 동일 호가
}


def tick_size_for(price: float, market: str = "KOSPI") -> int:
    """주어진 가격대의 호가 단위 (원). 가격은 0 이상이어야 함."""
    if price < 0:
        raise ValueError(f"price는 0 이상이어야 합니다: {price}")

    table = _TICKS_BY_MARKET.get(market)
    if table is None:
        raise ValueError(f"지원하지 않는 시장입니다: {market!r}")

    for threshold, tick in table:
        if price < threshold:
            return tick
    # threshold inf 항목이 항상 마지막에 있으므로 도달 불가
    return table[-1][1]


def round_to_tick(
    price: float,
    market: str = "KOSPI",
    side: str = "buy",
    mode: str = "buy_up_sell_down",
) -> int:
    """가격을 호가 단위로 반올림한 정수 가격을 반환.

    mode:
        "buy_up_sell_down" (기본, 보수): side="buy"면 올림, side="sell"이면 내림
        "nearest": 단순 반올림
    """
    if price < 0:
        raise ValueError(f"price는 0 이상이어야 합니다: {price}")

    tick = tick_size_for(price, market)

    if mode == "nearest":
        return int(round(price / tick) * tick)

    if mode == "buy_up_sell_down":
        if side == "buy":
            # 천장(올림)
            quotient = -(-int(price * 1_000_000) // (tick * 1_000_000))
            return quotient * tick
        if side == "sell":
            return (int(price) // tick) * tick
        raise ValueError(f"지원하지 않는 side: {side!r}")

    raise ValueError(f"지원하지 않는 mode: {mode!r}")
