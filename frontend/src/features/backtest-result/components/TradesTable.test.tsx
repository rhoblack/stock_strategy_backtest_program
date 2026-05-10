import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import TradesTable from "./TradesTable";
import type { TradeGroupOut } from "../../../api/backtests";

function makeTg(overrides: Partial<TradeGroupOut> = {}): TradeGroupOut {
  return {
    trade_group_id: 1,
    symbol: "GOLDEN",
    name: "골든종목",
    entry_date: "2024-01-12",
    entry_price: 9760,
    entry_quantity: 512,
    remaining_quantity: 0,
    fully_closed_at: "2024-01-19T00:00:00",
    final_profit: 50_000,
    final_profit_rate: 5.12,
    executions: [
      {
        execution_date: "2024-01-12",
        execution_type: "BUY",
        price: 9760,
        quantity: 512,
        realized_profit: null,
        exit_reason: null,
      },
      {
        execution_date: "2024-01-19",
        execution_type: "SELL",
        price: 10248,
        quantity: 512,
        realized_profit: 50_000,
        exit_reason: "take_profit",
      },
    ],
    ...overrides,
  };
}

const items: TradeGroupOut[] = [
  makeTg({ trade_group_id: 1, symbol: "GOLDEN", entry_date: "2024-01-12" }),
  makeTg({
    trade_group_id: 2,
    symbol: "ALPHA",
    name: "알파종목",
    entry_date: "2024-02-01",
    entry_price: 5000,
    entry_quantity: 100,
    final_profit: -10_000,
    final_profit_rate: -2.5,
    fully_closed_at: null,
    executions: [
      {
        execution_date: "2024-02-01",
        execution_type: "BUY",
        price: 5000,
        quantity: 100,
        realized_profit: null,
        exit_reason: null,
      },
      {
        execution_date: "2024-02-10",
        execution_type: "SELL",
        price: 4900,
        quantity: 100,
        realized_profit: -10_000,
        exit_reason: "stop_loss",
      },
    ],
  }),
  makeTg({
    trade_group_id: 3,
    symbol: "BETA",
    name: "베타종목",
    entry_date: "2024-03-01",
    final_profit: null,
    final_profit_rate: null,
    fully_closed_at: null,
    executions: [
      {
        execution_date: "2024-03-01",
        execution_type: "BUY",
        price: 7000,
        quantity: 200,
        realized_profit: null,
        exit_reason: null,
      },
    ],
  }),
];

describe("TradesTable", () => {
  it("기본 정렬: entry_date ASC (결정론)", () => {
    render(<TradesTable items={items} />);
    const rows = screen.getAllByTestId(/^trade-row-/);
    // 1(2024-01-12) → 2(2024-02-01) → 3(2024-03-01)
    expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual([
      "trade-row-1",
      "trade-row-2",
      "trade-row-3",
    ]);
  });

  it("종목 컬럼 클릭 시 정렬 방향 토글", () => {
    render(<TradesTable items={items} />);
    const symbolHeader = screen.getByTestId("th-symbol");
    fireEvent.click(symbolHeader); // ASC
    let rows = screen.getAllByTestId(/^trade-row-/);
    // ALPHA(2) → BETA(3) → GOLDEN(1)
    expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual([
      "trade-row-2",
      "trade-row-3",
      "trade-row-1",
    ]);
    fireEvent.click(symbolHeader); // DESC
    rows = screen.getAllByTestId(/^trade-row-/);
    expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual([
      "trade-row-1",
      "trade-row-3",
      "trade-row-2",
    ]);
  });

  it("필터 입력 시 매칭 행만 표시", () => {
    render(<TradesTable items={items} />);
    const filter = screen.getByTestId("trades-filter") as HTMLInputElement;
    fireEvent.change(filter, { target: { value: "ALPHA" } });
    const rows = screen.getAllByTestId(/^trade-row-/);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveAttribute("data-testid", "trade-row-2");
  });

  it("매도 사유로도 필터됨", () => {
    render(<TradesTable items={items} />);
    const filter = screen.getByTestId("trades-filter") as HTMLInputElement;
    fireEvent.change(filter, { target: { value: "stop_loss" } });
    const rows = screen.getAllByTestId(/^trade-row-/);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveAttribute("data-testid", "trade-row-2");
  });

  it("페이징: pageSize를 10으로 두고 11개를 넣으면 다음 페이지 버튼 활성", () => {
    const many: TradeGroupOut[] = Array.from({ length: 30 }, (_, i) =>
      makeTg({
        trade_group_id: i + 100,
        symbol: `S${String(i).padStart(3, "0")}`,
        entry_date: `2024-01-${String((i % 28) + 1).padStart(2, "0")}`,
      }),
    );
    render(<TradesTable items={many} />);
    const pageSize = screen.getByTestId("page-size") as HTMLSelectElement;
    fireEvent.change(pageSize, { target: { value: "10" } });
    expect(screen.getAllByTestId(/^trade-row-/)).toHaveLength(10);
    const next = screen.getByTestId("page-next");
    expect(next).not.toBeDisabled();
    fireEvent.click(next);
    expect(screen.getAllByTestId(/^trade-row-/)).toHaveLength(10);
  });

  it("행 클릭 시 onRowClick 콜백 호출 (entryDate, exitDate 포함)", () => {
    const handle = vi.fn();
    render(<TradesTable items={items} onRowClick={handle} />);
    fireEvent.click(screen.getByTestId("trade-row-1"));
    expect(handle).toHaveBeenCalledTimes(1);
    const arg = handle.mock.calls[0][0];
    expect(arg.tradeGroup.symbol).toBe("GOLDEN");
    expect(arg.entryDate).toBe("2024-01-12");
    expect(arg.exitDate).toBe("2024-01-19");
  });

  it("보유 중(SELL 없음) 행은 exitDate가 null로 전달됨", () => {
    const handle = vi.fn();
    render(<TradesTable items={items} onRowClick={handle} />);
    fireEvent.click(screen.getByTestId("trade-row-3"));
    const arg = handle.mock.calls[0][0];
    expect(arg.exitDate).toBeNull();
  });

  it("수익률 색상: 양수=빨강, 음수=파랑", () => {
    render(<TradesTable items={items} />);
    const row1 = screen.getByTestId("trade-row-1");
    const row2 = screen.getByTestId("trade-row-2");
    expect(within(row1).getByText("+5.12%")).toBeInTheDocument();
    expect(within(row2).getByText("-2.50%")).toBeInTheDocument();
  });

  it("일치하는 거래가 없을 때 안내 메시지", () => {
    render(<TradesTable items={items} />);
    const filter = screen.getByTestId("trades-filter") as HTMLInputElement;
    fireEvent.change(filter, { target: { value: "ZZZ존재하지않음" } });
    expect(screen.getByText("일치하는 거래가 없습니다.")).toBeInTheDocument();
  });
});
