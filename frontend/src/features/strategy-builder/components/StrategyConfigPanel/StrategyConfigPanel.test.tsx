/**
 * StrategyConfigPanel + 6 폼 통합 테스트.
 *
 * 02번 §7~§12, §17 + Wave 12-029.
 */
import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import StrategyConfigPanel from "./StrategyConfigPanel";
import { StrategyDraftProvider, useStrategyDraft } from "../../state/StrategyDraftContext";
import { serializeDraft } from "../../utils/serializeDraft";
import { STRATEGY_SCHEMA_VERSION } from "../../state/strategySections";

beforeEach(() => {
  // useBuilderMode가 localStorage를 읽으므로 매 테스트마다 expert default로 reset
  window.localStorage.clear();
});

function renderPanel() {
  return render(
    <StrategyDraftProvider>
      <StrategyConfigPanel />
    </StrategyDraftProvider>,
  );
}

/** 컴포넌트 트리에서 draft를 꺼내 직렬화 결과를 검사. */
function DraftProbe({ onReady }: { onReady: (snap: () => unknown) => void }) {
  const { draft } = useStrategyDraft();
  onReady(() => serializeDraft(draft));
  return null;
}

function renderWithProbe() {
  let snapFn: () => unknown = () => ({});
  const utils = render(
    <StrategyDraftProvider>
      <StrategyConfigPanel />
      <DraftProbe onReady={(fn) => (snapFn = fn)} />
    </StrategyDraftProvider>,
  );
  return { ...utils, snap: () => snapFn() };
}

describe("StrategyConfigPanel — 탭 전환", () => {
  it("초기 탭은 자금 배분 (position_sizing)", () => {
    renderPanel();
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText(/자금 배분/)).toBeInTheDocument();
  });

  it("탭 클릭 → 해당 폼으로 전환", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("tab", { name: /체결\/비용/ }));
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText(/체결\/비용 \(execution\)/)).toBeInTheDocument();
  });

  it("6 탭 모두 노출 (expert 모드 default)", () => {
    renderPanel();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(6);
    const labels = tabs.map((t) => t.textContent);
    expect(labels.some((l) => l?.includes("자금 배분"))).toBe(true);
    expect(labels.some((l) => l?.includes("예수금 관리"))).toBe(true);
    expect(labels.some((l) => l?.includes("리스크 관리"))).toBe(true);
    expect(labels.some((l) => l?.includes("체결/비용"))).toBe(true);
    expect(labels.some((l) => l?.includes("동시 신호 우선순위"))).toBe(true);
    expect(labels.some((l) => l?.includes("메타데이터"))).toBe(true);
  });

  it("초보자 모드 — position_sizing 탭만 노출 + 안내 문구", () => {
    window.localStorage.setItem("stockstrategy.builder_mode", "beginner");
    renderPanel();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(1);
    expect(tabs[0].textContent).toContain("자금 배분");
    expect(screen.getByText(/초보자 모드 — 자금 배분만 표시/)).toBeInTheDocument();
  });
});

describe("PositionSizingForm — 활성화 + 직렬화", () => {
  it("초기 비활성 → 직렬화에서 제외", () => {
    const { snap } = renderWithProbe();
    const out = snap() as { position_sizing?: unknown };
    expect(out.position_sizing).toBeUndefined();
  });

  it("활성화 + 금액/max_positions 변경 → 직렬화 반영", () => {
    const { snap } = renderWithProbe();
    fireEvent.click(screen.getByLabelText("자금 배분 (position_sizing) 활성화"));
    const panel = screen.getByRole("tabpanel");
    fireEvent.change(within(panel).getByLabelText("종목당 금액 (원)"), {
      target: { value: "750000" },
    });
    fireEvent.change(within(panel).getByLabelText("최대 보유 종목 수"), {
      target: { value: "8" },
    });
    const out = snap() as { position_sizing?: { amount?: number; max_positions?: number } };
    expect(out.position_sizing?.amount).toBe(750000);
    expect(out.position_sizing?.max_positions).toBe(8);
  });
});

