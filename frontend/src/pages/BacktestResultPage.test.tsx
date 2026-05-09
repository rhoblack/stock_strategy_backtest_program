import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import BacktestResultPage from "./BacktestResultPage";
import {
  useBacktestStatus,
  useBacktestSummary,
  useBacktestTrades,
  useDailyEquity,
} from "../api/backtests";

vi.mock("../api/backtests", () => ({
  useBacktestStatus: vi.fn(),
  useBacktestSummary: vi.fn(),
  useBacktestTrades: vi.fn(),
  useDailyEquity: vi.fn(),
}));

const useStatusMock = vi.mocked(useBacktestStatus);
const useSummaryMock = vi.mocked(useBacktestSummary);
const useTradesMock = vi.mocked(useBacktestTrades);
const useEquityMock = vi.mocked(useDailyEquity);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/backtests/42"]}>
        <Routes>
          <Route path="/backtests/:runId" element={<BacktestResultPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BacktestResultPage", () => {
  beforeEach(() => {
    useStatusMock.mockReset();
    useSummaryMock.mockReset();
    useTradesMock.mockReset();
    useEquityMock.mockReset();

    useStatusMock.mockReturnValue({
      data: {
        id: 42,
        user_id: 1,
        strategy_id: 1,
        run_name: "x",
        status: "completed",
        progress_pct: 100,
        error_message: null,
        created_at: "",
        started_at: null,
        finished_at: null,
      },
    } as ReturnType<typeof useBacktestStatus>);

    useSummaryMock.mockReturnValue({
      data: {
        run_id: 42,
        status: "completed",
        progress_pct: 100,
        started_at: null,
        finished_at: null,
        error_message: null,
        summary: {
          initial_cash: 10_000_000,
          final_equity: 10_188_570,
          total_return_pct: 1.8857,
          annual_return_pct: 7.96,
          mdd_pct: -4.9,
          trade_count: 8,
          open_position_count: 1,
          win_rate: 37.5,
          avg_holding_days: 7.5,
          avg_profit_pct: 6.13,
          avg_loss_pct: 3.0,
          profit_factor: 1.22,
        },
      },
    } as ReturnType<typeof useBacktestSummary>);

    useTradesMock.mockReturnValue({
      data: {
        items: [
          {
            trade_group_id: 1,
            symbol: "GOLDEN",
            name: "",
            entry_date: "2024-01-12",
            entry_price: 9760,
            entry_quantity: 512,
            remaining_quantity: 0,
            fully_closed_at: "2024-01-19T00:00:00",
            final_profit: 50_000,
            final_profit_rate: 5.12,
            executions: [
              { execution_date: "2024-01-12", execution_type: "BUY", price: 9760, quantity: 512, realized_profit: null, exit_reason: null },
              { execution_date: "2024-01-19", execution_type: "SELL", price: 10248, quantity: 512, realized_profit: 50_000, exit_reason: "take_profit" },
            ],
          },
        ],
        total_count: 1,
      },
    } as ReturnType<typeof useBacktestTrades>);

    useEquityMock.mockReturnValue({
      data: {
        items: [
          { date: "2024-01-02", cash: 10_000_000, stock_value: 0, total_equity: 10_000_000, drawdown: 0, positions_count: 0 },
          { date: "2024-04-01", cash: 188_570, stock_value: 10_000_000, total_equity: 10_188_570, drawdown: 0, positions_count: 1 },
        ],
        total_count: 2,
      },
    } as ReturnType<typeof useDailyEquity>);
  });

  it("status, 요약 카드, 거래 내역, 일별 자산 모두 표시", () => {
    renderPage();
    expect(screen.getByTestId("run-status").textContent).toBe("completed");

    const cards = screen.getByLabelText("요약 카드");
    expect(within(cards).getByText("총 수익률")).toBeInTheDocument();
    expect(within(cards).getByText("1.89%")).toBeInTheDocument();
    expect(within(cards).getByText("8")).toBeInTheDocument(); // trade_count

    const trades = screen.getByLabelText("거래 내역");
    expect(within(trades).getByText("GOLDEN")).toBeInTheDocument();
    expect(within(trades).getByText("take_profit")).toBeInTheDocument();

    const equity = screen.getByLabelText("일별 자산");
    expect(within(equity).getByText(/10,188,570/)).toBeInTheDocument();
  });
});
