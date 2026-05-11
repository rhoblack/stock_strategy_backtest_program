"""CSV/ZIP Export API 테스트.

신규 (step 035):
- test_export_symbol_performance_* : 09-i 분리 라우팅 + encoding
- test_export_universe_history_*   : 09-j 분리 라우팅 + encoding
- test_export_strategy_snapshot_route : 09-k /export/strategy-snapshot
- test_export_encoding_*           : 09-l encoding query param
"""

import io
import zipfile
from datetime import date


def _strategy_payload():
    return {
        "name": "테스트",
        "description": "",
        "strategy_json": {
            "entry": {"logic": "AND", "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"}
            ]},
            "exit_position": {"logic": "OR", "conditions": [
                {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
                {"type": "stop_loss", "percent": 3.0},
            ]},
        },
        "tags": [],
    }


def _backtest_payload(strategy_id):
    return {
        "strategy_id": strategy_id,
        "run_name": "GOLDEN",
        "universe_config": {
            "symbol": "GOLDEN", "position_size_amount": 5_000_000,
            "synthetic_seed": 42, "synthetic_n": 90,
        },
        "start_date": str(date(2024, 1, 2)),
        "end_date": str(date(2024, 12, 31)),
        "initial_cash": 10_000_000.0,
        "fee_rate": 0.0, "tax_rate": 0.0, "slippage": 0.0, "tick_rounding": "nearest",
    }


def _setup(client):
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()
    return run["id"]


def test_export_summary_csv(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/summary")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8-sig")
    assert "trade_count" in text  # header
    assert "8" in text  # frozen Phase 1 골든 결과


def test_export_trades_csv(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/trades")
    text = r.content.decode("utf-8-sig")
    # header
    assert "symbol" in text
    # 거래 9건 + 헤더 1줄
    line_count = sum(1 for line in text.splitlines() if line.strip())
    assert line_count == 9 + 1


def test_export_daily_equity_csv(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/daily-equity")
    text = r.content.decode("utf-8-sig")
    assert "drawdown_pct" in text
    line_count = sum(1 for line in text.splitlines() if line.strip())
    assert line_count == 90 + 1


def test_export_cash_events_csv(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/cash-events")
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert "event_type" in text


def test_export_strategy_snapshot_json(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/strategy")
    assert r.status_code == 200
    body = r.json()
    assert body["entry"]["conditions"][0]["type"] == "price_vs_ma"


def test_export_zip(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    # 09-k: 신규 symbol_performance.csv + universe_history.csv 포함 (7개 → 7파일)
    assert {
        "summary.csv", "trades.csv", "daily_equity.csv",
        "cash_events.csv", "symbol_performance.csv",
        "universe_history.csv", "strategy_snapshot.json",
    } == names


def test_export_invalid_kind(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/unknown")
    assert r.status_code == 400


def test_export_unknown_run(client):
    r = client.get("/api/backtests/9999/export/zip")
    assert r.status_code == 404


# ───────────────────────────────────────────────────────────────────────────
# 09-i: /export/symbol-performance 분리 라우팅
# ───────────────────────────────────────────────────────────────────────────

def test_export_symbol_performance_route_200(client):
    """분리 라우팅 /export/symbol-performance — 200 + CSV 헤더 확인."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/symbol-performance")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    # UTF-8 BOM 기본값 확인
    assert r.content[:3] == b"\xef\xbb\xbf"
    text = r.content.decode("utf-8-sig")
    # 컬럼 헤더 확인
    assert "symbol" in text
    assert "trade_count" in text
    assert "win_rate" in text
    assert "total_profit" in text
    assert "avg_holding_days" in text


def test_export_symbol_performance_total_profit_is_int(client):
    """total_profit 필드가 정수(KRW) — 소수점 없음."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/symbol-performance")
    text = r.content.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        # 헤더에서 total_profit 인덱스
        headers = lines[0].split(",")
        tp_idx = headers.index("total_profit")
        # 데이터 행의 total_profit 값이 정수 형식인지 확인
        for data_line in lines[1:]:
            vals = data_line.split(",")
            tp_val = vals[tp_idx]
            assert "." not in tp_val, f"total_profit에 소수점 있음: {tp_val!r}"


def test_export_symbol_performance_sorted_by_total_profit_desc(client):
    """total_profit DESC 정렬 확인."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/symbol-performance")
    text = r.content.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= 2:
        return  # 종목 1개 이하이면 정렬 검증 불가
    headers = lines[0].split(",")
    tp_idx = headers.index("total_profit")
    profits = [int(line.split(",")[tp_idx]) for line in lines[1:]]
    assert profits == sorted(profits, reverse=True), "total_profit DESC 정렬 위반"


def test_export_symbol_performance_via_kind_route(client):
    """하위 호환 /{kind} 라우트로도 동일 내용 접근 가능."""
    run_id = _setup(client)
    r1 = client.get(f"/api/backtests/{run_id}/export/symbol-performance")
    r2 = client.get(f"/api/backtests/{run_id}/export/symbol-performance")
    assert r1.status_code == 200
    assert r2.status_code == 200


# ───────────────────────────────────────────────────────────────────────────
# 09-j: /export/universe-history 분리 라우팅
# ───────────────────────────────────────────────────────────────────────────

def test_export_universe_history_route_200(client):
    """분리 라우팅 /export/universe-history — 200 + CSV 헤더 확인."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/universe-history")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.content[:3] == b"\xef\xbb\xbf"
    text = r.content.decode("utf-8-sig")
    assert "date" in text
    assert "symbol" in text
    assert "market" in text
    assert "rank" in text


def test_export_universe_history_empty_when_no_data(client):
    """universe_history 행이 없으면 헤더만 있는 CSV 반환."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/universe-history")
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    # 헤더 1줄만 있어야 함 (데이터 없음)
    assert len(lines) == 1, f"예상 헤더 1줄, 실제 {len(lines)}줄"


# ───────────────────────────────────────────────────────────────────────────
# 09-k: /export/strategy-snapshot 분리 라우팅
# ───────────────────────────────────────────────────────────────────────────

def test_export_strategy_snapshot_route(client):
    """/export/strategy-snapshot 분리 라우팅 — JSON 반환."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/strategy-snapshot")
    assert r.status_code == 200
    body = r.json()
    assert "entry" in body
    assert body["entry"]["conditions"][0]["type"] == "price_vs_ma"


def test_export_strategy_snapshot_content_disposition(client):
    """strategy-snapshot 응답의 Content-Disposition 확인."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/strategy-snapshot")
    assert "strategy_snapshot.json" in r.headers.get("content-disposition", "")


# ───────────────────────────────────────────────────────────────────────────
# 09-l: encoding query param
# ───────────────────────────────────────────────────────────────────────────

def test_export_encoding_utf8_bom_default(client):
    """기본값(encoding 미지정)은 UTF-8 BOM — 첫 3바이트 EF BB BF."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/symbol-performance")
    assert r.content[:3] == b"\xef\xbb\xbf", "UTF-8 BOM 기대값"


def test_export_encoding_utf8_no_bom(client):
    """?encoding=utf-8 — BOM 없는 UTF-8."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/symbol-performance?encoding=utf-8")
    assert r.status_code == 200
    # BOM 없음 확인 — 첫 3바이트가 EF BB BF가 아님
    assert r.content[:3] != b"\xef\xbb\xbf", "BOM이 없어야 함"
    # 유효한 UTF-8 텍스트 확인
    text = r.content.decode("utf-8")
    assert "symbol" in text


def test_export_encoding_cp949(client):
    """?encoding=cp949 — CP949 인코딩, BOM 없음."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/symbol-performance?encoding=cp949")
    assert r.status_code == 200
    # BOM 없음 — EF BB BF 아님
    assert r.content[:3] != b"\xef\xbb\xbf"
    # CP949 디코딩 가능 확인
    text = r.content.decode("cp949")
    assert "symbol" in text


def test_export_encoding_invalid(client):
    """잘못된 encoding 값 → 400 에러 envelope."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/symbol-performance?encoding=latin1")
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "INVALID_PARAMETER_VALUE"


def test_export_encoding_universe_history_utf8_bom(client):
    """universe-history도 encoding 옵션 지원 — UTF-8 BOM 기본값."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/universe-history")
    assert r.content[:3] == b"\xef\xbb\xbf"


