import { describe, expect, it } from "vitest";
import { buildPreviewText } from "./buildPreviewText";
import { emptyDraft } from "../state/types";
import type { ConditionMeta } from "../../../types/condition";

const PRICE_VS_MA: ConditionMeta = {
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
};

describe("buildPreviewText", () => {
  it("빈 draft 안내", () => {
    const lines = buildPreviewText(emptyDraft());
    expect(lines.join("\n")).toMatch(/조건이 없습니다/);
  });

  it("entry 단일 조건 → 매수 조건 헤더 + 문장", () => {
    const draft = emptyDraft();
    draft.sections.entry.conditions.push({
      instance_id: "x",
      type: "price_vs_ma",
      values: { price_field: "adj_close", ma_period: 20, operator: ">" },
      meta: PRICE_VS_MA,
    });
    const lines = buildPreviewText(draft);
    expect(lines[0]).toBe("매수 조건");
    expect(lines[1]).toContain("수정 종가가 20일 MA보다 위");
  });

  it("AND 2개 → '모두 만족' 라벨", () => {
    const draft = emptyDraft();
    draft.sections.entry.logic = "AND";
    draft.sections.entry.conditions.push(
      { instance_id: "a", type: "price_vs_ma", values: { price_field: "adj_close", ma_period: 5, operator: ">" }, meta: PRICE_VS_MA },
      { instance_id: "b", type: "price_vs_ma", values: { price_field: "adj_close", ma_period: 20, operator: ">" }, meta: PRICE_VS_MA },
    );
    const lines = buildPreviewText(draft);
    expect(lines[0]).toContain("모두 만족");
  });
});
