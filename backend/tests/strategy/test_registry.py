"""ConditionRegistry 단위 테스트.

pandas 미설치 환경에서도 동작하도록 dummy 함수(list / tuple 반환)로 테스트한다.
실제 pandas Series 반환 검증은 조건 함수별 테스트 (Step 4)에서 수행.
"""

import pytest

from app.core.exceptions import (
    PositionConditionMisuseError,
    TimeseriesConditionMisuseError,
    UnknownConditionTypeError,
)
from app.strategy.registry import ConditionEntry, ConditionRegistry


def make_fresh_registry() -> ConditionRegistry:
    """각 테스트가 독립된 registry 인스턴스를 사용하도록 헬퍼."""
    return ConditionRegistry()


# === 시계열 조건 ===


def test_register_and_evaluate_timeseries_condition():
    registry = make_fresh_registry()

    @registry.register("dummy_ts", category="test_ts")
    def cond(df, condition):
        return [True, False, True]

    result = registry.evaluate("dummy_ts", df=None, condition={})
    assert result == [True, False, True]


def test_evaluate_passes_df_and_condition_arguments():
    registry = make_fresh_registry()
    captured = {}

    @registry.register("capture_ts")
    def cond(df, condition):
        captured["df"] = df
        captured["condition"] = condition
        return []

    registry.evaluate("capture_ts", df="DF_OBJ", condition={"key": "value"})
    assert captured == {"df": "DF_OBJ", "condition": {"key": "value"}}


# === 포지션 조건 ===


def test_register_and_evaluate_position_condition():
    registry = make_fresh_registry()

    @registry.register("dummy_pos", requires_position=True, category="exit_position")
    def cond(position, market_row, condition):
        return (True, "take_profit")

    triggered, reason = registry.evaluate_position(
        "dummy_pos", position=None, market_row=None, condition={}
    )
    assert triggered is True
    assert reason == "take_profit"


def test_evaluate_position_passes_three_arguments():
    registry = make_fresh_registry()
    captured = {}

    @registry.register("capture_pos", requires_position=True)
    def cond(position, market_row, condition):
        captured["position"] = position
        captured["market_row"] = market_row
        captured["condition"] = condition
        return (False, None)

    registry.evaluate_position(
        "capture_pos", position="POS", market_row="ROW", condition={"k": "v"}
    )
    assert captured == {"position": "POS", "market_row": "ROW", "condition": {"k": "v"}}


# === 라우팅 오류 ===


def test_position_condition_via_evaluate_raises():
    registry = make_fresh_registry()

    @registry.register("pos_cond", requires_position=True)
    def cond(position, market_row, condition):
        return (True, "x")

    with pytest.raises(PositionConditionMisuseError) as excinfo:
        registry.evaluate("pos_cond", df=None, condition={})
    assert "pos_cond" in str(excinfo.value)
    assert excinfo.value.code == "POSITION_CONDITION_MISUSE"


def test_timeseries_condition_via_evaluate_position_raises():
    registry = make_fresh_registry()

    @registry.register("ts_cond")
    def cond(df, condition):
        return []

    with pytest.raises(TimeseriesConditionMisuseError) as excinfo:
        registry.evaluate_position("ts_cond", position=None, market_row=None, condition={})
    assert "ts_cond" in str(excinfo.value)
    assert excinfo.value.code == "TIMESERIES_CONDITION_MISUSE"


# === 미등록 type ===


def test_unknown_type_in_evaluate_raises():
    registry = make_fresh_registry()
    with pytest.raises(UnknownConditionTypeError) as excinfo:
        registry.evaluate("not_registered", df=None, condition={})
    assert excinfo.value.code == "UNKNOWN_CONDITION_TYPE"


def test_unknown_type_in_evaluate_position_raises():
    registry = make_fresh_registry()
    with pytest.raises(UnknownConditionTypeError):
        registry.evaluate_position(
            "not_registered", position=None, market_row=None, condition={}
        )


def test_unknown_type_in_is_position_condition_raises():
    registry = make_fresh_registry()
    with pytest.raises(UnknownConditionTypeError):
        registry.is_position_condition("not_registered")


# === 메타데이터 / 조회 ===


def test_is_position_condition_returns_correct_flag():
    registry = make_fresh_registry()

    @registry.register("ts_one")
    def ts(df, condition):
        return []

    @registry.register("pos_one", requires_position=True)
    def pos(position, market_row, condition):
        return (False, None)

    assert registry.is_position_condition("ts_one") is False
    assert registry.is_position_condition("pos_one") is True


def test_get_category_returns_registered_value():
    registry = make_fresh_registry()

    @registry.register("c1", category="moving_average")
    def f1(df, condition):
        return []

    assert registry.get_category("c1") == "moving_average"


def test_list_conditions_returns_metadata_dicts():
    registry = make_fresh_registry()

    @registry.register("ts_one", category="moving_average")
    def f1(df, condition):
        return []

    @registry.register("pos_one", requires_position=True, category="exit_position")
    def f2(position, market_row, condition):
        return (False, None)

    listed = registry.list_conditions()
    assert len(listed) == 2

    by_type = {item["type"]: item for item in listed}
    assert by_type["ts_one"] == {
        "type": "ts_one",
        "requires_position": False,
        "category": "moving_average",
    }
    assert by_type["pos_one"] == {
        "type": "pos_one",
        "requires_position": True,
        "category": "exit_position",
    }


def test_list_condition_types_returns_names():
    registry = make_fresh_registry()

    @registry.register("a")
    def fa(df, condition):
        return []

    @registry.register("b")
    def fb(df, condition):
        return []

    types = registry.list_condition_types()
    assert sorted(types) == ["a", "b"]


# === 재등록 ===


def test_re_registering_overwrites_previous():
    registry = make_fresh_registry()

    @registry.register("c1", category="v1")
    def f_v1(df, condition):
        return ["v1"]

    @registry.register("c1", category="v2")
    def f_v2(df, condition):
        return ["v2"]

    assert registry.evaluate("c1", df=None, condition={}) == ["v2"]
    assert registry.get_category("c1") == "v2"


# === ConditionEntry ===


def test_condition_entry_is_frozen():
    """ConditionEntry는 frozen dataclass — 변경 불가."""
    entry = ConditionEntry(func=lambda: None, requires_position=False, category="x")
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        entry.category = "y"  # type: ignore[misc]


# === 모듈 레벨 싱글턴 ===


def test_module_level_condition_registry_exists():
    from app.strategy import condition_registry

    assert isinstance(condition_registry, ConditionRegistry)
