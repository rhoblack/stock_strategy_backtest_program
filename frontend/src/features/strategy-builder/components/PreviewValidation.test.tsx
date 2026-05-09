import { describe, expect, it, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StrategyBuilderPage from "../../../pages/StrategyBuilderPage";
import type { ConditionMeta } from "../../../types/condition";

const sample: ConditionMeta[] = [
  {
    type: "price_vs_ma",
    category: "moving_average",
    requires_position: false,
    name: "가격과 이동평균 비교",
    description: "",
    sentence_template: "{price_field}가 {ma_period}일 MA보다 {operator_label}",
    parameters: [
      { name: "price_field", label: "가격", input_type: "select", default: "adj_close",
        options: [{ label: "수정 종가", value: "adj_close" }] },
      { name: "ma_period", label: "MA", input_type: "number", default: 20 },
      { name: "operator", label: "비교", input_type: "select", default: ">",
        options: [{ label: "위", value: ">" }] },
    ],
    allowed_in: ["entry"],
  },
];

vi.mock("../../../api/conditions", () => ({
  useConditions: vi.fn(() => ({ data: sample, isLoading: false, error: null })),
}));

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StrategyBuilderPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StrategyPreviewPanel + StrategyValidationPanel", () => {
  it("초기 상태: 미리보기 안내 + 검증 오류/경고 표시", () => {
    renderApp();
    const preview = screen.getByLabelText("전략 미리보기");
    expect(within(preview).getByText(/조건이 없습니다/)).toBeInTheDocument();

    const validation = screen.getByLabelText("전략 검증");
    expect(within(validation).getByText(/매수 조건이 없습니다/)).toBeInTheDocument();
  });

  it("entry 추가 → 미리보기에 문장 + 검증 오류 사라짐", () => {
    renderApp();
    const palette = screen.getByLabelText("블록 팔레트");
    fireEvent.click(within(palette).getByText("가격과 이동평균 비교"));

    const preview = screen.getByLabelText("전략 미리보기");
    expect(within(preview).getByText("매수 조건")).toBeInTheDocument();
    expect(within(preview).getByText(/수정 종가가 20일 MA보다 위/)).toBeInTheDocument();

    const validation = screen.getByLabelText("전략 검증");
    expect(within(validation).queryByText(/매수 조건이 없습니다/)).not.toBeInTheDocument();
  });
});
