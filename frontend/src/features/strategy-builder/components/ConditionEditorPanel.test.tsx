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
    description: "지정한 가격이 N일 이동평균선보다 위/아래인지 판단합니다.",
    sentence_template: "{price_field}가 {ma_period}일 MA보다 {operator_label}",
    parameters: [
      {
        name: "price_field",
        label: "가격 기준",
        input_type: "select",
        default: "adj_close",
        options: [
          { label: "수정 종가", value: "adj_close" },
          { label: "수정 시가", value: "adj_open" },
        ],
      },
      { name: "ma_period", label: "MA 기간", input_type: "number", default: 20, min: 2, max: 300 },
      {
        name: "operator",
        label: "비교",
        input_type: "select",
        default: ">",
        options: [
          { label: "위", value: ">" },
          { label: "아래", value: "<" },
        ],
      },
    ],
    allowed_in: ["entry", "exit_signal", "filters"],
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

describe("ConditionEditorPanel", () => {
  it("미선택 시 안내 메시지", () => {
    renderApp();
    const editor = screen.getByLabelText("조건 편집 패널");
    expect(within(editor).getByText(/조립 영역의 조건 카드를 클릭/)).toBeInTheDocument();
  });

  it("팔레트 클릭 → 자동 선택 → 편집 패널이 폼 표시", () => {
    renderApp();
    const palette = screen.getByLabelText("블록 팔레트");
    fireEvent.click(within(palette).getByText("가격과 이동평균 비교"));

    const editor = screen.getByLabelText("조건 편집 패널");
    // 폼 필드들
    expect(within(editor).getByLabelText("가격 기준")).toBeInTheDocument();
    expect(within(editor).getByLabelText("MA 기간")).toBeInTheDocument();
    expect(within(editor).getByLabelText("비교")).toBeInTheDocument();

    // 미리보기에 현재 문장
    const preview = within(editor).getByTestId("editor-preview");
    expect(preview.textContent).toMatch(/수정 종가가 20일 MA보다 위/);
  });

  it("number 입력 변경 → 카드 문장과 미리보기 모두 갱신", () => {
    renderApp();
    fireEvent.click(within(screen.getByLabelText("블록 팔레트")).getByText("가격과 이동평균 비교"));

    const editor = screen.getByLabelText("조건 편집 패널");
    const maInput = within(editor).getByLabelText("MA 기간") as HTMLInputElement;

    fireEvent.change(maInput, { target: { value: "5" } });

    // 미리보기
    expect(within(editor).getByTestId("editor-preview").textContent).toMatch(
      /수정 종가가 5일 MA보다 위/,
    );
    // Canvas 카드도 갱신
    const entrySection = screen.getByLabelText("매수 조건");
    expect(within(entrySection).getByText(/수정 종가가 5일 MA보다 위/)).toBeInTheDocument();
  });

  it("select 변경 (operator 위→아래)", () => {
    renderApp();
    fireEvent.click(within(screen.getByLabelText("블록 팔레트")).getByText("가격과 이동평균 비교"));

    const editor = screen.getByLabelText("조건 편집 패널");
    const opSelect = within(editor).getByLabelText("비교") as HTMLSelectElement;

    fireEvent.change(opSelect, { target: { value: "<" } });
    expect(within(editor).getByTestId("editor-preview").textContent).toMatch(/아래/);
  });
});