describe("ExecutionForm — tax_rate 시계열 GUI (02-k)", () => {
  it("기본 시계열 — 한국 거래세 변동 (정확성 정책 13.6)", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("tab", { name: /체결\/비용/ }));
    const panel = screen.getByRole("tabpanel");
    // 4개 행 — 2020/2023/2024/2025
    expect(within(panel).getByLabelText("tax_rate 1 from")).toHaveValue("2020-01-01");
    expect(within(panel).getByLabelText("tax_rate 4 from")).toHaveValue("2025-01-01");
  });

  it("행 추가/삭제", () => {
    const { snap } = renderWithProbe();
    fireEvent.click(screen.getByRole("tab", { name: /체결\/비용/ }));
    fireEvent.click(screen.getByLabelText("체결/비용 (execution) 활성화"));

    const panel = screen.getByRole("tabpanel");
    // 새 행 추가
    fireEvent.click(within(panel).getByRole("button", { name: /거래세 행 추가/ }));
    fireEvent.change(within(panel).getByLabelText("tax_rate 5 from"), {
      target: { value: "2026-01-01" },
    });
    fireEvent.change(within(panel).getByLabelText("tax_rate 5 rate"), {
      target: { value: "0.001" },
    });
    const out = snap() as { execution?: { tax_rate?: Array<{ from: string; rate: number }> } };
    expect(out.execution?.tax_rate).toContainEqual({ from: "2026-01-01", rate: 0.001 });

    // 마지막 행 삭제
    fireEvent.click(within(panel).getByLabelText("tax_rate 5 삭제"));
    const out2 = snap() as { execution?: { tax_rate?: Array<{ from: string; rate: number }> } };
    expect(out2.execution?.tax_rate).not.toContainEqual({ from: "2026-01-01", rate: 0.001 });
  });

  it("single 모드 전환 → 단일 float 직렬화", () => {
    const { snap } = renderWithProbe();
    fireEvent.click(screen.getByRole("tab", { name: /체결\/비용/ }));
    fireEvent.click(screen.getByLabelText("체결/비용 (execution) 활성화"));

    const panel = screen.getByRole("tabpanel");
    fireEvent.change(within(panel).getByLabelText("거래세 입력 방식"), {
      target: { value: "single" },
    });
    fireEvent.change(within(panel).getByLabelText("단일 세율"), {
      target: { value: "0.002" },
    });
    const out = snap() as { execution?: { tax_rate?: number } };
    expect(out.execution?.tax_rate).toBe(0.002);
  });
});

describe("PriorityForm + MetadataForm — random_seed 정책", () => {
  it("priority.random 선택 시 시드 안내 메시지", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("tab", { name: /동시 신호 우선순위/ }));
    fireEvent.click(screen.getByLabelText("동시 신호 우선순위 (priority) 활성화"));
    const panel = screen.getByRole("tabpanel");
    fireEvent.change(within(panel).getByLabelText("우선순위 방식"), { target: { value: "random" } });
    expect(within(panel).getByText(/random_seed를 입력해야/)).toBeInTheDocument();
  });

  it("metadata.random_seed 미입력 → 직렬화 제외, 입력 시 포함, schema_version은 fixed", () => {
    const { snap } = renderWithProbe();
    fireEvent.click(screen.getByRole("tab", { name: /메타데이터/ }));
    fireEvent.click(screen.getByLabelText("메타데이터 (metadata) 활성화"));
    let out = snap() as { metadata?: { schema_version: string; random_seed?: number } };
    expect(out.metadata?.schema_version).toBe(STRATEGY_SCHEMA_VERSION);
    expect(out.metadata?.random_seed).toBeUndefined();

    const panel = screen.getByRole("tabpanel");
    fireEvent.change(within(panel).getByLabelText("random_seed"), { target: { value: "42" } });
    out = snap() as { metadata?: { schema_version: string; random_seed?: number } };
    expect(out.metadata?.random_seed).toBe(42);
  });

  it("metadata 태그 추가/삭제", () => {
    const { snap } = renderWithProbe();
    fireEvent.click(screen.getByRole("tab", { name: /메타데이터/ }));
    fireEvent.click(screen.getByLabelText("메타데이터 (metadata) 활성화"));
    const panel = screen.getByRole("tabpanel");
    const input = within(panel).getByLabelText("새 태그");
    fireEvent.change(input, { target: { value: "거래량" } });
    fireEvent.click(within(panel).getByRole("button", { name: "추가" }));
    let out = snap() as { metadata?: { tags?: string[] } };
    expect(out.metadata?.tags).toEqual(["거래량"]);

    // 같은 태그 다시 추가 → 무시
    fireEvent.change(input, { target: { value: "거래량" } });
    fireEvent.click(within(panel).getByRole("button", { name: "추가" }));
    out = snap() as { metadata?: { tags?: string[] } };
    expect(out.metadata?.tags).toEqual(["거래량"]);

    // 삭제
    fireEvent.click(within(panel).getByLabelText("태그 거래량 삭제"));
    out = snap() as { metadata?: { tags?: string[] } };
    expect(out.metadata).toBeDefined();
    expect(out.metadata?.tags).toBeUndefined(); // 빈 배열은 직렬화 제외
  });
});

describe("CashManagementForm — threshold 트리거", () => {
  it("trigger=cash_below_threshold 선택 → threshold 입력 노출", () => {
    const { snap } = renderWithProbe();
    fireEvent.click(screen.getByRole("tab", { name: /예수금 관리/ }));
    fireEvent.click(screen.getByLabelText("예수금 관리 (cash_management) 활성화"));
    const panel = screen.getByRole("tabpanel");
    fireEvent.change(within(panel).getByLabelText("부족 판단"), {
      target: { value: "cash_below_threshold" },
    });
    fireEvent.change(within(panel).getByLabelText("기준 금액 (원)"), {
      target: { value: "300000" },
    });
    const out = snap() as {
      cash_management?: { shortage_rule?: { trigger: { type: string; threshold?: number } } };
    };
    expect(out.cash_management?.shortage_rule?.trigger).toEqual({
      type: "cash_below_threshold",
      threshold: 300000,
    });
  });
});

