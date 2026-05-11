import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StrategyListPage from "./StrategyListPage";
import { useStrategies } from "../api/strategies";
import type { StrategyOut } from "../api/strategies";

vi.mock("../api/strategies", () => ({
  useStrategies: vi.fn(),
}));

const useStrategiesMock = vi.mocked(useStrategies);

const baseStrategy: StrategyOut = {
  id: 1,
  user_id: 1,
  name: "거래량 돌파 전략",
  description: "거래량 급증 종목 매수",
  strategy_json: {},
  tags: ["거래량", "돌파"],
  favorite: false,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  deleted_at: null,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StrategyListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StrategyListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("전략 목록 표시 + 태그 표시", () => {
    useStrategiesMock.mockReturnValue({
      data: [baseStrategy],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);

    renderPage();
    expect(screen.getByText("거래량 돌파 전략")).toBeInTheDocument();
    expect(screen.getByText("거래량, 돌파")).toBeInTheDocument();
  });

  it("last_backtest 필드 있을 때 수익률과 MDD 표시", () => {
    const strategyWithBacktest: StrategyOut = {
      ...baseStrategy,
      last_backtest: {
        total_return: 84.2,
        mdd: -18.5,
        win_rate: 47.8,
        run_date: "2026-05-11",
      },
    };

    useStrategiesMock.mockReturnValue({
      data: [strategyWithBacktest],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);

    renderPage();

    // 뱃지가 표시되는지 확인
    expect(screen.getByTestId("last-backtest-badge")).toBeInTheDocument();

    // 수익률 양수 표시 확인 (+84.2%)
    const returnEl = screen.getByTestId("last-backtest-return");
    expect(returnEl).toHaveTextContent("+84.2%");
    // 양수는 초록색
    expect(returnEl).toHaveStyle({ color: "#16a34a" });

    // MDD 표시
    expect(screen.getByText(/MDD -18.5%/)).toBeInTheDocument();

    // 날짜 포맷 확인 ("2026-05-11" → "2026.05.11")
    expect(screen.getByText("2026.05.11")).toBeInTheDocument();
  });

  it("last_backtest 수익률 음수일 때 빨간색 표시", () => {
    const strategyWithNegativeReturn: StrategyOut = {
      ...baseStrategy,
      last_backtest: {
        total_return: -12.3,
        mdd: -25.0,
        win_rate: 30.0,
      },
    };

    useStrategiesMock.mockReturnValue({
      data: [strategyWithNegativeReturn],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);

    renderPage();

    const returnEl = screen.getByTestId("last-backtest-return");
    expect(returnEl).toHaveTextContent("-12.3%");
    // 음수는 빨간색
    expect(returnEl).toHaveStyle({ color: "#dc2626" });
  });

  it("last_backtest 필드 없을 때 '최근 백테스트 없음' 표시", () => {
    useStrategiesMock.mockReturnValue({
      data: [baseStrategy],   // last_backtest 필드 없음
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);

    renderPage();
    expect(screen.getByTestId("last-backtest-empty")).toBeInTheDocument();
    expect(screen.getByText("최근 백테스트 없음")).toBeInTheDocument();
  });

  it("last_backtest가 null일 때 '최근 백테스트 없음' 표시", () => {
    const strategyWithNull: StrategyOut = {
      ...baseStrategy,
      last_backtest: null,
    };

    useStrategiesMock.mockReturnValue({
      data: [strategyWithNull],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);

    renderPage();
    expect(screen.getByTestId("last-backtest-empty")).toBeInTheDocument();
  });

  it("로딩 중 표시", () => {
    useStrategiesMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);

    renderPage();
    expect(screen.getByText("로딩 중...")).toBeInTheDocument();
  });

  it("전략 없을 때 안내 문구 표시", () => {
    useStrategiesMock.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);

    renderPage();
    expect(screen.getByText("아직 저장된 전략이 없습니다.")).toBeInTheDocument();
  });

  it("백테스트 실행 링크가 올바른 URL로 생성됨", () => {
    useStrategiesMock.mockReturnValue({
      data: [baseStrategy],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);

    renderPage();
    const link = screen.getByRole("link", { name: "백테스트 실행" });
    expect(link).toHaveAttribute("href", "/backtests/new?strategy_id=1");
  });
});
