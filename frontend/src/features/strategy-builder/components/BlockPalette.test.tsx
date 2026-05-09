import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import BlockPalette from "./BlockPalette";
import { useConditions } from "../../../api/conditions";
import { StrategyDraftProvider } from "../state/StrategyDraftContext";
import type { ConditionMeta } from "../../../types/condition";

vi.mock("../../../api/conditions", () => ({
  useConditions: vi.fn(),
}));

const mockUseConditions = vi.mocked(useConditions);

const sample: ConditionMeta[] = [
  {
    type: "price_vs_ma",
    category: "moving_average",
    requires_position: false,
    name: "가격과 이동평균 비교",
    description: "테스트 설명",
    sentence_template: "",
    parameters: [],
    allowed_in: ["entry", "exit_signal", "filters"],
  },
  {
    type: "ma_cross",
    category: "moving_average",
    requires_position: false,
    name: "이동평균 교차",
    description: "",
    sentence_template: "",
    parameters: [],
    allowed_in: ["entry", "exit_signal"],
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

function renderPalette() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StrategyDraftProvider>
        <BlockPalette />
      </StrategyDraftProvider>
    </QueryClientProvider>,
  );
}

describe("BlockPalette", () => {
  beforeEach(() => {
    mockUseConditions.mockReset();
  });

  it("로딩 중 메시지를 보여준다", () => {
    mockUseConditions.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();
    expect(screen.getByText(/로딩 중/)).toBeInTheDocument();
  });

  it("카테고리별로 조건을 그룹화하여 렌더한다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    expect(screen.getByText("moving_average")).toBeInTheDocument();
    expect(screen.getByText("exit_position")).toBeInTheDocument();
    expect(screen.getByText("가격과 이동평균 비교")).toBeInTheDocument();
    expect(screen.getByText("이동평균 교차")).toBeInTheDocument();
    expect(screen.getByText("익절")).toBeInTheDocument();
  });

  it("API 실패 시 안내", () => {
    mockUseConditions.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as ReturnType<typeof useConditions>);
    renderPalette();
    expect(screen.getByText(/조건 카탈로그 불러오기 실패/)).toBeInTheDocument();
  });
});
