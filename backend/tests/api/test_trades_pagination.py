"""trades pagination / filter / sort 단위 테스트 (10-p).

테스트 항목:
- 기본 응답 구조 (PaginatedTradesResponse)
- page / page_size 동작
- sort (execution_date_asc / execution_date_desc / profit_desc / profit_asc)
- symbol 필터
- has_next / total_pages 계산 정확성
"""

from datetime import date


def _strategy_payload() -> dict:
    return {
        "name": "페이지네이션 테스트 전략",
        "description": "",
        "strategy_json": {
            "entry": {
                "logic": "AND",
                "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
            },
            "exit_position": {
                "logic": "OR",
                "conditions": [{"type": "stop_loss", "percent": 3.0}],
            },
        },
        "tags": [],
    }


def _backtest_payload(strategy_id: int) -> dict:
    return {
        "strategy_id": strategy_id,
        "run_name": "페이징 테스트",
        "universe_config": {
            "symbol": "GOLDEN",
            "position_size_amount": 5_000_000,
            "synthetic_seed": 42,
            "synthetic_n": 90,
        },
        "start_date": str(date(2024, 1, 2)),
        "end_date": str(date(2024, 12, 31)),
        "initial_cash": 10_000_000.0,
        "fee_rate": 0.0,
        "tax_rate": 0.0,
        "slippage": 0.0,
        "tick_rounding": "nearest",
    }


def _make_run(client):
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    return client.post("/api/backtests", json=_backtest_payload(s["id"])).json()


def test_trades_response_structure(client):
    """응답 구조가 PaginatedTradesResponse 형식이다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades")
    assert r.status_code == 200
    body = r.json()

    # 페이지네이션 메타
    for key in ("items", "page", "page_size", "total_count", "total_pages", "has_next"):
        assert key in body, f"{key} 필드 누락"

    assert body["page"] == 1
    assert body["page_size"] == 50  # 기본값


def test_trades_items_have_required_fields(client):
    """items 단건에 필수 필드가 존재한다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades")
    body = r.json()
    if body["items"]:
        item = body["items"][0]
        for field in (
            "trade_group_id", "symbol", "entry_date", "entry_price",
            "entry_quantity", "remaining_quantity", "executions"
        ):
            assert field in item, f"{field} 필드 누락"

        # executions 단건
        if item["executions"]:
            ex = item["executions"][0]
            for field in ("execution_date", "execution_type", "price", "quantity"):
                assert field in ex, f"executions.{field} 필드 누락"


def test_trades_krw_int_fields(client):
    """entry_price / final_profit 등 금액 필드는 KRW 정수여야 한다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades")
    body = r.json()
    for item in body["items"]:
        assert isinstance(item["entry_price"], int), "entry_price가 int 아님"
        if item["final_profit"] is not None:
            assert isinstance(item["final_profit"], int), "final_profit이 int 아님"
        for ex in item["executions"]:
            assert isinstance(ex["price"], int), "execution.price가 int 아님"


def test_trades_page_size_limit(client):
    """page_size=2 로 요청하면 items가 최대 2개다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades?page_size=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) <= 2
    assert body["page_size"] == 2


def test_trades_pagination_total_count_consistent(client):
    """total_count와 total_pages가 일관적이다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades?page_size=3")
    body = r.json()
    total_count = body["total_count"]
    page_size = body["page_size"]
    expected_total_pages = max(1, (total_count + page_size - 1) // page_size)
    assert body["total_pages"] == expected_total_pages


def test_trades_has_next_false_on_last_page(client):
    """마지막 페이지에서는 has_next=False다."""
    run = _make_run(client)
    # 전체 건수 파악
    r_all = client.get(f"/api/backtests/{run['id']}/trades")

    # page=total_pages 요청
    total_pages = r_all.json()["total_pages"]
    r = client.get(f"/api/backtests/{run['id']}/trades?page={total_pages}")
    body = r.json()
    assert body["has_next"] is False


def test_trades_page2_returns_different_items(client):
    """page=1과 page=2의 items가 다르다 (trade_group이 2개 이상인 경우)."""
    run = _make_run(client)
    total = client.get(f"/api/backtests/{run['id']}/trades").json()["total_count"]
    if total < 2:
        return  # 데이터 부족 시 skip

    r1 = client.get(f"/api/backtests/{run['id']}/trades?page=1&page_size=1")
    r2 = client.get(f"/api/backtests/{run['id']}/trades?page=2&page_size=1")
    ids1 = [item["trade_group_id"] for item in r1.json()["items"]]
    ids2 = [item["trade_group_id"] for item in r2.json()["items"]]
    assert set(ids1).isdisjoint(set(ids2)), "page1과 page2가 같은 항목을 반환함"


def test_trades_sort_execution_date_desc(client):
    """sort=execution_date_desc 시 entry_date가 DESC 정렬된다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades?sort=execution_date_desc")
    assert r.status_code == 200
    items = r.json()["items"]
    if len(items) >= 2:
        dates = [item["entry_date"] for item in items]
        assert dates == sorted(dates, reverse=True), "DESC 정렬 실패"


