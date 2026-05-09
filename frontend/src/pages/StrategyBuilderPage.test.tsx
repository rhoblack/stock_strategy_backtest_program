import { describe, expect, it, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StrategyBuilderPage from "./StrategyBuilderPage";
import type { ConditionMeta } from "../types/condition";

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
        options: [{ label: "위", value: ">" }, { label: "아래", value: "<" }] },
    ],
    allowed_in: ["entry", "exit_signal", "filters"],
  },
  {
    type: "take_profit",
    category: "exit_position",
    requires_position: true,
    name: "익절",
    description: "",
    sentence_template: "수익률 {percent}% 이상이면 익절",
    parameters: [{ name: "percent", label: "%", input_type: "number", default: 7.0 }],
    allowed_in: ["exit_position"],
  },
];

vi.mock("../api/conditions", () => ({
  useConditions: vi.fn(() => ({ data: sample, isLoading: false, error: null })),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StrategyBuilderPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StrategyBuilderPage", () => {
  it("3열 + 5 섹션 + 저장 disabled", () => {
    renderPage();
    expect(screen.getByLabelText("블록 팔레트")).toBeInTheDocument();
    expect(screen.getByLabelText("전략 조립 영역")).toBeInTheDocument();
    expect(screen.getByLabelText("조건 편집 패널")).toBeInTheDocument();
    expect(screen.getByLabelText("매수 조건")).toBeInTheDocument();
    expect(screen.getByLabelText("매도 시계열 조건")).toBeInTheDocument();
    expect(screen.getByLabelText("매도 포지션 조건")).toBeInTheDocument();
    expect(screen.getByLabelText("필터")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "전략 저장" })).toBeDisabled();
  });

  it("팔레트 클릭 → 매수 조건 섹션에 카드 추가 → 문장 렌더", () => {
    renderPage();
    const palette = screen.getByLabelText("블록 팔레트");
    fireEvent.click(within(palette).getByText("가격과 이동평균 비교"));

    const entrySection = screen.getByLabelText("매수 조건");
    expect(within(entrySection).getByText(/수정 종가가 20일 MA보다 위/)).toBeInTheDocument();
  });

  it("take_profit 팔레트 클릭 → 매도 포지션 조건에 추가", () => {
    renderPage();
    const palette = screen.getByLabelText("블록 팔레트");
    fireEvent.click(within(palette).getByText("익절"));

    const exitPos = screen.getByLabelText("매도 포지션 조건");
    expect(within(exitPos).getByText(/수익률 7% 이상이면 익절/)).toBeInTheDocument();
  });

  it("카드 × 버튼 클릭 → 삭제", () => {
    renderPage();
    fireEvent.click(within(screen.getByLabelText("블록 팔레트")).getByText("가격과 이동평균 비교"));
    const entrySection = screen.getByLabelText("매수 조건");
    expect(within(entrySection).queryByText(/수정 종가가 20일 MA보다 위/)).toBeInTheDocument();

    fireEvent.click(within(entrySection).getByLabelText("조건 삭제"));
    expect(within(entrySection).queryByText(/수정 종가가 20일 MA보다 위/)).not.toBeInTheDocument();
  });

  it("logic 셀렉트 변경 → AND/OR 갱신", () => {
    renderPage();
    const select = screen.getByLabelText("매수 조건 조합") as HTMLSelectElement;
    expect(select.value).toBe("AND");
    fireEvent.change(select, { target: { value: "OR" } });
    expect(select.value).toBe("OR");
  });
});
