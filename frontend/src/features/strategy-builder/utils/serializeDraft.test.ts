import { describe, expect, it } from "vitest";
import { serializeDraft } from "./serializeDraft";
import { emptyDraft } from "../state/types";
import type { ConditionMeta } from "../../../types/condition";

const META = (type: string): ConditionMeta => ({
  type,
  category: "x",
  requires_position: false,
  name: type,
  description: "",
  sentence_template: type,
  parameters: [],
  allowed_in: ["entry"],
});

describe("serializeDraft", () => {
  it("빈 draft → name만", () => {
    const out = serializeDraft({ ...emptyDraft("X"), name: "X" });
    expect(out).toEqual({ name: "X" });
  });

  it("entry 단일 조건 → 평탄화 (instance_id/meta 제거)", () => {
    const draft = emptyDraft("S");
    draft.sections.entry.conditions.push({
      instance_id: "tmp",
      type: "price_vs_ma",
      values: { price_field: "adj_close", ma_period: 20, operator: ">" },
      meta: META("price_vs_ma"),
    });
    const out = serializeDraft(draft);
    expect(out.entry).toEqual({
      logic: "AND",
      conditions: [
        { type: "price_vs_ma", price_field: "adj_close", ma_period: 20, operator: ">" },
      ],
    });
  });

  it("exit_position OR + 두 조건", () => {
    const draft = emptyDraft("S");
    draft.sections.exit_position.conditions.push(
      {
        instance_id: "a",
        type: "take_profit",
        values: { percent: 7 },
        meta: META("take_profit"),
      },
      {
        instance_id: "b",
        type: "stop_loss",
        values: { percent: 3 },
        meta: META("stop_loss"),
      },
    );
    const out = serializeDraft(draft);
    expect(out.exit_position?.logic).toBe("OR");
    expect(out.exit_position?.conditions).toEqual([
      { type: "take_profit", percent: 7 },
      { type: "stop_loss", percent: 3 },
    ]);
  });
});
