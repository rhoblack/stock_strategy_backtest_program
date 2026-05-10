"""CsvExporter 단위 테스트 (step 035).

검증 항목:
- 09-i: symbol_performance.csv — 집계 정확성 + total_profit DESC 정렬
- 09-j: universe_history.csv — rows × symbols 전개 정확성
- 09-l: encoding 옵션 — 각 옵션으로 출력된 bytes 첫 3바이트 검증

픽스처는 services/conftest.py의 db_session / user를 재사용.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.backtest import BacktestRun, BacktestStatus
from app.models.strategy import Strategy
from app.models.trade import TradeExecution, TradeGroup
from app.models.enums import TradeExecutionType
from app.models.universe_history import UniverseHistory
from app.services.csv_exporter import (
    export_symbol_performance_csv,
    export_universe_history_csv,
    _to_bytes,
)


# ─── 공통 픽스처 ────────────────────────────────────────────────────────────

@pytest.fixture
def db_engine():
    from app.db.session import create_db_engine, drop_db, init_db
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    yield engine
    drop_db(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    from app.db.session import make_session_factory
    SessionLocal = make_session_factory(db_engine)
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user(db_session):
    from app.models.user import User
    u = User(email="tester@example.com")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def strategy(db_session, user):
    s = Strategy(
        user_id=user.id,
        name="테스트전략",
        strategy_json={
            "entry": {"logic": "AND", "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}]},
            "exit_position": {"logic": "OR", "conditions": [{"type": "take_profit", "percent": 5.0}]},
        },
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture
def backtest_run(db_session, user, strategy):
    run = BacktestRun(
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="TEST",
        strategy_snapshot_json=strategy.strategy_json,
        universe_config_json={},
        start_date=date(2024, 1, 2),
        end_date=date(2024, 12, 31),
        initial_cash=10_000_000,
        fee_rate=0.0,
        tax_rate_json=0.0,
        slippage=0.0,
        status=BacktestStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


# ─── 헬퍼 ───────────────────────────────────────────────────────────────────

def _add_trade_group(db_session, run_id, symbol, name, entry_price, entry_qty,
                     final_profit, final_profit_rate, holding_days=5):
    """완전 청산 TradeGroup 생성 헬퍼."""
    entry_dt = date(2024, 2, 1)
    closed_at = datetime(2024, 2, 1 + holding_days, tzinfo=timezone.utc)
    tg = TradeGroup(
        run_id=run_id,
        symbol=symbol,
        name=name,
        entry_date=entry_dt,
        entry_price=entry_price,
        entry_quantity=entry_qty,
        remaining_quantity=0,          # 완전 청산
        fully_closed_at=closed_at,
        final_profit=final_profit,
        final_profit_rate=final_profit_rate,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(tg)
    db_session.commit()
    db_session.refresh(tg)
    return tg


# ─── 09-i: symbol_performance.csv 집계 정확성 ──────────────────────────────

class TestSymbolPerformanceCsv:
    """symbol_performance.csv 집계 정확성 테스트."""

    def test_aggregation_basic(self, db_session, backtest_run):
        """단일 종목 2건 청산 — trade_count / win_count / total_profit 집계."""
        rid = backtest_run.id
        # 삼성전자 2건: 이익 50만, 손실 -20만
        _add_trade_group(db_session, rid, "005930", "삼성전자", 70_000, 7, 500_000, 7.1, 10)
        _add_trade_group(db_session, rid, "005930", "삼성전자", 75_000, 7, -200_000, -2.7, 3)

        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]

        # 헤더 + 삼성전자 1행
        assert len(lines) == 2, f"행 수 불일치: {lines}"
        headers = lines[0].split(",")
        vals = lines[1].split(",")
        row = dict(zip(headers, vals))

        assert row["symbol"] == "005930"
        assert int(row["trade_count"]) == 2
        assert int(row["total_profit"]) == 300_000   # 500k + (-200k)
        # win_count=1 → win_rate=50.0
        assert float(row["win_rate"]) == 50.0

    def test_aggregation_multi_symbol(self, db_session, backtest_run):
        """두 종목 — 각각 집계 후 total_profit DESC 정렬."""
        rid = backtest_run.id
        # NAVER: 1건 -10만 (손실)
        _add_trade_group(db_session, rid, "035420", "NAVER", 180_000, 3, -100_000, -1.8, 4)
        # 삼성전자: 1건 80만 (이익)
        _add_trade_group(db_session, rid, "005930", "삼성전자", 70_000, 10, 800_000, 11.4, 7)

        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]

        assert len(lines) == 3  # 헤더 + 2 종목
        headers = lines[0].split(",")
        tp_idx = headers.index("total_profit")
        # 첫 번째 데이터 행이 큰 total_profit (삼성전자 80만)
        first_profit = int(lines[1].split(",")[tp_idx])
        second_profit = int(lines[2].split(",")[tp_idx])
        assert first_profit >= second_profit, "total_profit DESC 정렬 위반"
        assert first_profit == 800_000
        assert second_profit == -100_000

    def test_total_profit_is_int_no_decimal(self, db_session, backtest_run):
        """total_profit이 정수 — 소수점 없음."""
        rid = backtest_run.id
        _add_trade_group(db_session, rid, "005930", "삼성전자", 70_000, 5, 123_456, 1.76, 5)

        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]
        headers = lines[0].split(",")
        tp_idx = headers.index("total_profit")
        tp_val = lines[1].split(",")[tp_idx]
        assert "." not in tp_val, f"소수점 발견: {tp_val!r}"
        assert int(tp_val) == 123_456

    def test_open_positions_excluded(self, db_session, backtest_run):
        """미청산(remaining_quantity > 0) TradeGroup은 집계에서 제외."""
        rid = backtest_run.id
        # 청산 1건
        _add_trade_group(db_session, rid, "005930", "삼성전자", 70_000, 5, 100_000, 1.4, 5)
        # 미청산 1건 (remaining_quantity = 3)
        tg_open = TradeGroup(
            run_id=rid,
            symbol="035420",
            name="NAVER",
            entry_date=date(2024, 3, 1),
            entry_price=180_000,
            entry_quantity=3,
            remaining_quantity=3,   # 미청산
            final_profit=None,
            final_profit_rate=None,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(tg_open)
        db_session.commit()

        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]

        # 청산 1건만 집계 → 삼성전자 1행만
        assert len(lines) == 2, f"미청산이 포함된 것으로 보임: {lines}"
        assert "005930" in lines[1]
        assert "035420" not in lines[1]

    def test_empty_when_no_trades(self, db_session, backtest_run):
        """거래가 없으면 헤더만 있는 CSV."""
        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]
        assert len(lines) == 1  # 헤더만

    def test_avg_holding_days(self, db_session, backtest_run):
        """avg_holding_days — 보유일 평균 계산 확인."""
        rid = backtest_run.id
        # holding_days=10, 6 → 평균 8.0
        _add_trade_group(db_session, rid, "005930", "삼성전자", 70_000, 5, 50_000, 0.7, 10)
        _add_trade_group(db_session, rid, "005930", "삼성전자", 72_000, 5, 30_000, 0.4, 6)

        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]
        headers = lines[0].split(",")
        hd_idx = headers.index("avg_holding_days")
        avg_hd = float(lines[1].split(",")[hd_idx])
        assert avg_hd == 8.0, f"avg_holding_days 기대 8.0, 실제 {avg_hd}"


# ─── 09-j: universe_history.csv 전개 정확성 ──────────────────────────────

class TestUniverseHistoryCsv:
    """universe_history.csv — rows × symbols 전개 정확성."""

    def _add_universe(self, db_session, run_id, as_of_date, symbols):
        uh = UniverseHistory(
            run_id=run_id,
            as_of_date=as_of_date,
            market="KOSPI",
            selection_method="MARKET_CAP_TOP_N",
            config_json={"top_n": len(symbols)},
            config_hash=None,
            symbols_json=symbols,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(uh)
        db_session.commit()
        db_session.refresh(uh)
        return uh

    def test_expand_single_date(self, db_session, backtest_run):
        """1개 날짜 × 3종목 → 3행 전개."""
        rid = backtest_run.id
        symbols = ["005930", "035420", "000660"]
        self._add_universe(db_session, rid, date(2024, 1, 2), symbols)

        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]

        # 헤더 + 3 데이터 행
        assert len(lines) == 4, f"헤더+3행 기대, 실제 {lines}"

    def test_expand_multi_date(self, db_session, backtest_run):
        """2개 날짜 × 2, 3종목 → 5행 전개."""
        rid = backtest_run.id
        self._add_universe(db_session, rid, date(2024, 1, 2), ["005930", "035420"])
        self._add_universe(db_session, rid, date(2024, 2, 1), ["005930", "035420", "000660"])

        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]

        # 헤더 + 2 + 3 = 6행
        assert len(lines) == 6, f"헤더+5행 기대, 실제 {lines}"

    def test_rank_increments(self, db_session, backtest_run):
        """rank 필드가 1부터 순서대로 증가."""
        rid = backtest_run.id
        symbols = ["005930", "035420", "000660"]
        self._add_universe(db_session, rid, date(2024, 1, 2), symbols)

        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]

        headers = lines[0].split(",")
        rank_idx = headers.index("rank")
        sym_idx = headers.index("symbol")
        for expected_rank, expected_sym in enumerate(symbols, start=1):
            vals = lines[expected_rank].split(",")
            assert int(vals[rank_idx]) == expected_rank
            assert vals[sym_idx] == expected_sym

    def test_empty_when_no_universe(self, db_session, backtest_run):
        """universe_history 없으면 헤더만."""
        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]
        assert len(lines) == 1

    def test_date_column_format(self, db_session, backtest_run):
        """date 컬럼이 ISO 형식 (YYYY-MM-DD)."""
        rid = backtest_run.id
        as_of = date(2024, 3, 15)
        self._add_universe(db_session, rid, as_of, ["005930"])

        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]
        headers = lines[0].split(",")
        date_idx = headers.index("date")
        date_val = lines[1].split(",")[date_idx]
        assert date_val == "2024-03-15"

    def test_only_own_run_data(self, db_session, backtest_run, user, strategy):
        """다른 run_id의 UniverseHistory는 포함하지 않음."""
        # 다른 BacktestRun 생성
        other_run = BacktestRun(
            user_id=user.id,
            strategy_id=strategy.id,
            run_name="OTHER",
            strategy_snapshot_json=strategy.strategy_json,
            universe_config_json={},
            start_date=date(2024, 1, 2),
            end_date=date(2024, 12, 31),
            initial_cash=10_000_000,
            fee_rate=0.0,
            tax_rate_json=0.0,
            slippage=0.0,
            status=BacktestStatus.COMPLETED,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(other_run)
        db_session.commit()
        db_session.refresh(other_run)

        # 다른 run의 universe
        other_uh = UniverseHistory(
            run_id=other_run.id,
            as_of_date=date(2024, 1, 2),
            market="KOSPI",
            selection_method="ALL",
            config_json={},
            symbols_json=["999999"],  # 구별용 심볼
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(other_uh)
        # 현재 run의 universe
        own_uh = UniverseHistory(
            run_id=backtest_run.id,
            as_of_date=date(2024, 2, 1),
            market="KOSPI",
            selection_method="ALL",
            config_json={},
            symbols_json=["005930"],
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(own_uh)
        db_session.commit()

        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        assert "999999" not in text, "다른 run의 symbol이 포함되면 안 됨"
        assert "005930" in text


# ─── 09-l: encoding 옵션 — bytes 첫 3바이트 검증 ────────────────────────────

class TestEncodingOption:
    """encoding 옵션별 출력 bytes 첫 3바이트 검증."""

    def _sample_rows(self):
        return [{"symbol": "005930", "name": "삼성전자", "trade_count": 1,
                 "win_rate": 100.0, "total_profit": 100000,
                 "avg_profit_rate": 1.0, "max_profit_rate": 1.0,
                 "max_loss_rate": 1.0, "avg_holding_days": 5.0}]

    _fieldnames = ["symbol", "name", "trade_count", "win_rate",
                   "total_profit", "avg_profit_rate", "max_profit_rate",
                   "max_loss_rate", "avg_holding_days"]

    def test_utf8_bom_first_3bytes(self):
        """utf-8-bom → 첫 3바이트 EF BB BF."""
        result = _to_bytes(self._sample_rows(), self._fieldnames, encoding="utf-8-bom")
        assert result[:3] == b"\xef\xbb\xbf", f"BOM 기대값 EF BB BF, 실제 {result[:3].hex()}"

    def test_utf8_no_bom_first_3bytes(self):
        """utf-8 → BOM 없음 — 첫 3바이트가 EF BB BF 아님."""
        result = _to_bytes(self._sample_rows(), self._fieldnames, encoding="utf-8")
        assert result[:3] != b"\xef\xbb\xbf", "BOM이 없어야 함"
        # 첫 바이트가 's'(symbol 헤더 시작) — ASCII 범위 내
        text = result.decode("utf-8")
        assert text.startswith("symbol")

    def test_cp949_no_bom_first_3bytes(self):
        """cp949 → BOM 없음."""
        result = _to_bytes(self._sample_rows(), self._fieldnames, encoding="cp949")
        assert result[:3] != b"\xef\xbb\xbf"
        # CP949 디코딩 가능
        text = result.decode("cp949")
        assert "삼성전자" in text

    def test_utf8_bom_decodable_as_utf8_sig(self):
        """utf-8-bom 출력이 utf-8-sig로 디코딩 가능."""
        result = _to_bytes(self._sample_rows(), self._fieldnames, encoding="utf-8-bom")
        text = result.decode("utf-8-sig")
        assert "삼성전자" in text

    def test_empty_rows_utf8_bom(self):
        """빈 rows여도 BOM + 헤더만 출력."""
        result = _to_bytes([], self._fieldnames, encoding="utf-8-bom")
        assert result[:3] == b"\xef\xbb\xbf"
        text = result.decode("utf-8-sig")
        assert "symbol" in text
