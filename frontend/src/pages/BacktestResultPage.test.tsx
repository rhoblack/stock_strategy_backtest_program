import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
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

vi.mock("../api/chartData", () => ({
  useChartData: vi.fn(() => ({
    data: {
      candles: [
        { time: "2024-01-02", open: 100, high: 110, low: 90, close: 105, volume: 1000 },
        { time: "2024-01-03", open: 105, high: 115, low: 100, close: 102, volume: 800 },
      ],
      markers: [],
      equity_curve: [
        { time: "2024-01-02", value: 10_000_000, drawdown: 0 },
        { time: "2024-01-03", value: 10_050_000, drawdown: -0.5 },
      ],
      symbol: "GOLDEN",
      source: "daily_prices",
    },
  })),
}));

// jsdom에서 lightweight-charts canvas 측정 안 됨 → 모든 차트 mock
vi.mock("../features/backtest-result/components/CandleTradeChart", () => ({
  default: () => <div data-testid="candle-trade-chart" />,
}));
vi.mock("../features/backtest-result/components/EquityCurveChart", () => ({
  default: () => <div data-testid="equity-curve-chart" />,
}));
vi.mock("../components/charts/DrawdownChart", () => ({
  default: () => <div data-testid="drawdown-chart" />,
}));
vi.mock("../components/charts/CashChart", () => ({
  default: () => <div data-testid="cash-chart" />,
}));
vi.mock("../components/charts/PositionsCountChart", () => ({
  default: () => <div data-testid="positions-count-chart" />,
}));
vi.mock("../components/charts/VolumeChart", () => ({
  default: () => <div data-testid="volume-chart" />,
}));
vi.mock("../components/charts/BenchmarkCompareChart", () => ({
  default: () => <div data-testid="benchmark-compare-chart" />,
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
            name: "골든종목",
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
          {
            trade_group_id: 2,
            symbol: "ALPHA",
            name: "알파종목",
            entry_date: "2024-02-01",
            entry_price: 5000,
            entry_quantity: 100,
            remaining_quantity: 100,
            fully_closed_at: null,
            final_profit: null,
            final_profit_rate: null,
            executions: [
              { execution_date: "2024-02-01", execution_type: "BUY", price: 5000, quantity: 100, realized_profit: null, exit_reason: null },
            ],
          },
        ],
        total_count: 2,
      },
    } as ReturnType<typeof useBacktestTrades>);

    useEquityMock.mockReturnValue({
      data: {
        items: [
          { date: "2024-01-02", cash: 10_000_000, stock_value: 0, total_equity: 10_000_000, drawdown: 0, positions_count: 0 },
          { date: "2024-02-01", cash: 5_000_000, stock_value: 5_100_000, total_equity: 10_100_000, drawdown: 0, positions_count: 1 },
          { date: "2024-04-01", cash: 188_570, stock_value: 10_000_000, total_equity: 10_188_570, drawdown: 0, positions_count: 1 },
        ],
        total_count: 3,
      },
    } as ReturnType<typeof useDailyEquity>);
  });

  it("탭 6개가 표시된다 (요약/거래/자산/월별 성과/리스크/자금 관리)", () => {
    renderPage();
    expect(screen.getByTestId("tab-summary")).toBeInTheDocument();
    expect(screen.getByTestId("tab-trades")).toBeInTheDocument();
    expect(screen.getByTestId("tab-equity")).toBeInTheDocument();
    expect(screen.getByTestId("tab-monthly")).toBeInTheDocument();
    expect(screen.getByTestId("tab-risk")).toBeInTheDocument();
    expect(screen.getByTestId("tab-cash")).toBeInTheDocument();
  });

  it("기본 탭은 요약, 요약 카드 + 봉차트 표시", () => {
    renderPage();
    expect(screen.getByTestId("run-status").textContent).toBe("completed");
    const cards = screen.getByLabelText("요약 카드");
    expect(within(cards).getByText("총 수익률")).toBeInTheDocument();
    expect(within(cards).getByText("1.89%")).toBeInTheDocument();
    expect(screen.getByTestId("candle-trade-chart")).toBeInTheDocument();
  });

  it("거래 탭으로 전환 시 거래 내역 표시", () => {
    renderPage();
    fireEvent.click(screen.getByTestId("tab-trades"));
    const trades = screen.getByLabelText("거래 내역");
    expect(within(trades).getByText("GOLDEN")).toBeInTheDocument();
    expect(within(trades).getByText("take_profit")).toBeInTheDocument();
  });

  it("자산 탭에 EquityCurve / Volume / Benchmark 차트 표시", () => {
    renderPage();
    fireEvent.click(screen.getByTestId("tab-equity"));
    expect(screen.getByTestId("equity-curve-chart")).toBeInTheDocument();
    expect(screen.getByTestId("volume-chart")).toBeInTheDocument();
    expect(screen.getByTestId("benchmark-compare-chart")).toBeInTheDocument();
  });

  it("월별 성과 탭에 월별 표 + 수익률 표시", () => {
    renderPage();
    fireEvent.click(screen.getByTestId("tab-monthly"));
    const monthly = screen.getByLabelText("월별 성과");
    expect(within(monthly).getByText("2024-01")).toBeInTheDocument();
    expect(within(monthly).getByText("2024-02")).toBeInTheDocument();
    expect(within(monthly).getByText("2024-04")).toBeInTheDocument();
  });

  it("리스크 탭에 MDD / Profit Factor 카드 + DrawdownChart 표시", () => {
    renderPage();
    fireEvent.click(screen.getByTestId("tab-risk"));
    expect(screen.getByTestId("drawdown-chart")).toBeInTheDocument();
    const cards = screen.getByLabelText("리스크 지표");
    expect(within(cards).getByText("최대 낙폭 (MDD)")).toBeInTheDocument();
  });

  it("자금 관리 탭에 CashChart + PositionsCountChart + 통계 카드 표시", () => {
    renderPage();
    fireEvent.click(screen.getByTestId("tab-cash"));
    expect(screen.getByTestId("cash-chart")).toBeInTheDocument();
    expect(screen.getByTestId("positions-count-chart")).toBeInTheDocument();
    const cards = screen.getByLabelText("자금 관리 카드");
    expect(within(cards).getByText("초기 자금")).toBeInTheDocument();
    expect(within(cards).getByText("평균 예수금")).toBeInTheDocument();
    expect(within(cards).getByText("최소 예수금")).toBeInTheDocument();
  });

  it("종목 선택 드롭다운: 2종목 이상이면 표시되고 변경 시 반영", () => {
    renderPage();
    // 요약 탭이 기본 활성. SymbolSelector는 요약 탭의 봉차트 위에 노출.
    const select = screen.getByTestId("symbol-select") as HTMLSelectElement;
    expect(select).toBeInTheDocument();
    // ASC 정렬: ALPHA가 GOLDEN 앞에
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
    expect(options).toEqual(["", "ALPHA", "GOLDEN"]);
    fireEvent.change(select, { target: { value: "ALPHA" } });
    expect(select.value).toBe("ALPHA");
  });
});
