/**
 * 통합 테스트: 거래 행 클릭 → 종목 선택 + 요약 탭 이동 + 봉차트 visibleRange 전달.
 * 033 / 08-m.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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
        { time: "2024-01-12", open: 9760, high: 9900, low: 9700, close: 9800 },
        { time: "2024-01-19", open: 10200, high: 10300, low: 10100, close: 10248 },
      ],
      markers: [],
      equity_curve: [],
      symbol: "GOLDEN",
      source: "daily_prices",
    },
  })),
}));

// CandleTradeChart는 visibleRange prop을 data attribute로 노출하는 mock
vi.mock("../features/backtest-result/components/CandleTradeChart", () => ({
  default: ({ visibleRange }: { visibleRange?: { from: string; to: string | null } | null }) => (
    <div
      data-testid="candle-trade-chart"
      data-visible-from={visibleRange?.from ?? ""}
      data-visible-to={visibleRange?.to ?? ""}
    />
  ),
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

describe("BacktestResultPage — 거래 클릭 → 차트 이동 (033 / 08-m)", () => {
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
          total_return_pct: 1.88,
          annual_return_pct: 7.96,
          mdd_pct: -4.9,
          trade_count: 2,
          open_position_count: 0,
          win_rate: 50,
          avg_holding_days: 7,
          avg_profit_pct: 5,
          avg_loss_pct: 2.5,
          profit_factor: 2.0,
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
        items: [] as Array<{
          date: string;
          cash: number;
          stock_value: number;
          total_equity: number;
          drawdown: number;
          positions_count: number;
        }>,
        total_count: 0,
      },
    } as ReturnType<typeof useDailyEquity>);
  });

  it("거래 행 클릭 → 요약 탭으로 이동 + 차트에 visibleRange 전달", () => {
    renderPage();
    // 거래 탭 진입
    fireEvent.click(screen.getByTestId("tab-trades"));
    // 거래 행 클릭
    fireEvent.click(screen.getByTestId("trade-row-1"));
    // 요약 탭 활성화 검증
    expect(screen.getByTestId("tab-summary")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // 봉차트의 visibleRange data 속성 확인
    const chart = screen.getByTestId("candle-trade-chart");
    expect(chart.getAttribute("data-visible-from")).toBe("2024-01-12");
    expect(chart.getAttribute("data-visible-to")).toBe("2024-01-19");
  });

  it("보유 중 거래 클릭 시 visibleRange.to는 빈 값 (null)", () => {
    renderPage();
    fireEvent.click(screen.getByTestId("tab-trades"));
    fireEvent.click(screen.getByTestId("trade-row-2"));
    const chart = screen.getByTestId("candle-trade-chart");
    expect(chart.getAttribute("data-visible-from")).toBe("2024-02-01");
    expect(chart.getAttribute("data-visible-to")).toBe("");
  });

  it("종목을 사용자가 직접 변경하면 visibleRange가 해제됨", () => {
    renderPage();
    fireEvent.click(screen.getByTestId("tab-trades"));
    fireEvent.click(screen.getByTestId("trade-row-1"));
    // 요약 탭에 들어와 있고 visibleRange가 있는 상태
    let chart = screen.getByTestId("candle-trade-chart");
    expect(chart.getAttribute("data-visible-from")).toBe("2024-01-12");
    // 종목 셀렉터 변경
    fireEvent.change(screen.getByTestId("symbol-select"), {
      target: { value: "ALPHA" },
    });
    chart = screen.getByTestId("candle-trade-chart");
    expect(chart.getAttribute("data-visible-from")).toBe("");
    expect(chart.getAttribute("data-visible-to")).toBe("");
  });
});
