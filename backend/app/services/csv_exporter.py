"""CSV / ZIP Export (설계서 09번).

UTF-8 with BOM 기본 (Excel 호환). KRW 통화는 정수.

encoding 옵션 (09-l):
    "utf-8-bom"  (기본값) — UTF-8 with BOM, Excel 한글 호환
    "utf-8"       — BOM 없는 UTF-8
    "cp949"       — EUC-KR 계열, 구형 Excel 호환
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from typing import Literal
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.backtest import BacktestRun
from app.models.cash_event import CashEvent
from app.models.daily_equity import DailyEquity
from app.models.trade import TradeExecution, TradeGroup
from app.models.universe_history import UniverseHistory

# 지원 encoding 리터럴
CsvEncoding = Literal["utf-8-bom", "utf-8", "cp949"]

UTF8_BOM = "\ufeff"  # BOM 문자 (U+FEFF)

# encoding → (Python codec, BOM prefix bytes)
_ENCODING_MAP: dict[str, tuple[str, bytes]] = {
    "utf-8-bom": ("utf-8", b"\xef\xbb\xbf"),
    "utf-8": ("utf-8", b""),
    "cp949": ("cp949", b""),
}


def _to_bytes(rows: list[dict], fieldnames: list[str], encoding: CsvEncoding = "utf-8-bom") -> bytes:
    """CSV를 지정 encoding으로 인코딩한 bytes 반환.

    - "utf-8-bom": BOM(EF BB BF) + UTF-8 본문
    - "utf-8": BOM 없는 UTF-8
    - "cp949": CP949 인코딩 (구형 Excel)
    """
    codec, bom = _ENCODING_MAP.get(encoding, _ENCODING_MAP["utf-8-bom"])

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})

    body = buf.getvalue().encode(codec)
    return bom + body


def _to_csv(rows: list[dict], fieldnames: list[str]) -> str:
    """기존 호환: UTF-8 BOM 포함 str 반환."""
    buf = io.StringIO()
    buf.write(UTF8_BOM)
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def export_summary_csv(session: Session, run: BacktestRun) -> str:
    result = run.result
    row = {
        "run_id": run.id,
        "strategy_id": run.strategy_id,
        "run_name": run.run_name,
        "start_date": run.start_date.isoformat(),
        "end_date": run.end_date.isoformat(),
        "initial_cash": run.initial_cash,
        "final_equity": result.final_equity if result else "",
        "total_return_pct": result.total_return_pct if result else "",
        "annual_return_pct": result.annual_return_pct if result else "",
        "mdd_pct": result.mdd_pct if result else "",
        "trade_count": result.trade_count if result else 0,
        "win_rate": result.win_rate if result else "",
        "avg_holding_days": result.avg_holding_days if result else "",
        "profit_factor": result.profit_factor if result else "",
        "status": run.status.value,
    }
    return _to_csv([row], list(row.keys()))


def export_trades_csv(session: Session, run: BacktestRun) -> str:
    """trades.csv — 09번 §5 컬럼 전체 포함 (09-h).

    컬럼 정의:
        symbol, name, entry_date, entry_price, entry_quantity, entry_amount,
        exit_date, exit_price, exit_quantity, exit_amount,
        profit, profit_rate, holding_days, exit_reason, signal_date
    """
    rows = []
    tgs = (
        session.query(TradeGroup)
        .filter_by(run_id=run.id)
        .order_by(TradeGroup.entry_date.asc(), TradeGroup.id.asc())
        .all()
    )
    for tg in tgs:
        execs = (
            session.query(TradeExecution)
            .filter_by(trade_group_id=tg.id)
            .order_by(TradeExecution.execution_date.asc(), TradeExecution.id.asc())
            .all()
        )

        # BUY execution — signal_date 추출 (첫 BUY)
        buy_exec = next((e for e in execs if e.execution_type.value == "BUY"), None)
        signal_date_val = ""
        if buy_exec is not None and buy_exec.signal_date is not None:
            signal_date_val = buy_exec.signal_date.isoformat()

        # SELL/PARTIAL_SELL executions — exit 관련 집계
        sell_execs = [e for e in execs if e.execution_type.value != "BUY"]
        last_sell = sell_execs[-1] if sell_execs else None

        exit_quantity = sum(e.quantity for e in sell_execs) if sell_execs else ""
        exit_amount = sum(e.net_amount for e in sell_execs) if sell_execs else ""

        # entry_amount = entry_price × entry_quantity (매수 총 비용 개념: gross)
        entry_amount = tg.entry_price * tg.entry_quantity

        # holding_days = fully_closed_at(date) - entry_date (완전 청산 시만)
        holding_days = ""
        if tg.fully_closed_at is not None:
            closed_date = (
                tg.fully_closed_at.date()
                if hasattr(tg.fully_closed_at, "date")
                else tg.fully_closed_at
            )
            holding_days = (closed_date - tg.entry_date).days

        rows.append({
            "symbol": tg.symbol,
            "name": tg.name,
            "entry_date": tg.entry_date.isoformat(),
            "entry_price": tg.entry_price,
            "entry_quantity": tg.entry_quantity,
            "entry_amount": entry_amount,
            "exit_date": last_sell.execution_date.isoformat() if last_sell else "",
            "exit_price": last_sell.price if last_sell else "",
            "exit_quantity": exit_quantity,
            "exit_amount": exit_amount,
            "profit": tg.final_profit if tg.final_profit is not None else "",
            "profit_rate": tg.final_profit_rate if tg.final_profit_rate is not None else "",
            "holding_days": holding_days,
            "exit_reason": last_sell.exit_reason if last_sell else "",
            "signal_date": signal_date_val,
        })
    return _to_csv(rows, [
        "symbol", "name",
        "entry_date", "entry_price", "entry_quantity", "entry_amount",
        "exit_date", "exit_price", "exit_quantity", "exit_amount",
        "profit", "profit_rate", "holding_days", "exit_reason", "signal_date",
    ])


def export_daily_equity_csv(session: Session, run: BacktestRun) -> str:
    rows = (
        session.query(DailyEquity)
        .filter_by(run_id=run.id)
        .order_by(DailyEquity.date.asc(), DailyEquity.id.asc())
        .all()
    )
    return _to_csv(
        [
            {
                "date": eq.date.isoformat(),
                "cash": eq.cash,
                "stock_value": eq.stock_value,
                "total_equity": eq.total_equity,
                "drawdown_pct": eq.drawdown,
                "positions_count": eq.positions_count,
            }
            for eq in rows
        ],
        ["date", "cash", "stock_value", "total_equity", "drawdown_pct", "positions_count"],
    )


def export_cash_events_csv(session: Session, run: BacktestRun) -> str:
    rows = (
        session.query(CashEvent)
        .filter_by(run_id=run.id)
        .order_by(CashEvent.date.asc(), CashEvent.id.asc())
        .all()
    )
    return _to_csv(
        [
            {
                "date": ev.date.isoformat(),
                "event_type": ev.event_type,
                "cash_before": ev.cash_before,
                "required_cash": ev.required_cash if ev.required_cash is not None else "",
                "cash_after": ev.cash_after,
                "action": ev.action or "",
                "symbol": ev.symbol or "",
                "sell_quantity": ev.sell_quantity if ev.sell_quantity is not None else "",
                "sell_amount": ev.sell_amount if ev.sell_amount is not None else "",
                "reason": ev.reason or "",
            }
            for ev in rows
        ],
        ["date", "event_type", "cash_before", "required_cash", "cash_after",
         "action", "symbol", "sell_quantity", "sell_amount", "reason"],
    )


def export_symbol_performance_csv(
    session: Session,
    run: BacktestRun,
    encoding: CsvEncoding = "utf-8-bom",
) -> bytes:
    """종목별 성과 집계 CSV (09번 §7, 09-i).

    trade_groups를 symbol 기준으로 집계:
        - trade_count: 완전 청산된 TradeGroup 수 (remaining_quantity == 0)
        - win_count: final_profit > 0 인 건수
        - win_rate: win_count / trade_count * 100 (%, 소수 첫째)
        - total_profit: final_profit 합계 (KRW 정수)
        - avg_profit_rate: final_profit_rate 평균 (%, 소수 둘째)
        - max_profit_rate: final_profit_rate 최대
        - max_loss_rate: final_profit_rate 최소 (음수)
        - avg_holding_days: 보유일 평균 (소수 첫째)

    정렬: total_profit DESC (09번 §7 명시)
    미청산 TradeGroup(remaining_quantity > 0)은 집계에서 제외.
    """
    tgs = (
        session.query(TradeGroup)
        .filter(
            TradeGroup.run_id == run.id,
            TradeGroup.remaining_quantity == 0,  # 완전 청산된 건만
        )
        .order_by(TradeGroup.symbol.asc(), TradeGroup.id.asc())
        .all()
    )

    # symbol별로 집계
    perf: dict[str, dict] = {}
    for tg in tgs:
        sym = tg.symbol
        if sym not in perf:
            perf[sym] = {
                "symbol": sym,
                "name": tg.name,
                "trade_count": 0,
                "win_count": 0,
                "total_profit": 0,
                "_profit_rates": [],
                "_holding_days": [],
            }
        bucket = perf[sym]
        bucket["trade_count"] += 1
        profit = tg.final_profit or 0
        bucket["total_profit"] += profit
        if profit > 0:
            bucket["win_count"] += 1
        if tg.final_profit_rate is not None:
            bucket["_profit_rates"].append(tg.final_profit_rate)

        # 보유일 계산: fully_closed_at(date 부분) - entry_date
        if tg.fully_closed_at is not None:
            closed_date = tg.fully_closed_at.date() if hasattr(tg.fully_closed_at, "date") else tg.fully_closed_at
            holding = (closed_date - tg.entry_date).days
            bucket["_holding_days"].append(holding)

    rows: list[dict] = []
    for bucket in perf.values():
        tc = bucket["trade_count"]
        wc = bucket["win_count"]
        rates = bucket["_profit_rates"]
        holding = bucket["_holding_days"]
        rows.append({
            "symbol": bucket["symbol"],
            "name": bucket["name"],
            "trade_count": tc,
            "win_rate": round(wc / tc * 100, 1) if tc > 0 else 0.0,
            "total_profit": int(bucket["total_profit"]),
            "avg_profit_rate": round(sum(rates) / len(rates), 2) if rates else 0.0,
            "max_profit_rate": round(max(rates), 2) if rates else 0.0,
            "max_loss_rate": round(min(rates), 2) if rates else 0.0,
            "avg_holding_days": round(sum(holding) / len(holding), 1) if holding else 0.0,
        })

    # total_profit DESC 정렬
    rows.sort(key=lambda r: r["total_profit"], reverse=True)

    fieldnames = [
        "symbol", "name", "trade_count", "win_rate",
        "total_profit", "avg_profit_rate", "max_profit_rate",
        "max_loss_rate", "avg_holding_days",
    ]
    return _to_bytes(rows, fieldnames, encoding)


def export_universe_history_csv(
    session: Session,
    run: BacktestRun,
    encoding: CsvEncoding = "utf-8-bom",
) -> bytes:
    """유니버스 이력 CSV (09번 §9, 09-j).

    universe_history 테이블에서 run_id 기준으로 조회하고,
    symbols_json(list[str])을 행 단위로 전개: (date, symbol) 1:N.

    출력 컬럼: date, market, selection_method, rank, symbol
        - symbol_name, market_cap, trading_value는 현재 UniverseHistory 모델에
          없으므로 빈 값("")으로 출력.
        - rank는 symbols_json 내 0-base 인덱스 + 1 (저장 시 ASC 정렬이므로
          순위는 알 수 없음 — index 순서로 표시).
    """
    histories = (
        session.query(UniverseHistory)
        .filter(UniverseHistory.run_id == run.id)
        .order_by(UniverseHistory.as_of_date.asc(), UniverseHistory.id.asc())
        .all()
    )

    rows: list[dict] = []
    for hist in histories:
        symbols: list[str] = hist.symbols_json or []
        for rank, symbol in enumerate(symbols, start=1):
            rows.append({
                "date": hist.as_of_date.isoformat(),
                "market": hist.market,
                "selection_method": hist.selection_method,
                "rank": rank,
                "symbol": symbol,
                "name": "",          # 모델에 없음 — 빈 값
                "market_cap": "",    # 모델에 없음 — 빈 값
                "trading_value": "", # 모델에 없음 — 빈 값
            })

    fieldnames = [
        "date", "market", "selection_method", "rank",
        "symbol", "name", "market_cap", "trading_value",
    ]
    return _to_bytes(rows, fieldnames, encoding)


def export_strategy_snapshot_json(run: BacktestRun) -> str:
    return json.dumps(run.strategy_snapshot_json, ensure_ascii=False, indent=2)


def sanitize_filename(name: str) -> str:
    """전략명을 ZIP 파일명에 사용 가능한 URL-safe 문자열로 변환 (09-m).

    처리 순서:
        1. 공백 → 언더스코어
        2. 알파벳·숫자·한글·언더스코어·하이픈 이외 문자 제거
        3. 연속 언더스코어 → 단일 언더스코어
        4. 앞뒤 언더스코어 제거
        5. 빈 문자열이면 "strategy" 기본값 반환
    """
    s = name.strip()
    s = s.replace(" ", "_")
    # 알파벳(대소문자), 숫자, 한글, 언더스코어, 하이픈만 허용
    s = re.sub(r"[^\w\-]", "", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    return s if s else "strategy"


def make_zip_filename(strategy_name: str, run_id: int) -> str:
    """ZIP 파일명 생성: backtest_{strategy_name}_{run_id}.zip (09-m)."""
    safe_name = sanitize_filename(strategy_name)
    return f"backtest_{safe_name}_{run_id}.zip"


def make_content_disposition(filename: str) -> str:
    """HTTP Content-Disposition 헤더 값 생성 (RFC 5987).

    파일명에 non-ASCII(한글 등) 포함 시 latin-1 인코딩이 실패하므로
    RFC 5987 형식 (filename*=UTF-8''<percent-encoded>) 사용.
    ASCII 호환 폴백 파일명 (filename=) 도 함께 제공해 구형 클라이언트 지원.

    ASCII 범위만 사용하는 파일명은 단순 filename= 형식 반환.
    """
    try:
        filename.encode("ascii")
        # ASCII 안전 — 단순 형식
        return f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        # non-ASCII 포함 — RFC 5987 percent-encoding
        encoded = quote(filename, safe="")
        # 폴백 ASCII 파일명 (한글 제거 → ASCII만 남김)
        ascii_fallback = re.sub(r"[^\x20-\x7e]", "_", filename).strip("_") or "download"
        return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def export_zip(session: Session, run: BacktestRun) -> bytes:
    """7개 파일 + strategy_snapshot.json을 ZIP으로 묶음 (09-k)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.csv", export_summary_csv(session, run))
        zf.writestr("trades.csv", export_trades_csv(session, run))
        zf.writestr("daily_equity.csv", export_daily_equity_csv(session, run))
        zf.writestr("cash_events.csv", export_cash_events_csv(session, run))
        zf.writestr(
            "symbol_performance.csv",
            export_symbol_performance_csv(session, run, encoding="utf-8-bom"),
        )
        zf.writestr(
            "universe_history.csv",
            export_universe_history_csv(session, run, encoding="utf-8-bom"),
        )
        zf.writestr(
            "strategy_snapshot.json",
            export_strategy_snapshot_json(run),
        )
    return buf.getvalue()
