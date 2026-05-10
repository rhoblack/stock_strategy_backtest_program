"""GUI/API 노출용 조건 메타데이터 카탈로그.

각 조건 모듈에 정의된 `*_META` dict를 모아 단일 카탈로그로 노출.
`registry.list_conditions()`는 type/requires_position/category만 반환하지만,
프론트엔드의 BlockPalette/ConditionEditorPanel은 sentence_template, parameters,
allowed_in 등 풍부한 메타가 필요하다.

이 모듈을 import하는 시점에 모든 conditions/* 모듈이 로드되며 그 안의
`@condition_registry.register(...)` 데코레이터가 실행되어 자동 등록된다.

ALL_DEFINITIONS: dict[type, meta]
get_condition_catalog(): registry 등록 정보와 META를 합친 dict 리스트
"""

from __future__ import annotations

from app.strategy.conditions import breakout as _breakout
from app.strategy.conditions import exit_position as _exit_position
from app.strategy.conditions import macd as _macd
from app.strategy.conditions import moving_average as _moving_average
from app.strategy.conditions import rsi as _rsi
from app.strategy.conditions import trading_value as _trading_value
from app.strategy.conditions import volume as _volume
from app.strategy.registry import condition_registry

# type → 풍부한 메타데이터
ALL_DEFINITIONS: dict[str, dict] = {
    _moving_average.PRICE_VS_MA_META["type"]: _moving_average.PRICE_VS_MA_META,
    _moving_average.MA_CROSS_META["type"]: _moving_average.MA_CROSS_META,
    _volume.VOLUME_RATIO_META["type"]: _volume.VOLUME_RATIO_META,
    _rsi.RSI_LEVEL_META["type"]: _rsi.RSI_LEVEL_META,
    _trading_value.AVG_TRADING_VALUE_META["type"]: _trading_value.AVG_TRADING_VALUE_META,
    _trading_value.MARKET_INDEX_FILTER_META["type"]: _trading_value.MARKET_INDEX_FILTER_META,
    _macd.MACD_CROSS_META["type"]: _macd.MACD_CROSS_META,
    _macd.MACD_HISTOGRAM_META["type"]: _macd.MACD_HISTOGRAM_META,
    _breakout.NEW_HIGH_BREAKOUT_META["type"]: _breakout.NEW_HIGH_BREAKOUT_META,
    _breakout.GAP_PCT_META["type"]: _breakout.GAP_PCT_META,
    _breakout.MOMENTUM_RETURN_META["type"]: _breakout.MOMENTUM_RETURN_META,
    _exit_position.TAKE_PROFIT_META["type"]: _exit_position.TAKE_PROFIT_META,
    _exit_position.STOP_LOSS_META["type"]: _exit_position.STOP_LOSS_META,
    _exit_position.MAX_HOLDING_DAYS_META["type"]: _exit_position.MAX_HOLDING_DAYS_META,
    _exit_position.TRAILING_STOP_META["type"]: _exit_position.TRAILING_STOP_META,
}


def get_condition_catalog() -> list[dict]:
    """registry 등록 정보 + META를 머지한 카탈로그 (`GET /api/conditions` 응답 형태).

    registry에는 등록되었지만 META가 없는 조건이 있으면 KeyError로 빠르게 실패.
    """
    catalog = []
    for entry in condition_registry.list_conditions():
        condition_type = entry["type"]
        if condition_type not in ALL_DEFINITIONS:
            raise KeyError(
                f"{condition_type}이 ALL_DEFINITIONS에 등록되지 않았습니다. "
                "조건 모듈에 META를 정의하고 condition_definitions.py에 추가하세요."
            )
        meta = ALL_DEFINITIONS[condition_type]
        # registry 정보와 META가 충돌하지 않는지 가벼운 검증
        if meta["requires_position"] != entry["requires_position"]:
            raise ValueError(
                f"{condition_type}의 META.requires_position이 registry와 다릅니다"
            )
        catalog.append({**entry, **meta})
    return catalog