def test_trades_sort_execution_date_asc(client):
    """sort=execution_date_asc 시 entry_date가 ASC 정렬된다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades?sort=execution_date_asc")
    assert r.status_code == 200
    items = r.json()["items"]
    if len(items) >= 2:
        dates = [item["entry_date"] for item in items]
        assert dates == sorted(dates), "ASC 정렬 실패"


def test_trades_sort_profit_desc(client):
    """sort=profit_desc 시 final_profit 기준 DESC 정렬된다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades?sort=profit_desc&page_size=200")
    assert r.status_code == 200
    items = r.json()["items"]
    profits = [item["final_profit"] for item in items if item["final_profit"] is not None]
    if len(profits) >= 2:
        assert profits == sorted(profits, reverse=True), "profit_desc 정렬 실패"


def test_trades_symbol_filter(client):
    """symbol 필터가 동작한다."""
    run = _make_run(client)
    # GOLDEN 합성 데이터의 심볼
    r_all = client.get(f"/api/backtests/{run['id']}/trades")
    all_symbols = {item["symbol"] for item in r_all.json()["items"]}
    if not all_symbols:
        return  # 거래 없으면 skip

    target = list(all_symbols)[0]
    r = client.get(f"/api/backtests/{run['id']}/trades?symbol={target}")
    assert r.status_code == 200
    body = r.json()
    for item in body["items"]:
        assert item["symbol"] == target, f"symbol 필터 실패: {item['symbol']} != {target}"


def test_trades_not_found_returns_404(client):
    """미존재 run_id → 404 BACKTEST_RUN_NOT_FOUND."""
    r = client.get("/api/backtests/99999/trades")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_trades_page_size_max_200(client):
    """page_size > 200 요청은 422 에러다."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades?page_size=201")
    assert r.status_code == 422 or r.status_code == 400


# ── 신규 컬럼 테스트 (10-t, step 053) ────────────────────────────────────────


def test_trades_response_has_new_columns(client):
    """응답 아이템에 entry_amount / exit_quantity / exit_amount / holding_days / signal_date 5개 필드 존재 (10-t)."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades")
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        return  # 거래 없으면 skip (구조 자체는 200이면 OK)

    item = items[0]
    new_fields = ("entry_amount", "exit_quantity", "exit_amount", "holding_days", "signal_date")
    for field in new_fields:
        assert field in item, f"응답 아이템에 {field} 필드 누락"


def test_entry_amount_calculation(client):
    """entry_amount = entry_price × entry_quantity 정확성 (10-t)."""
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades")
    assert r.status_code == 200
    for item in r.json()["items"]:
        expected = item["entry_price"] * item["entry_quantity"]
        assert item["entry_amount"] == expected, (
            f"entry_amount 불일치: {item['entry_amount']} != {expected} "
            f"(price={item['entry_price']}, qty={item['entry_quantity']})"
        )
        # KRW 정수 타입 검증
        assert isinstance(item["entry_amount"], int), "entry_amount가 int 아님"


def test_holding_days_null_for_open_position(client):
    """미청산 포지션(remaining_quantity > 0)은 holding_days=None (10-t).

    합성 데이터(synthetic_seed=42, 90봉)에서 백테스트 종료 시점에 포지션이 열린
    채로 끝나는 경우를 확인한다. 모든 포지션이 청산된 경우는 skip.
    """
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades?page_size=200")
    assert r.status_code == 200
    items = r.json()["items"]

    open_positions = [it for it in items if it["remaining_quantity"] > 0]
    if not open_positions:
        # 모두 청산됐으면 holding_days가 None이 아닌지 검증 (청산된 것은 int이어야 함)
        closed_positions = [it for it in items if it["fully_closed_at"] is not None]
        for it in closed_positions:
            assert it["holding_days"] is not None, (
                f"청산된 포지션의 holding_days가 None: trade_group_id={it['trade_group_id']}"
            )
        return  # 미청산 없으면 나머지 검증 불필요

    for it in open_positions:
        assert it["holding_days"] is None, (
            f"미청산 포지션의 holding_days가 None이 아님: "
            f"trade_group_id={it['trade_group_id']}, holding_days={it['holding_days']}"
        )


def test_signal_date_present(client):
    """SELL(청산)이 있는 거래 그룹에 signal_date 필드가 포함된다 (10-t).

    signal_date는 진입 신호일로 BUY TradeExecution에서 가져온다.
    값이 있으면 ISO 날짜 문자열(YYYY-MM-DD)이어야 한다.
    """
    run = _make_run(client)
    r = client.get(f"/api/backtests/{run['id']}/trades?page_size=200")
    assert r.status_code == 200
    items = r.json()["items"]

    for item in items:
        # signal_date 필드가 반드시 존재해야 함 (None도 허용)
        assert "signal_date" in item, f"signal_date 필드 누락: {item['trade_group_id']}"
        sd = item["signal_date"]
        if sd is not None:
            # ISO 날짜 형식 검증
            from datetime import date as _date
            try:
                _date.fromisoformat(sd)
            except ValueError:
                raise AssertionError(
                    f"signal_date가 ISO 날짜 형식이 아님: {sd!r} "
                    f"(trade_group_id={item['trade_group_id']})"
                ) from None
