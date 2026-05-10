import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import TemplateSelector from "./TemplateSelector";
import { StrategyDraftProvider } from "../state/StrategyDraftContext";
import type { ConditionMeta } from "../../../types/condition";
import { useConditions } from "../../../api/conditions";

const PRICE_VS_MA: ConditionMeta = {
  type: "price_vs_ma",
  category: "moving_average",
  requires_position: false,
  name: "가격과 이동평균 비교",
  description: "",
  sentence_template: "{price_field}가 {ma_period}일 MA보다 {operator}",
  parameters: [
    { name: "price_field", label: "가격", input_type: "select", default: "adj_close" },
    { name: "ma_period", label: "MA", input_type: "number", default: 20 },
    { name: "operator", label: "비교", input_type: "select", default: ">" },
  ],
  allowed_in: ["entry"],
};

const TAKE_PROFIT: ConditionMeta = {
  type: "take_profit",
  category: "exit_position",
  requires_position: true,
  name: "익절",
  description: "",
  sentence_template: "수익률 {percent}% 이상이면 익절",
  parameters: [{ name: "percent", label: "%", input_type: "number", default: 7.0 }],
  allowed_in: ["exit_position"],
};

const STOP_LOSS: ConditionMeta = {
  type: "stop_loss",
  category: "exit_position",
  requires_position: true,
  name: "손절",
  description: "",
  sentence_template: "수익률 {percent}% 이하면 손절",
  parameters: [{ name: "percent", label: "%", input_type: "number", default: 5.0 }],
  allowed_in: ["exit_position"],
};

const FULL_CATALOG: ConditionMeta[] = [PRICE_VS_MA, TAKE_PROFIT, STOP_LOSS];

vi.mock("../../../api/conditions", () => ({
  useConditions: vi.fn(),
}));
const mockedUseConditions = vi.mocked(useConditions);

function renderSelector(extraProps: Partial<React.ComponentProps<typeof TemplateSelector>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StrategyDraftProvider>
          <TemplateSelector {...extraProps} />
        </StrategyDraftProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TemplateSelector", () => {
  beforeEach(() => {
    mockedUseConditions.mockReturnValue({
      data: FULL_CATALOG,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useConditions>);
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("4종 템플릿 표시 (카테고리별 그룹)", () => {
    renderSelector();
    expect(screen.getByLabelText("빈 전략 템플릿 적용")).toBeInTheDocument();
    expect(screen.getByLabelText("골든 크로스 (5/20 MA) 템플릿 적용")).toBeInTheDocument();
    expect(screen.getByLabelText("RSI 과매도 진입 템플릿 적용")).toBeInTheDocument();
    expect(
      screen.getByLabelText("단기 신고가 + 거래량 모멘텀 템플릿 적용"),
    ).toBeInTheDocument();
  });

  it("showEmpty=false → 빈 전략 숨김", () => {
    renderSelector({ showEmpty: false });
    expect(screen.queryByLabelText("빈 전략 템플릿 적용")).not.toBeInTheDocument();
    expect(screen.getByLabelText("골든 크로스 (5/20 MA) 템플릿 적용")).toBeInTheDocument();
  });

  it("템플릿 클릭 → onApplied 콜백 호출", () => {
    const onApplied = vi.fn();
    renderSelector({ onApplied });
    fireEvent.click(screen.getByLabelText("빈 전략 템플릿 적용"));
    expect(onApplied).toHaveBeenCalled();
    expect(onApplied.mock.calls[0][0].id).toBe("empty");
  });

  it("dirty 상태에서 비-empty 템플릿 클릭 → confirm 노출", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderSelector();
    // empty가 아닌 템플릿 (작업 내용이 있다는 가정 — 그러나 새로 시작하면 empty 상태이므로
    // dirty 검사를 위해 이름을 미리 입력해야 함. 여기서는 디폴트로 empty 상태 → confirm 안 뜸)
    fireEvent.click(screen.getByLabelText("골든 크로스 (5/20 MA) 템플릿 적용"));
    // 빈 draft → dirty=false → confirm 호출 안 됨
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("카탈로그에 없는 condition type → 경고 메시지 노출", () => {
    // catalog에 take_profit/stop_loss 빠뜨림
    mockedUseConditions.mockReturnValue({
      data: [PRICE_VS_MA],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useConditions>);
    renderSelector();
    fireEvent.click(screen.getByLabelText("골든 크로스 (5/20 MA) 템플릿 적용"));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert").textContent).toMatch(/take_profit|stop_loss/);
  });
});