def test_export_encoding_universe_history_utf8(client):
    """universe-history ?encoding=utf-8 — BOM 없음."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/universe-history?encoding=utf-8")
    assert r.status_code == 200
    assert r.content[:3] != b"\xef\xbb\xbf"


# ───────────────────────────────────────────────────────────────────────────
# 09-h (step 052): trades.csv 컬럼 정합화
# ───────────────────────────────────────────────────────────────────────────

def test_export_trades_csv_required_columns(client):
    """trades.csv 헤더에 09번 §5 정의 컬럼 전체 포함 (09-h)."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/trades")
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    headers = text.splitlines()[0].split(",")
    required = [
        "symbol", "name",
        "entry_date", "entry_price", "entry_quantity", "entry_amount",
        "exit_date", "exit_price", "exit_quantity", "exit_amount",
        "profit", "profit_rate", "holding_days", "exit_reason", "signal_date",
    ]
    for col in required:
        assert col in headers, f"trades.csv 누락 컬럼: {col!r}"


def test_export_trades_csv_no_legacy_columns(client):
    """구 컬럼(trade_group_id, remaining_quantity)은 trades.csv에 없어야 함 (09-h)."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/trades")
    text = r.content.decode("utf-8-sig")
    headers_line = text.splitlines()[0]
    assert "trade_group_id" not in headers_line
    assert "remaining_quantity" not in headers_line


# ───────────────────────────────────────────────────────────────────────────
# 09-m (step 052): ZIP 파일명 형식 backtest_{strategy_name}_{run_id}.zip
# ───────────────────────────────────────────────────────────────────────────

def test_export_zip_filename_format(client):
    """ZIP Content-Disposition이 backtest_{strategy_name}_{run_id}.zip 형식 (09-m)."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/zip")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    # filename이 backtest_로 시작하고 .zip으로 끝나야 함
    assert "backtest_" in cd, f"Content-Disposition에 backtest_ 없음: {cd!r}"
    assert ".zip" in cd, f"Content-Disposition에 .zip 없음: {cd!r}"
    # run_id가 파일명에 포함되어야 함
    assert str(run_id) in cd, f"run_id({run_id})가 파일명에 없음: {cd!r}"


def test_export_zip_filename_no_run_prefix(client):
    """ZIP 파일명이 구 형식 backtest_run_{id}.zip이 아님 (09-m)."""
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/zip")
    cd = r.headers.get("content-disposition", "")
    # 구 형식 "backtest_run_" 이 없어야 함
    assert "backtest_run_" not in cd, f"구 파일명 형식 감지: {cd!r}"
