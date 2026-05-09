"""condition_definitions 카탈로그 테스트.

조건 자동 등록과 메타 정합성을 검증.
"""

from app.strategy.condition_definitions import ALL_DEFINITIONS, get_condition_catalog
from app.strategy.registry import condition_registry

EXPECTED_TYPES = {"price_vs_ma", "ma_cross", "volume_ratio", "rsi_level", "take_profit"}


def test_all_5_conditions_registered():
    registered = set(condition_registry.list_condition_types())
    assert EXPECTED_TYPES.issubset(registered), (
        f"누락된 조건: {EXPECTED_TYPES - registered}"
    )


def test_all_5_conditions_in_definitions():
    assert set(ALL_DEFINITIONS.keys()) >= EXPECTED_TYPES


def test_meta_requires_position_matches_registry():
    for condition_type in EXPECTED_TYPES:
        meta = ALL_DEFINITIONS[condition_type]
        registry_flag = condition_registry.is_position_condition(condition_type)
        assert meta["requires_position"] == registry_flag, (
            f"{condition_type} META({meta['requires_position']}) vs registry({registry_flag})"
        )


def test_get_condition_catalog_returns_merged_entries():
    catalog = get_condition_catalog()
    assert len(catalog) >= len(EXPECTED_TYPES)
    # 머지 결과: registry 키 + META 키 모두 존재
    by_type = {item["type"]: item for item in catalog}
    for condition_type in EXPECTED_TYPES:
        item = by_type[condition_type]
        # registry 키
        assert "requires_position" in item
        assert "category" in item
        # META 키
        assert "name" in item
        assert "sentence_template" in item
        assert "parameters" in item
        assert "allowed_in" in item


def test_meta_allowed_in_values_are_valid():
    valid_sections = {"entry", "exit_signal", "exit_position", "filters"}
    for meta in ALL_DEFINITIONS.values():
        for section in meta["allowed_in"]:
            assert section in valid_sections, f"{meta['type']}.allowed_in 잘못된 값: {section}"


def test_position_condition_only_in_exit_position():
    """requires_position=True 조건은 exit_position에만 노출되어야 함."""
    for meta in ALL_DEFINITIONS.values():
        if meta["requires_position"]:
            assert meta["allowed_in"] == ["exit_position"], (
                f"{meta['type']}: 포지션 조건은 exit_position에만 허용됩니다"
            )


def test_timeseries_condition_not_in_exit_position():
    """requires_position=False 조건은 exit_position에 들어가면 안 됨."""
    for meta in ALL_DEFINITIONS.values():
        if not meta["requires_position"]:
            assert "exit_position" not in meta["allowed_in"], (
                f"{meta['type']}: 시계열 조건은 exit_position에 노출 금지"
            )


def test_meta_parameters_have_required_fields():
    for meta in ALL_DEFINITIONS.values():
        for param in meta["parameters"]:
            assert "name" in param
            assert "label" in param
            assert "input_type" in param
            assert "default" in param


def test_meta_select_parameters_have_options():
    for meta in ALL_DEFINITIONS.values():
        for param in meta["parameters"]:
            if param["input_type"] == "select":
                assert "options" in param
                assert len(param["options"]) >= 1
                for opt in param["options"]:
                    assert "label" in opt
                    assert "value" in opt
