import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StrategyBuilderPage from "./StrategyBuilderPage";
import { useCreateStrategy } from "../api/strategies";
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
        options: [{ label: "위", value: ">" }] },
    ],
    allowed_in: ["entry"],
  },
];

vi.mock("../api/conditions", () => ({
  useConditions: vi.fn(() => ({ data: sample, isLoading: false, error: null })),
}));

vi.mock("../api/strategies", () => ({
  useCreateStrategy: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

const mutate = vi.fn();
const mockedUseCreate = vi.mocked(useCreateStrategy);

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

describe("저장 흐름", () => {
  beforeEach(() => {
    mutate.mockReset();
    mockNavigate.mockReset();
    // 기본 mutate 동작: onSuccess 콜백을 즉시 호출
    mutate.mockImplementation((_payload, opts) => {
      opts?.onSuccess?.({
        id: 1,
        user_id: 1,
        name: "내 전략",
        description: "",
        strategy_json: {},
        tags: [],
        favorite: false,
        created_at: "",
        updated_at: "",
        deleted_at: null,
      });
    });
    mockedUseCreate.mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof useCreateStrategy>);
  });

  it("초기: 저장 버튼 disabled (이름 없음 + 검증 오류)", () => {
    renderApp();
    expect(screen.getByRole("button", { name: "전략 저장" })).toBeDisabled();
  });

  it("이름 입력 + entry 추가 → 저장 활성화", () => {
    renderApp();
    fireEvent.change(screen.getByLabelText("전략 이름"), { target: { value: "내 전략" } });
    fireEvent.click(within(screen.getByLabelText("블록 팔레트")).getByText("가격과 이동평균 비교"));
    expect(screen.getByRole("button", { name: "전략 저장" })).not.toBeDisabled();
  });

  it("저장 클릭 → mutate 호출 + redirect", async () => {
    renderApp();
    fireEvent.change(screen.getByLabelText("전략 이름"), { target: { value: "내 전략" } });
    fireEvent.click(within(screen.getByLabelText("블록 팔레트")).getByText("가격과 이동평균 비교"));
    fireEvent.click(screen.getByRole("button", { name: "전략 저장" }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalled();
    });

    const payload = mutate.mock.calls[0][0];
    expect(payload.name).toBe("내 전략");
    expect((payload.strategy_json as Record<string, unknown>).entry).toBeDefined();

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/strategies");
    });
  });
});
