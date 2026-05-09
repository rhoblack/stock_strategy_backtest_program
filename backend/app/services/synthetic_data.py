"""dev 모드 합성 시계열 데이터 generator.

Phase 14 (데이터 파이프라인)가 구현되기 전까지 dev/demo용으로 사용.
Phase 1 골든 테스트와 동일 알고리즘 (결정론, log normal returns).
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


def build_synthetic_series(
    seed: int = 42,
    n: int = 90,
    start_price: float = 10_000,
    base_date: date | None = None,
) -> pd.DataFrame:
    """결정론적 합성 OHLCV 데이터 + next_open / next_volume 컬럼."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.001, scale=0.02, size=n)
    closes = (start_price * np.exp(np.cumsum(returns))).round(0)
    high_mults = 1 + rng.uniform(0.001, 0.015, n)
    low_mults = 1 - rng.uniform(0.001, 0.015, n)
    open_jitter = rng.uniform(-0.005, 0.005, n)
    opens = (closes * (1 + open_jitter)).round(0)
    highs = (np.maximum(closes, opens) * high_mults).round(0)
    lows = (np.minimum(closes, opens) * low_mults).round(0)

    base = base_date or date(2024, 1, 2)
    dates = [base + timedelta(days=i) for i in range(n)]

    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": opens,
            "adj_high": highs,
            "adj_low": lows,
            "adj_close": closes,
            "adj_volume": np.full(n, 10_000.0),
        }
    )
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df
