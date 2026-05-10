import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StrategyHeader from "./StrategyHeader";
import { StrategyDraftProvider } from "../../state/StrategyDraftContext";
import {
  useDuplicateStrategy,
  useCreateStrategy,
} from "../../../../api/strategies";
import { useConditions } from "../../../../api/conditions";
import type { ConditionMeta } from "../../../../types/condition";

const SAMPLE: ConditionMeta[] = [
  {
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
  },
];

vi.mock("../../../../api/conditions", () => ({
  useConditions: vi.fn(() => ({ data: SAMPLE, isLoading: false, error: null })),
}));

vi.mock("../../../../api/strategies", () => ({
  useCreateStrategy: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  })),
  useDuplicateStrategy: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

// silence used-import warnings
void useConditions;
void useCreateStrategy;

const dupMutate = vi.fn();
const mockedUseDuplicate = vi.mocked(useDuplicateStrategy);

function renderHeader(props: Partial<React.ComponentProps<typeof StrategyHeader>> = {}) {
  const onSave = props.onSave ?? vi.fn().mockResolvedValue(123);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    onSave,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <StrategyDraftProvider>
            <StrategyHeader
              savedStrategyId={props.savedStrategyId ?? null}
              canSave={props.canSave ?? false}
              onSave={onSave}
              isSaving={props.isSaving ?? false}
              saveErrorMessage={props.saveErrorMessage ?? null}
            />
          </StrategyDraftProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

describe("StrategyHeader", () => {
  beforeEach(() => {
    dupMutate.mockReset();
    mockNavigate.mockReset();
    window.localStorage.clear();
    mockedUseDuplicate.mockReturnValue({
      mutate: dupMutate,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof useDuplicateStrategy>);
  });

  it("렌더링 — 모든 핵심 버튼 존재", () => {
    renderHeader();
    expect(screen.getByLabelText("전략 이름")).toBeInTheDocument();
    expect(screen.getByLabelText("템플릿 선택")).toBeInTheDocument();
    expect(screen.getByLabelText("전략 저장")).toBeInTheDocument();
    expect(screen.getByLabelText("전략 복사")).toBeInTheDocument();
    expect(screen.getByLabelText("JSON 보기")).toBeInTheDocument();
    expect(screen.getByLabelText("백테스트 실행")).toBeInTheDocument();
    expect(screen.getByLabelText("초보자 모드")).toBeInTheDocument();
    expect(screen.getByLabelText("전문가 모드")).toBeInTheDocument();
  });

  it("초기 — 저장 disabled (canSave=false), 복사 disabled (savedStrategyId=null)", () => {
    renderHeader({ canSave: false, savedStrategyId: null });
    expect(screen.getByLabelText("전략 저장")).toBeDisabled();
    expect(screen.getByLabelText("전략 복사")).toBeDisabled();
  });

  it("canSave=true → 저장 활성", () => {
    renderHeader({ canSave: true });
    expect(screen.getByLabelText("전략 저장")).not.toBeDisabled();
  });

  it("savedStrategyId 있음 → 복사 활성, 클릭 시 duplicate mutate 호출", async () => {
    dupMutate.mockImplementation((_payload, opts) =>
      opts?.onSuccess?.({ id: 999, name: "복사본" }),
    );
    renderHeader({ savedStrategyId: 5 });
    fireEvent.click(screen.getByLabelText("전략 복사"));
    await waitFor(() => {
      expect(dupMutate).toHaveBeenCalledWith(
        expect.objectContaining({ strategyId: 5 }),
        expect.anything(),
      );
    });
    const payload = dupMutate.mock.calls[0][0];
    expect(payload.newName).toContain("(복사)");
    expect(mockNavigate).toHaveBeenCalledWith("/strategies/999");
  });

  it("JSON 보기 클릭 → modal 열림 + serialized JSON 표시", () => {
    renderHeader();
    fireEvent.click(screen.getByLabelText("JSON 보기"));
    const dialog = screen.getByRole("dialog", { name: "전략 JSON" });
    expect(dialog).toBeInTheDocument();
    const pre = within(dialog).getByLabelText("직렬화된 전략 JSON");
    // 빈 draft → name만 있는 JSON
    expect(pre.textContent).toContain('"name":');
  });

  it("JSON modal 닫기 — × 버튼", () => {
    renderHeader();
    fireEvent.click(screen.getByLabelText("JSON 보기"));
    expect(screen.getByRole("dialog", { name: "전략 JSON" })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("닫기"));
    expect(screen.queryByRole("dialog", { name: "전략 JSON" })).not.toBeInTheDocument();
  });

  it("백테스트 실행 — savedStrategyId 있으면 즉시 navigate", async () => {
    renderHeader({ savedStrategyId: 7 });
    fireEvent.click(screen.getByLabelText("백테스트 실행"));
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/backtests/new?strategy_id=7");
    });
  });

  it("백테스트 실행 — savedStrategyId 없고 canSave=false → 에러 메시지", async () => {
    renderHeader({ savedStrategyId: null, canSave: false });
    fireEvent.click(screen.getByLabelText("백테스트 실행"));
    await waitFor(() => {
      expect(
        screen.getByText(/백테스트 실행 전에 전략 이름과 조건을 입력하세요/),
      ).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("백테스트 실행 — savedStrategyId 없으나 canSave=true → onSave 호출 후 navigate", async () => {
    const onSave = vi.fn().mockResolvedValue(42);
    renderHeader({ savedStrategyId: null, canSave: true, onSave });
    fireEvent.click(screen.getByLabelText("백테스트 실행"));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith("/backtests/new?strategy_id=42");
    });
  });

  it("모드 토글 — 초보자/전문가 클릭 시 aria-checked 변경 + localStorage 갱신", () => {
    renderHeader();
    const beginnerBtn = screen.getByLabelText("초보자 모드");
    const expertBtn = screen.getByLabelText("전문가 모드");
    expect(expertBtn).toHaveAttribute("aria-checked", "true");

    fireEvent.click(beginnerBtn);
    expect(beginnerBtn).toHaveAttribute("aria-checked", "true");
    expect(window.localStorage.getItem("stockstrategy.builder_mode")).toBe("beginner");

    fireEvent.click(expertBtn);
    expect(expertBtn).toHaveAttribute("aria-checked", "true");
    expect(window.localStorage.getItem("stockstrategy.builder_mode")).toBe("expert");
  });

  it("템플릿 버튼 → modal 열림", () => {
    renderHeader();
    fireEvent.click(screen.getByLabelText("템플릿 선택"));
    expect(screen.getByRole("dialog", { name: "전략 템플릿 선택" })).toBeInTheDocument();
    // 4종 템플릿 표시
    expect(screen.getByLabelText("빈 전략 템플릿 적용")).toBeInTheDocument();
    expect(screen.getByLabelText("골든 크로스 (5/20 MA) 템플릿 적용")).toBeInTheDocument();
  });

  it("저장 실패 메시지 노출", () => {
    renderHeader({ saveErrorMessage: "저장 실패" });
    expect(screen.getByText("저장 실패")).toBeInTheDocument();
  });
});
