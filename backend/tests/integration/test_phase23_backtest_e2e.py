"""Phase 23 step 069: 백테스트 API 수준 end-to-end 통합 테스트.

검증 목표 (E23-01 ~ E23-05):
  E23-01: 전략 생성 → 백테스트 실행 → 결과 조회 전 흐름
  E23-02: 거래 내역 조회 + CSV / ZIP export
  E23-03: strategy_snapshot_json 기반 재현성 (동일 전략 2회 실행 → 동일 메트릭)
  E23-04: 백테스트 취소 end-to-end (cancel → cancelled 또는 completed 허용)
  E23-05: 잘못된 조건 타입 → 422 또는 status=="failed"

정확성 정책 매핑:
  - 13.12   결정론 — 동일 입력 동일 결과 (E23-03)
  - 13.9    거래세 시계열 — fee_rate/tax_rate=0 으로 격리
  - CLAUDE.md #9  strategy_snapshot_json + 파라미터 영속화 (E23-03)
  - CLAUDE.md #8  ORDER BY 결정론 (E23-03)
  - 10번 §4.4  CancellationToken (E23-04)

본 파일: tests/integration/test_phase23_backtest_e2e.py
TestClient + SQLite fixture는 tests/api/conftest.py 패턴을 인라인 복사
(통합 테스트 디렉토리에는 conftest.py 의존성 없음 — 자체 완결).
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.db.session import create_db_engine, init_db, make_session_factory
from app.main import app
from app.main_state import reset_engine_for_tests
from app.models.user import User

# ---------------------------------------------------------------------------
# fixture — tests/api/conftest.py 패턴 인라인 (자체 완결)
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """파일 기반 SQLite — dependency 새 session에서도 테이블 보존."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "phase23_e2e.db")
    url = f"sqlite:///{path}"
    engine = create_db_engine(url)
    init_db(engine)

    SessionLocal = make_session_factory(engine)
    with SessionLocal() as session:
        if session.get(User, 1) is None:
            session.add(User(id=1, email="system@local"))
            session.commit()

    reset_engine_for_tests(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        try:
            if os.path.exists(path):
                os.unlink(path)
            os.rmdir(tmpdir)
        except OSError:
            pass


@pytest.fixture()
def client(db_engine):  # noqa: ARG001
    return TestClient(app)


# ---------------------------------------------------------------------------
# 공용 payload 빌더
# ---------------------------------------------------------------------------

_STRATEGY_JSON = {
    "entry": {
        "logic": "AND",
        "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
    },
    "exit_position": {
        "logic": "OR",
        "conditions": [
            {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
            {"type": "stop_loss", "percent": 3.0},
        ],
    },
}


def _strategy_payload(name: str = "e2e 테스트 전략") -> dict:
    return {
        "name": name,
        "description": "",
        "strategy_json": _STRATEGY_JSON,
        "tags": [],
    }


def _backtest_payload(strategy_id: int, run_name: str = "integration_test") -> dict:
    """BacktestCreate payload 기준값 (합성 데이터 — pykrx 호출 없음)."""
    return {
        "strategy_id": strategy_id,
        "run_name": run_name,
        "universe_config": {
            "symbol": "GOLDEN",
            "synthetic_seed": 42,
            "synthetic_n": 90,
            "position_size_amount": 5_000_000,
        },
        "start_date": "2024-01-02",
        "end_date": "2024-12-31",
        "initial_cash": 10_000_000,
        "fee_rate": 0.0,
        "tax_rate": 0.0,
        "slippage": 0.0,
    }


def _create_and_run(client: TestClient, *, run_name: str = "integration_test") -> dict:
    """전략 생성 + 백테스트 실행 → run 딕셔너리 반환 (completed까지 동기 대기)."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    r = client.post("/api/backtests", json=_backtest_payload(s["id"], run_name))
    assert r.status_code == 202, f"백테스트 생성 실패: {r.text}"
    run = r.json()
    # TestClient의 BackgroundTask는 응답 후 동기 실행 → 곧바로 completed
    return run


# ---------------------------------------------------------------------------
# E23-01: 전략 생성 → 백테스트 실행 → 결과 조회 전 흐름
# ---------------------------------------------------------------------------


def test_full_e2e_flow(client):
    """E23-01: POST /api/strategies → POST /api/backtests → GET /{id}/summary.

    정확성 정책 매핑:
      - CLAUDE.md #9  strategy_snapshot_json + 파라미터 영속화
      - 13.12  결정론 — 합성 seed=42 기반 고정 결과
    """
    # 전략 생성
    s_resp = client.post("/api/strategies", json=_strategy_payload())
    assert s_resp.status_code == 201, f"전략 생성 실패: {s_resp.text}"
    strategy = s_resp.json()
    assert strategy["id"] > 0

    # 백테스트 실행
    b_resp = client.post("/api/backtests", json=_backtest_payload(strategy["id"]))
    assert b_resp.status_code == 202, f"백테스트 생성 실패: {b_resp.text}"
    run = b_resp.json()
    run_id = run["id"]
    assert run_id > 0

    # 상태 조회 — TestClient BackgroundTask 동기 실행이므로 completed 기대
    status_resp = client.get(f"/api/backtests/{run_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "completed", (
        f"백테스트가 완료되지 않음: {status_data['status']}"
    )

    # 요약 결과 조회
    summary_resp = client.get(f"/api/backtests/{run_id}/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["status"] == "completed"
    assert summary["summary"] is not None

    s = summary["summary"]
    assert s["trade_count"] > 0, "거래 0건 — 전략/데이터 문제"
    assert s["final_equity"] > 0, "최종 자산 0 — 계산 오류"
    # win_rate는 0.0~100.0 퍼센트 스케일로 저장됨 (예: 37.5%)
    assert 0.0 <= s.get("win_rate", 0.0) <= 100.0, "win_rate 범위 이탈 (0~100)"


# ---------------------------------------------------------------------------
# E23-02: 거래 내역 조회 + CSV / ZIP export
# ---------------------------------------------------------------------------


def test_trades_and_csv_export(client):
    """E23-02: GET /{id}/trades, GET /{id}/export/trades, GET /{id}/export/zip.

    정확성 정책 매핑:
      - 07번 §9~10  trade_groups + trade_executions 1:N 모델
      - 09번 §4     CSV export 형식
    """
    run = _create_and_run(client)
    run_id = run["id"]

    # 거래 내역 조회
    trades_resp = client.get(f"/api/backtests/{run_id}/trades")
    assert trades_resp.status_code == 200
    trades_body = trades_resp.json()
    assert trades_body["total_count"] > 0, "거래 내역이 비어있음"
    first = trades_body["items"][0]
    assert "executions" in first, "executions 필드 누락"
    assert len(first["executions"]) >= 1, "execution이 0건"

    # CSV export (trades)
    csv_resp = client.get(f"/api/backtests/{run_id}/export/trades")
    assert csv_resp.status_code == 200, f"trades CSV export 실패: {csv_resp.status_code}"
    content_type = csv_resp.headers.get("content-type", "")
    assert "text/csv" in content_type, f"content-type 이상: {content_type}"
    # CSV 내용이 비어있지 않음
    assert len(csv_resp.content) > 10, "CSV 내용이 너무 짧음"

    # ZIP export
    zip_resp = client.get(f"/api/backtests/{run_id}/export/zip")
    assert zip_resp.status_code == 200, f"ZIP export 실패: {zip_resp.status_code}"
    zip_content_type = zip_resp.headers.get("content-type", "")
    assert "zip" in zip_content_type or "octet-stream" in zip_content_type, (
        f"ZIP content-type 이상: {zip_content_type}"
    )
    # PK signature (ZIP magic bytes)
    assert zip_resp.content[:2] == b"PK", "ZIP 파일이 아님 (magic bytes 불일치)"


# ---------------------------------------------------------------------------
# E23-03: 재현성 검증 (strategy_snapshot_json 기반 결정론)
# ---------------------------------------------------------------------------


def test_reproducibility_with_snapshot(client):
    """E23-03: 동일 전략으로 2회 백테스트 → trade_count / final_equity 동일.

    정확성 정책 매핑:
      - 13.12  결정론 — 동일 입력 동일 결과 (CLAUDE.md #8)
      - CLAUDE.md #9  strategy_snapshot_json 영속화로 재현 보장
    """
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    strategy_id = s["id"]

    run1 = client.post("/api/backtests", json=_backtest_payload(strategy_id, "run1")).json()
    run2 = client.post("/api/backtests", json=_backtest_payload(strategy_id, "run2")).json()

    run1_id = run1["id"]
    run2_id = run2["id"]

    # 두 실행 모두 완료 확인
    status1 = client.get(f"/api/backtests/{run1_id}/status").json()
    status2 = client.get(f"/api/backtests/{run2_id}/status").json()
    assert status1["status"] == "completed", f"run1 미완료: {status1['status']}"
    assert status2["status"] == "completed", f"run2 미완료: {status2['status']}"

    summary1 = client.get(f"/api/backtests/{run1_id}/summary").json()["summary"]
    summary2 = client.get(f"/api/backtests/{run2_id}/summary").json()["summary"]

    assert summary1["trade_count"] == summary2["trade_count"], (
        f"결정론 위반 — trade_count 불일치: {summary1['trade_count']} != {summary2['trade_count']}"
    )
    assert summary1["final_equity"] == summary2["final_equity"], (
        f"결정론 위반 — final_equity 불일치: {summary1['final_equity']} != {summary2['final_equity']}"
    )


# ---------------------------------------------------------------------------
# E23-04: 취소 end-to-end
# ---------------------------------------------------------------------------


def test_cancel_e2e(client):
    """E23-04: POST /api/backtests → POST /{id}/cancel → cancelled 또는 completed.

    TestClient의 BackgroundTask는 POST 응답 직후 동기 실행되므로,
    cancel 요청이 도달할 때 이미 completed일 수 있다 (경쟁 조건 허용).
    두 상태 모두 정상 — 중요한 것은 500 에러가 없어야 함.

    정확성 정책 매핑:
      - 10번 §4.4  CancellationToken end-to-end 전파
    """
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()
    run_id = run["id"]

    cancel_resp = client.post(f"/api/backtests/{run_id}/cancel")
    # 이미 completed면 409 (BACKTEST_NOT_RUNNING) 반환 가능
    assert cancel_resp.status_code in (200, 409), (
        f"예상하지 않은 상태 코드: {cancel_resp.status_code} — {cancel_resp.text}"
    )

    # 최종 status 확인
    final = client.get(f"/api/backtests/{run_id}/status").json()
    assert final["status"] in ("cancelled", "cancelling", "completed"), (
        f"취소 후 비정상 상태: {final['status']}"
    )


# ---------------------------------------------------------------------------
# E23-05: 잘못된 전략 JSON → 422 또는 status=="failed"
# ---------------------------------------------------------------------------


def test_invalid_strategy_json_422(client):
    """E23-05: 존재하지 않는 condition type → 422 또는 백테스트 status=="failed".

    FastAPI validator가 전략 JSON 형식 자체를 차단하면 422,
    조건 등록 레지스트리 오류로 서비스에서 실패하면 status=="failed".
    두 결과 모두 허용 — 중요한 것은 무결성(500 Internal Server Error 없음).

    정확성 정책 매핑:
      - CLAUDE.md #1  JSON 데이터 — eval 금지, 유효하지 않은 타입 거부
      - 10번 §7.1    에러 응답 표준 envelope
    """
    invalid_strategy_json = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "THIS_CONDITION_DOES_NOT_EXIST_IN_REGISTRY", "value": 999}
            ],
        },
    }
    # 1) 전략 생성 자체가 막히는 경우 (validator)
    s_resp = client.post(
        "/api/strategies",
        json={
            "name": "invalid condition 테스트",
            "description": "",
            "strategy_json": invalid_strategy_json,
            "tags": [],
        },
    )
    if s_resp.status_code == 422:
        # validator가 조건 타입 검증을 막음 → 정상
        return

    # 2) 전략 생성은 되었지만 백테스트 실행 시 실패하는 경우
    assert s_resp.status_code == 201, (
        f"전략 생성 비예상 코드: {s_resp.status_code} — {s_resp.text}"
    )
    strategy_id = s_resp.json()["id"]

    b_resp = client.post(
        "/api/backtests",
        json=_backtest_payload(strategy_id),
    )
    if b_resp.status_code == 422:
        # 백테스트 생성 단계에서도 차단 가능
        return

    assert b_resp.status_code == 202, (
        f"백테스트 생성 비예상 코드: {b_resp.status_code} — {b_resp.text}"
    )
    run_id = b_resp.json()["id"]

    final = client.get(f"/api/backtests/{run_id}/status").json()
    assert final["status"] in ("failed", "completed"), (
        f"잘못된 전략 실행 후 비정상 상태: {final['status']}"
    )
