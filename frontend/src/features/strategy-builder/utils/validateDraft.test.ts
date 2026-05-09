import { describe, expect, it } from "vitest";
import { hasErrors, validateDraft } from "./validateDraft";
import { emptyDraft } from "../state/types";
import type { ConditionMeta } from "../../../types/condition";

const FAKE_META = (type: string): ConditionMeta => ({
  type,
  category: "x",
  requires_position: false,
  name: type,
  description: "",
  sentence_template: type,
  parameters: [],
  allowed_in: ["entry"],
});

function makeInst(type: string) {
  return {
    instance_id: type,
    type,
    values: {},
    meta: FAKE_META(type),
  };
}

describe("validateDraft", () => {
  it("빈 draft → entry 없음 + 매도 없음 + 유동성 필터 없음", () => {
    const items = validateDraft(emptyDraft());
    const codes = items.map((i) => i.code);
    expect(codes).toContain("ENTRY_REQUIRED");
    expect(codes).toContain("EXIT_MISSING");
    expect(codes).toContain("NO_LIQUIDITY_FILTER");
    expect(hasErrors(items)).toBe(true);
  });

  it("entry 추가 → ENTRY_REQUIRED 사라짐", () => {
    const draft = emptyDraft();
    draft.sections.entry.conditions.push(makeInst("price_vs_ma"));
    const items = validateDraft(draft);
    expect(items.map((i) => i.code)).not.toContain("ENTRY_REQUIRED");
    expect(hasErrors(items)).toBe(false);
  });

  it("exit_position에 take_profit만 있고 stop_loss 없음 → NO_STOP_LOSS 경고", () => {
    const draft = emptyDraft();
    draft.sections.entry.conditions.push(makeInst("price_vs_ma"));
    draft.sections.exit_position.conditions.push(makeInst("take_profit"));
    const items = validateDraft(draft);
    expect(items.map((i) => i.code)).toContain("NO_STOP_LOSS");
  });

  it("exit_position에 stop_loss 있으면 NO_STOP_LOSS 경고 없음", () => {
    const draft = emptyDraft();
    draft.sections.entry.conditions.push(makeInst("price_vs_ma"));
    draft.sections.exit_position.conditions.push(makeInst("take_profit"));
    draft.sections.exit_position.conditions.push(makeInst("stop_loss"));
    const items = validateDraft(draft);
    expect(items.map((i) => i.code)).not.toContain("NO_STOP_LOSS");
  });

  it("filters에 avg_trading_value 추가 → NO_LIQUIDITY_FILTER 사라짐", () => {
    const draft = emptyDraft();
    draft.sections.entry.conditions.push(makeInst("price_vs_ma"));
    draft.sections.filters.conditions.push(makeInst("avg_trading_value"));
    const items = validateDraft(draft);
    expect(items.map((i) => i.code)).not.toContain("NO_LIQUIDITY_FILTER");
  });
});
