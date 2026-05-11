"""CsvExporter 단위 테스트 (step 035 / 052).

검증 항목:
- 09-i: symbol_performance.csv — 집계 정확성 + total_profit DESC 정렬
- 09-j: universe_history.csv — rows × symbols 전개 정확성
- 09-l: encoding 옵션 — 각 옵션으로 출력된 bytes 첫 3바이트 검증
- 09-h (step 052): trades.csv 컬럼 정합화 — entry_amount, exit_quantity,
  exit_amount, holding_days, signal_date 포함 + 값 정확성
- 09-m (step 052): ZIP 파일명 형식 — sanitize_filename / make_zip_filename

픽스처는 services/conftest.py의 db_session / user를 재사용.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.backtest import BacktestRun, BacktestStatus
from app.models.enums import TradeExecutionType
from app.models.strategy import Strategy
from app.models.trade import TradeExecution, TradeGroup
from app.models.universe_history import UniverseHistory
from app.services.csv_exporter import (
    _to_bytes,
    export_symbol_performance_csv,
    export_trades_csv,
    export_universe_history_csv,
    make_zip_filename,
    sanitize_filename,
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
        created_at=datetime.now(UTC),
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
    closed_at = datetime(2024, 2, 1 + holding_days, tzinfo=UTC)
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
        created_at=datetime.now(UTC),
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
        lines = [line for line in text.splitlines() if line.strip()]

        # 헤더 + 삼성전자 1행
        assert len(lines) == 2, f"행 수 불일치: {lines}"
        headers = lines[0].split(",")
        vals = lines[1].split(",")
        row = dict(zip(headers, vals, strict=False))

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
        lines = [line for line in text.splitlines() if line.strip()]

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
        lines = [line for line in text.splitlines() if line.strip()]
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
            created_at=datetime.now(UTC),
        )
        db_session.add(tg_open)
        db_session.commit()

        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]

        # 청산 1건만 집계 → 삼성전자 1행만
        assert len(lines) == 2, f"미청산이 포함된 것으로 보임: {lines}"
        assert "005930" in lines[1]
        assert "035420" not in lines[1]

    def test_empty_when_no_trades(self, db_session, backtest_run):
        """거래가 없으면 헤더만 있는 CSV."""
        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]
        assert len(lines) == 1  # 헤더만

    def test_avg_holding_days(self, db_session, backtest_run):
        """avg_holding_days — 보유일 평균 계산 확인."""
        rid = backtest_run.id
        # holding_days=10, 6 → 평균 8.0
        _add_trade_group(db_session, rid, "005930", "삼성전자", 70_000, 5, 50_000, 0.7, 10)
        _add_trade_group(db_session, rid, "005930", "삼성전자", 72_000, 5, 30_000, 0.4, 6)

        content = export_symbol_performance_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]
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
            created_at=datetime.now(UTC),
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
        lines = [line for line in text.splitlines() if line.strip()]

        # 헤더 + 3 데이터 행
        assert len(lines) == 4, f"헤더+3행 기대, 실제 {lines}"

    def test_expand_multi_date(self, db_session, backtest_run):
        """2개 날짜 × 2, 3종목 → 5행 전개."""
        rid = backtest_run.id
        self._add_universe(db_session, rid, date(2024, 1, 2), ["005930", "035420"])
        self._add_universe(db_session, rid, date(2024, 2, 1), ["005930", "035420", "000660"])

        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]

        # 헤더 + 2 + 3 = 6행
        assert len(lines) == 6, f"헤더+5행 기대, 실제 {lines}"

    def test_rank_increments(self, db_session, backtest_run):
        """rank 필드가 1부터 순서대로 증가."""
        rid = backtest_run.id
        symbols = ["005930", "035420", "000660"]
        self._add_universe(db_session, rid, date(2024, 1, 2), symbols)

        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]

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
        lines = [line for line in text.splitlines() if line.strip()]
        assert len(lines) == 1

    def test_date_column_format(self, db_session, backtest_run):
        """date 컬럼이 ISO 형식 (YYYY-MM-DD)."""
        rid = backtest_run.id
        as_of = date(2024, 3, 15)
        self._add_universe(db_session, rid, as_of, ["005930"])

        content = export_universe_history_csv(db_session, backtest_run, encoding="utf-8-bom")
        text = content.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]
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
            created_at=datetime.now(UTC),
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
            created_at=datetime.now(UTC),
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
            created_at=datetime.now(UTC),
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


# ─── 09-h (step 052): trades.csv 컬럼 정합화 ────────────────────────────────

def _add_trade_pair(db_session, run_id, *, symbol="005930", name="삼성전자",
                    entry_price=70_000, entry_qty=10, sell_price=77_000, sell_qty=10,
                    signal_date_val=None, exit_reason="take_profit",
                    entry_date=date(2024, 2, 1), exit_date=date(2024, 2, 16)):
    """BUY + SELL TradeExecution 한 쌍을 가진 TradeGroup 생성 헬퍼 (09-h 테스트용)."""

    closed_at = datetime(exit_date.year, exit_date.month, exit_date.day, tzinfo=UTC)
    gross_buy = entry_price * entry_qty
    gross_sell = sell_price * sell_qty
    profit = gross_sell - gross_buy
    profit_rate = round(profit / gross_buy * 100, 4)

    tg = TradeGroup(
        run_id=run_id,
        symbol=symbol,
        name=name,
        entry_date=entry_date,
        entry_price=entry_price,
        entry_quantity=entry_qty,
        remaining_quantity=0,
        fully_closed_at=closed_at,
        final_profit=profit,
        final_profit_rate=profit_rate,
        created_at=datetime.now(UTC),
    )
    db_session.add(tg)
    db_session.flush()  # tg.id 확보

    buy_ex = TradeExecution(
        trade_group_id=tg.id,
        run_id=run_id,
        execution_date=entry_date,
        signal_date=signal_date_val,
        execution_type=TradeExecutionType.BUY,
        price=entry_price,
        quantity=entry_qty,
        gross_amount=gross_buy,
        fee=0,
        tax=0,
        net_amount=gross_buy,
        realized_profit=None,
        created_at=datetime.now(UTC),
    )
    db_session.add(buy_ex)

    sell_ex = TradeExecution(
        trade_group_id=tg.id,
        run_id=run_id,
        execution_date=exit_date,
        signal_date=None,
        execution_type=TradeExecutionType.SELL,
        price=sell_price,
        quantity=sell_qty,
        gross_amount=gross_sell,
        fee=0,
        tax=0,
        net_amount=gross_sell,
        realized_profit=profit,
        exit_reason=exit_reason,
        created_at=datetime.now(UTC),
    )
    db_session.add(sell_ex)
    db_session.commit()
    db_session.refresh(tg)
    return tg


class TestTradesCsvColumns:
    """09-h: trades.csv 컬럼 존재 및 값 정확성 테스트."""

    def _parse_csv(self, content: str) -> tuple[list[str], list[dict]]:
        """UTF-8 BOM str CSV를 헤더/행 목록으로 파싱."""
        import csv as csv_mod
        import io

        # _to_csv는 BOM 문자를 포함한 str 반환
        text = content.lstrip("\ufeff")
        reader = csv_mod.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        rows = list(reader)
        return list(headers), rows

    def test_required_columns_exist(self, db_session, backtest_run):
        """09번 §5 정의 컬럼 전체가 헤더에 존재해야 한다."""
        _add_trade_pair(db_session, backtest_run.id)
        content = export_trades_csv(db_session, backtest_run)
        headers, _ = self._parse_csv(content)

        required = [
            "symbol", "name",
            "entry_date", "entry_price", "entry_quantity", "entry_amount",
            "exit_date", "exit_price", "exit_quantity", "exit_amount",
            "profit", "profit_rate", "holding_days", "exit_reason", "signal_date",
        ]
        for col in required:
            assert col in headers, f"누락 컬럼: {col!r}"

    def test_entry_amount_equals_price_times_qty(self, db_session, backtest_run):
        """entry_amount = entry_price × entry_quantity."""
        _add_trade_pair(
            db_session, backtest_run.id,
            entry_price=70_000, entry_qty=5,
        )
        content = export_trades_csv(db_session, backtest_run)
        _, rows = self._parse_csv(content)
        assert len(rows) == 1
        assert int(rows[0]["entry_amount"]) == 70_000 * 5

    def test_exit_quantity_sum_of_sell_executions(self, db_session, backtest_run):
        """exit_quantity = SELL execution 수량 합계."""
        _add_trade_pair(
            db_session, backtest_run.id,
            entry_price=70_000, entry_qty=10, sell_price=77_000, sell_qty=10,
        )
        content = export_trades_csv(db_session, backtest_run)
        _, rows = self._parse_csv(content)
        assert len(rows) == 1
        assert int(rows[0]["exit_quantity"]) == 10

    def test_exit_amount_sum_of_sell_net_amounts(self, db_session, backtest_run):
        """exit_amount = SELL execution net_amount 합계."""
        _add_trade_pair(
            db_session, backtest_run.id,
            entry_price=70_000, entry_qty=10, sell_price=77_000, sell_qty=10,
        )
        content = export_trades_csv(db_session, backtest_run)
        _, rows = self._parse_csv(content)
        # net_amount = 77_000 * 10 = 770_000 (fee=0, tax=0)
        assert int(rows[0]["exit_amount"]) == 77_000 * 10

    def test_holding_days_fully_closed(self, db_session, backtest_run):
        """holding_days = fully_closed_at - entry_date (일수)."""
        entry = date(2024, 3, 1)
        exit_ = date(2024, 3, 20)  # 19일 차이
        _add_trade_pair(
            db_session, backtest_run.id,
            entry_date=entry, exit_date=exit_,
        )
        content = export_trades_csv(db_session, backtest_run)
        _, rows = self._parse_csv(content)
        assert int(rows[0]["holding_days"]) == 19

    def test_holding_days_empty_for_open_position(self, db_session, backtest_run):
        """미청산(remaining_quantity > 0) 포지션은 holding_days 빈 문자열."""

        # 미청산 TradeGroup (SELL execution 없음, fully_closed_at=None)
        tg = TradeGroup(
            run_id=backtest_run.id,
            symbol="000660",
            name="SK하이닉스",
            entry_date=date(2024, 4, 1),
            entry_price=150_000,
            entry_quantity=5,
            remaining_quantity=5,
            fully_closed_at=None,
            final_profit=None,
            final_profit_rate=None,
            created_at=datetime.now(UTC),
        )
        db_session.add(tg)
        db_session.commit()

        content = export_trades_csv(db_session, backtest_run)
        _, rows = self._parse_csv(content)
        assert len(rows) == 1
        assert rows[0]["holding_days"] == ""

    def test_signal_date_from_buy_execution(self, db_session, backtest_run):
        """signal_date = BUY execution의 signal_date 값."""
        signal = date(2024, 2, 5)
        _add_trade_pair(
            db_session, backtest_run.id,
            signal_date_val=signal,
            entry_date=date(2024, 2, 6),
            exit_date=date(2024, 2, 20),
        )
        content = export_trades_csv(db_session, backtest_run)
        _, rows = self._parse_csv(content)
        assert rows[0]["signal_date"] == "2024-02-05"

    def test_signal_date_empty_when_null(self, db_session, backtest_run):
        """signal_date가 NULL이면 빈 문자열."""
        _add_trade_pair(
            db_session, backtest_run.id,
            signal_date_val=None,
        )
        content = export_trades_csv(db_session, backtest_run)
        _, rows = self._parse_csv(content)
        assert rows[0]["signal_date"] == ""

    def test_partial_sell_exit_quantity_aggregated(self, db_session, backtest_run):
        """부분 매도 2회 → exit_quantity = 두 PARTIAL_SELL 수량 합계."""

        entry_d = date(2024, 5, 1)
        closed_at = datetime(2024, 5, 20, tzinfo=UTC)
        tg = TradeGroup(
            run_id=backtest_run.id,
            symbol="035420",
            name="NAVER",
            entry_date=entry_d,
            entry_price=180_000,
            entry_quantity=10,
            remaining_quantity=0,
            fully_closed_at=closed_at,
            final_profit=100_000,
            final_profit_rate=5.56,
            created_at=datetime.now(UTC),
        )
        db_session.add(tg)
        db_session.flush()

        # BUY
        db_session.add(TradeExecution(
            trade_group_id=tg.id, run_id=backtest_run.id,
            execution_date=entry_d, signal_date=None,
            execution_type=TradeExecutionType.BUY,
            price=180_000, quantity=10,
            gross_amount=1_800_000, fee=0, tax=0, net_amount=1_800_000,
            created_at=datetime.now(UTC),
        ))
        # PARTIAL_SELL 1차: 5주
        db_session.add(TradeExecution(
            trade_group_id=tg.id, run_id=backtest_run.id,
            execution_date=date(2024, 5, 10), signal_date=None,
            execution_type=TradeExecutionType.PARTIAL_SELL,
            price=185_000, quantity=5,
            gross_amount=925_000, fee=0, tax=0, net_amount=925_000,
            realized_profit=25_000, exit_reason="take_profit",
            created_at=datetime.now(UTC),
        ))
        # SELL 2차: 5주
        db_session.add(TradeExecution(
            trade_group_id=tg.id, run_id=backtest_run.id,
            execution_date=date(2024, 5, 20), signal_date=None,
            execution_type=TradeExecutionType.SELL,
            price=190_000, quantity=5,
            gross_amount=950_000, fee=0, tax=0, net_amount=950_000,
            realized_profit=75_000, exit_reason="take_profit",
            created_at=datetime.now(UTC),
        ))
        db_session.commit()

        content = export_trades_csv(db_session, backtest_run)
        _, rows = self._parse_csv(content)
        assert len(rows) == 1
        assert int(rows[0]["exit_quantity"]) == 10   # 5 + 5
        # exit_amount = 925_000 + 950_000 = 1_875_000
        assert int(rows[0]["exit_amount"]) == 1_875_000

    def test_no_legacy_columns(self, db_session, backtest_run):
        """구 컬럼(trade_group_id, remaining_quantity, realized_profit_pct)은 제거."""
        _add_trade_pair(db_session, backtest_run.id)
        content = export_trades_csv(db_session, backtest_run)
        headers, _ = self._parse_csv(content)
        removed = ["trade_group_id", "remaining_quantity", "realized_profit_pct"]
        for col in removed:
            assert col not in headers, f"구 컬럼이 남아 있음: {col!r}"


# ─── 09-m (step 052): ZIP 파일명 형식 ────────────────────────────────────────

class TestSanitizeFilename:
    """sanitize_filename + make_zip_filename 단위 테스트 (09-m)."""

    def test_plain_ascii(self):
        """일반 영문 전략명 — 변화 없음."""
        assert sanitize_filename("MyStrategy") == "MyStrategy"

    def test_spaces_to_underscore(self):
        """공백 → 언더스코어."""
        assert sanitize_filename("My Strategy") == "My_Strategy"

    def test_special_chars_removed(self):
        """특수문자 제거."""
        result = sanitize_filename("전략@2024!")
        assert "@" not in result
        assert "!" not in result

    def test_consecutive_underscores_collapsed(self):
        """연속 언더스코어 → 단일."""
        result = sanitize_filename("My  Strategy")  # 공백 2개
        assert "__" not in result

    def test_leading_trailing_underscores_stripped(self):
        """앞뒤 언더스코어 제거."""
        result = sanitize_filename("  거래량돌파전략  ")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_empty_string_default(self):
        """빈 문자열 → 'strategy' 기본값."""
        assert sanitize_filename("") == "strategy"

    def test_only_special_chars_default(self):
        """특수문자만 있으면 → 'strategy' 기본값."""
        assert sanitize_filename("!!!") == "strategy"

    def test_korean_preserved(self):
        """한글 보존."""
        result = sanitize_filename("거래량돌파전략")
        assert "거래량돌파전략" in result

    def test_make_zip_filename_format(self):
        """make_zip_filename: backtest_{name}_{run_id}.zip 형식."""
        name = make_zip_filename("거래량돌파전략", 100)
        assert name.startswith("backtest_")
        assert name.endswith(".zip")
        assert "_100.zip" in name

    def test_make_zip_filename_special_chars_in_name(self):
        """전략명에 특수문자 포함 시 sanitize 적용."""
        name = make_zip_filename("전략 (2024)!", 42)
        assert "@" not in name
        assert "!" not in name
        assert "(" not in name
        assert name.endswith("_42.zip")

    def test_make_zip_filename_spaces(self):
        """전략명 공백은 언더스코어로 치환."""
        name = make_zip_filename("My Strategy", 7)
        assert "My_Strategy" in name

    def test_make_zip_filename_empty_strategy_name(self):
        """빈 전략명 → 'strategy' 기본값."""
        name = make_zip_filename("", 1)
        assert name == "backtest_strategy_1.zip"
