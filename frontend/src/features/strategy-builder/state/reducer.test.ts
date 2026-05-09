import { describe, expect, it, beforeEach } from "vitest";
import { _resetIdCounterForTests, draftReducer } from "./reducer";
import { emptyDraft } from "./types";
import type { ConditionMeta } from "../../../types/condition";

const PRICE_VS_MA: ConditionMeta = {
  type: "price_vs_ma",
  category: "moving_average",
  requires_position: false,
  name: "가격과 이동평균 비교",
  description: "",
  sentence_template: "{price_field}가 {ma_period}일 MA보다 {operator}",
  parameters: [
    { name: "price_field", label: "가격", input_type: "select", default: "adj_close",
      options: [{ label: "수정 종가", value: "adj_close" }] },
    { name: "ma_period", label: "MA 기간", input_type: "number", default: 20 },
    { name: "operator", label: "비교", input_type: "select", default: ">",
      options: [{ label: "위", value: ">" }, { label: "아래", value: "<" }] },
  ],
  allowed_in: ["entry", "exit_signal", "filters"],
};

const TAKE_PROFIT: ConditionMeta = {
  type: "take_profit",
  category: "exit_position",
  requires_position: true,
  name: "익절",
  description: "",
  sentence_template: "수익률 {percent}% 이상이면 익절",
  parameters: [
    { name: "percent", label: "%", input_type: "number", default: 7.0 },
  ],
  allowed_in: ["exit_position"],
};

describe("draftReducer", () => {
  beforeEach(() => _resetIdCounterForTests());

  it("초기 상태", () => {
    const s = emptyDraft("새 전략");
    expect(s.name).toBe("새 전략");
    expect(s.sections.entry.logic).toBe("AND");
    expect(s.sections.exit_position.logic).toBe("OR");
    expect(s.selected).toBeNull();
  });

  it("ADD_CONDITION → entry 섹션에 instance 추가 + 자동 선택", () => {
    const s1 = emptyDraft();
    const s2 = draftReducer(s1, { type: "ADD_CONDITION", section: "entry", meta: PRICE_VS_MA });
    expect(s2.sections.entry.conditions).toHaveLength(1);
    const inst = s2.sections.entry.conditions[0];
    expect(inst.type).toBe("price_vs_ma");
    expect(inst.values).toEqual({ price_field: "adj_close", ma_period: 20, operator: ">" });
    expect(s2.selected?.instance_id).toBe(inst.instance_id);
  });

  it("UPDATE_VALUE — 특정 instance의 값 갱신", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_CONDITION", section: "entry", meta: PRICE_VS_MA });
    const id = s.sections.entry.conditions[0].instance_id;
    s = draftReducer(s, {
      type: "UPDATE_VALUE",
      section: "entry",
      instance_id: id,
      name: "ma_period",
      value: 5,
    });
    expect(s.sections.entry.conditions[0].values.ma_period).toBe(5);
  });

  it("REMOVE_CONDITION — 삭제 + 선택 해제", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_CONDITION", section: "entry", meta: PRICE_VS_MA });
    const id = s.sections.entry.conditions[0].instance_id;
    s = draftReducer(s, { type: "REMOVE_CONDITION", section: "entry", instance_id: id });
    expect(s.sections.entry.conditions).toHaveLength(0);
    expect(s.selected).toBeNull();
  });

  it("SET_LOGIC — section logic 변경", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "SET_LOGIC", section: "entry", logic: "OR" });
    expect(s.sections.entry.logic).toBe("OR");
  });

  it("ADD_CONDITION (take_profit) → exit_position 섹션", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_CONDITION", section: "exit_position", meta: TAKE_PROFIT });
    expect(s.sections.exit_position.conditions).toHaveLength(1);
    expect(s.sections.exit_position.conditions[0].values.percent).toBe(7.0);
  });

  it("RESET — 빈 상태로 복원", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_CONDITION", section: "entry", meta: PRICE_VS_MA });
    s = draftReducer(s, { type: "RESET", name: "새것" });
    expect(s.name).toBe("새것");
    expect(s.sections.entry.conditions).toHaveLength(0);
  });

  it("SELECT / CLEAR_SELECTION", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_CONDITION", section: "entry", meta: PRICE_VS_MA });
    const id = s.sections.entry.conditions[0].instance_id;
    s = draftReducer(s, { type: "CLEAR_SELECTION" });
    expect(s.selected).toBeNull();
    s = draftReducer(s, { type: "SELECT", section: "entry", instance_id: id });
    expect(s.selected?.instance_id).toBe(id);
  });
});
