import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { useConditions } from "./api/conditions";
import type { ConditionMeta } from "./types/condition";

vi.mock("./api/conditions", () => ({
  useConditions: vi.fn(),
}));

const mockUseConditions = vi.mocked(useConditions);

const sampleConditions: ConditionMeta[] = [
  {
    type: "price_vs_ma",
    category: "moving_average",
    requires_position: false,
    name: "가격과 이동평균 비교",
    description: "",
    sentence_template: "",
    parameters: [],
    allowed_in: ["entry", "exit_signal", "filters"],
  },
  {
    type: "take_profit",
    category: "exit_position",
    requires_position: true,
    name: "익절",
    description: "",
    sentence_template: "",
    parameters: [],
    allowed_in: ["exit_position"],
  },
];

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("App", () => {
  beforeEach(() => {
    mockUseConditions.mockReset();
  });

  it("페이지 제목을 렌더한다", () => {
    mockUseConditions.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderWithClient(<App />);
    expect(screen.getByText("주식 전략 연구소")).toBeInTheDocument();
  });

  it("API 응답을 받아 조건 목록을 렌더한다", () => {
    mockUseConditions.mockReturnValue({
      data: sampleConditions,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderWithClient(<App />);

    expect(screen.getByText(/가격과 이동평균 비교/)).toBeInTheDocument();
    expect(screen.getByText(/익절/)).toBeInTheDocument();
    expect(screen.getByText(/시계열/)).toBeInTheDocument();
    expect(screen.getByText(/포지션/)).toBeInTheDocument();
  });

  it("API 실패 시 안내 메시지를 보여준다", () => {
    mockUseConditions.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("connect failed"),
    } as ReturnType<typeof useConditions>);
    renderWithClient(<App />);

    expect(screen.getByText(/백엔드 연결 실패/)).toBeInTheDocument();
  });
});
