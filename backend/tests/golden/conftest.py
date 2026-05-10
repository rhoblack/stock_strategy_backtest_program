"""golden test 공통 fixture.

12번 §15 golden test fixture 구조:
  tests/golden/fixtures/   — 시세 데이터 파일
  tests/golden/strategies/ — 전략 JSON 파일
  tests/golden/expected/   — 기대값 JSON 파일
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

GOLDEN_DIR = Path(__file__).parent
STRATEGIES_DIR = GOLDEN_DIR / "strategies"
EXPECTED_DIR = GOLDEN_DIR / "expected"
FIXTURES_DIR = GOLDEN_DIR / "fixtures"


@pytest.fixture
def golden_strategy(request):
    """파라미터로 전달된 이름의 전략 JSON 로드.

    사용법: @pytest.mark.parametrize("golden_strategy", ["golden_01_ma_cross"], indirect=True)
    """
    name = request.param
    path = STRATEGIES_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"전략 파일 없음: {path}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    # _description 키는 메타 정보 — 전략 dict에서 제거
    return {k: v for k, v in data.items() if not k.startswith("_")}


@pytest.fixture
def golden_expected(request):
    """파라미터로 전달된 이름의 기대값 JSON 로드.

    사용법: @pytest.mark.parametrize("golden_expected", ["golden_01_summary"], indirect=True)
    """
    name = request.param
    path = EXPECTED_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"기대값 파일 없음: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_strategy(name: str) -> dict:
    """전략 JSON 파일 직접 로드 (fixture 외 일반 함수 사용용)."""
    path = STRATEGIES_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_expected(name: str) -> dict:
    """기대값 JSON 파일 직접 로드."""
    path = EXPECTED_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_synthetic_series(seed: int, n: int, start_price: float = 10_000) -> pd.DataFrame:
    """결정론적 합성 가격 시계열 생성 (golden test 공용).

    OHLC는 close 기준 ±1.5% 범위. 거래량 일정.
    phase1_golden.py와 동일한 알고리즘 (회귀 보호).
    """
    from datetime import date, timedelta

    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.001, scale=0.02, size=n)
    closes = start_price * np.exp(np.cumsum(returns))
    closes = closes.round(0)

    high_mults = 1 + rng.uniform(0.001, 0.015, n)
    low_mults = 1 - rng.uniform(0.001, 0.015, n)
    open_jitter = rng.uniform(-0.005, 0.005, n)

    opens = (closes * (1 + open_jitter)).round(0)
    highs = (np.maximum(closes, opens) * high_mults).round(0)
    lows = (np.minimum(closes, opens) * low_mults).round(0)

    base_date = date(2024, 1, 2)
    dates = [base_date + timedelta(days=i) for i in range(n)]

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
