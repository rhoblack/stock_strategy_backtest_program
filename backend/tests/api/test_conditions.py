"""GET /api/conditions 응답 형식 검증."""


EXPECTED_TYPES = {"price_vs_ma", "ma_cross", "volume_ratio", "rsi_level", "take_profit"}


def test_list_conditions_returns_all_registered(client):
    r = client.get("/api/conditions")
    assert r.status_code == 200
    items = r.json()
    types = {item["type"] for item in items}
    assert EXPECTED_TYPES.issubset(types)


def test_list_conditions_each_item_has_required_fields(client):
    items = client.get("/api/conditions").json()
    required = {
        "type", "category", "requires_position",
        "name", "description", "sentence_template",
        "parameters", "allowed_in",
    }
    for item in items:
        missing = required - set(item.keys())
        assert not missing, f"{item.get('type')} 누락 필드: {missing}"


def test_position_conditions_only_in_exit_position(client):
    items = client.get("/api/conditions").json()
    for item in items:
        if item["requires_position"]:
            assert item["allowed_in"] == ["exit_position"], (
                f"{item['type']}: 포지션 조건은 exit_position에만 노출"
            )


def test_take_profit_meta_fields(client):
    items = client.get("/api/conditions").json()
    take_profit = next(i for i in items if i["type"] == "take_profit")
    assert take_profit["requires_position"] is True
    assert take_profit["category"] == "exit_position"
    # parameters에 percent / trigger
    param_names = {p["name"] for p in take_profit["parameters"]}
    assert {"percent", "trigger"}.issubset(param_names)


def test_price_vs_ma_default_price_field_is_adj_close(client):
    """정확성 정책 13.7."""
    items = client.get("/api/conditions").json()
    cond = next(i for i in items if i["type"] == "price_vs_ma")
    price_field_param = next(p for p in cond["parameters"] if p["name"] == "price_field")
    assert price_field_param["default"] == "adj_close"
