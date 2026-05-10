import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StrategyComparePage from "./StrategyComparePage";
import { useStrategies } from "../api/strategies";

vi.mock("../api/strategies", () => ({
  useStrategies: vi.fn(),
}));

const useStrategiesMock = vi.mocked(useStrategies);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/strategies/compare"]}>
        <Routes>
          <Route path="/strategies/compare" element={<StrategyComparePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StrategyComparePage", () => {
  beforeEach(() => {
    useStrategiesMock.mockReset();
    useStrategiesMock.mockReturnValue({
      data: [
        { id: 1, name: "전략 A", tags: [] as string[] },
        { id: 2, name: "전략 B", tags: [] as string[] },
        { id: 3, name: "전략 C", tags: [] as string[] },
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useStrategies>);
  });

  it("페이지 골격 + 두 selector 표시", () => {
    renderPage();
    expect(screen.getByTestId("strategy-compare-page")).toBeInTheDocument();
    expect(screen.getByTestId("compare-left")).toBeInTheDocument();
    expect(screen.getByTestId("compare-right")).toBeInTheDocument();
  });

  it("선택 전: 안내 메시지 (서로 다른 전략 선택)", () => {
    renderPage();
    expect(
      screen.getByText(/비교할 두 전략을 각각 선택하세요/),
    ).toBeInTheDocument();
  });

  it("같은 전략 2개 선택 시 비교 영역 활성 안 됨", () => {
    renderPage();
    fireEvent.change(screen.getByTestId("compare-left"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByTestId("compare-right"), {
      target: { value: "1" },
    });
    expect(
      screen.getByText(/비교할 두 전략을 각각 선택하세요/),
    ).toBeInTheDocument();
  });

  it("서로 다른 전략 2개 선택 시 비교 기능 준비 중 메시지", () => {
    renderPage();
    fireEvent.change(screen.getByTestId("compare-left"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByTestId("compare-right"), {
      target: { value: "2" },
    });
    expect(screen.getByText("비교 기능 준비 중")).toBeInTheDocument();
  });
});
