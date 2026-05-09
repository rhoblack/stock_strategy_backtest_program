import { describe, expect, it } from "vitest";
import { renderSentence } from "./renderSentence";
import type { ConditionMeta } from "../../../types/condition";
import type { ConditionInstance } from "../state/types";

const meta: ConditionMeta = {
  type: "price_vs_ma",
  category: "moving_average",
  requires_position: false,
  name: "가격과 이동평균 비교",
  description: "",
  sentence_template: "{price_field}가 {ma_period}일 이동평균선보다 {operator_label}",
  parameters: [
    {
      name: "price_field",
      label: "가격",
      input_type: "select",
      default: "adj_close",
      options: [
        { label: "수정 종가", value: "adj_close" },
        { label: "수정 시가", value: "adj_open" },
      ],
    },
    { name: "ma_period", label: "MA", input_type: "number", default: 20 },
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
  allowed_in: ["entry"],
};

function makeInstance(values: Record<string, string | number | boolean>): ConditionInstance {
  return { instance_id: "x", type: meta.type, values, meta };
}

describe("renderSentence", () => {
  it("select 값을 label로 치환", () => {
    const text = renderSentence(
      makeInstance({ price_field: "adj_close", ma_period: 20, operator: ">" }),
    );
    expect(text).toBe("수정 종가가 20일 이동평균선보다 위");
  });

  it("operator_label 별칭 치환", () => {
    const text = renderSentence(
      makeInstance({ price_field: "adj_open", ma_period: 5, operator: "<" }),
    );
    expect(text).toBe("수정 시가가 5일 이동평균선보다 아래");
  });

  it("값 없으면 placeholder 유지", () => {
    const text = renderSentence(makeInstance({}));
    // {price_field} 등이 그대로 (혹은 빈 문자열)
    expect(text).toContain("이동평균선보다");
  });
});
