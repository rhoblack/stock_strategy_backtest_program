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

describe("draftReducer (조건 섹션)", () => {
  beforeEach(() => _resetIdCounterForTests());

  it("초기 상태", () => {
    const s = emptyDraft("새 전략");
    expect(s.name).toBe("새 전략");
    expect(s.sections.entry.logic).toBe("AND");
    expect(s.sections.exit_position.logic).toBe("OR");
    expect(s.selected).toBeNull();
    // 6 비조건 섹션 default
    expect(s.position_sizing.enabled).toBe(false);
    expect(s.execution.enabled).toBe(false);
    expect(s.metadata.random_seed).toBe("");
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
    s = draftReducer(s, { type: "SET_LOGIC", section: "entry", logic: "GROUP" });
    expect(s.sections.entry.logic).toBe("GROUP");
  });

  it("ADD_CONDITION (take_profit) → exit_position 섹션", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_CONDITION", section: "exit_position", meta: TAKE_PROFIT });
    expect(s.sections.exit_position.conditions).toHaveLength(1);
    expect(s.sections.exit_position.conditions[0].values.percent).toBe(7.0);
  });

  it("RESET — 빈 상태로 복원 (6 비조건 섹션 default도 초기화)", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_CONDITION", section: "entry", meta: PRICE_VS_MA });
    s = draftReducer(s, { type: "POSITION_SIZING_SET", patch: { enabled: true, amount: 9 } });
    s = draftReducer(s, { type: "RESET", name: "새것" });
    expect(s.name).toBe("새것");
    expect(s.sections.entry.conditions).toHaveLength(0);
    expect(s.position_sizing.enabled).toBe(false);
    expect(s.position_sizing.amount).toBe(1_000_000);
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

describe("draftReducer (GROUP — 02번 §4)", () => {
  beforeEach(() => _resetIdCounterForTests());

  it("ADD_GROUP → 새 그룹 추가 (1단계)", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "SET_LOGIC", section: "entry", logic: "GROUP" });
    s = draftReducer(s, { type: "ADD_GROUP", section: "entry", logic: "AND" });
    expect(s.sections.entry.groups).toHaveLength(1);
    expect(s.sections.entry.groups[0].logic).toBe("AND");
  });

  it("ADD_CONDITION with group_id → 해당 그룹 안에 추가", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_GROUP", section: "entry", logic: "AND" });
    const gid = s.sections.entry.groups[0].group_id;
    s = draftReducer(s, {
      type: "ADD_CONDITION",
      section: "entry",
      meta: PRICE_VS_MA,
      group_id: gid,
    });
    expect(s.sections.entry.groups[0].conditions).toHaveLength(1);
    // section.conditions는 영향 없음
    expect(s.sections.entry.conditions).toHaveLength(0);
  });

  it("SET_GROUP_OPERATOR — GROUP 결합 연산자 변경", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "SET_GROUP_OPERATOR", section: "entry", operator: "AND" });
    expect(s.sections.entry.group_operator).toBe("AND");
  });

  it("REMOVE_GROUP — 그룹 제거", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "ADD_GROUP", section: "entry" });
    const gid = s.sections.entry.groups[0].group_id;
    s = draftReducer(s, { type: "REMOVE_GROUP", section: "entry", group_id: gid });
    expect(s.sections.entry.groups).toHaveLength(0);
  });
});

describe("draftReducer (6 비조건 섹션 — Wave 12-029)", () => {
  beforeEach(() => _resetIdCounterForTests());

  it("POSITION_SIZING_SET — 부분 패치", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "POSITION_SIZING_SET", patch: { enabled: true, amount: 500_000 } });
    expect(s.position_sizing.enabled).toBe(true);
    expect(s.position_sizing.amount).toBe(500_000);
    expect(s.position_sizing.method).toBe("fixed_amount"); // 다른 필드는 유지
  });

  it("CASH_MGMT_SET / RISK_MGMT_SET / PRIORITY_SET — 부분 패치", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "CASH_MGMT_SET", patch: { enabled: true } });
    s = draftReducer(s, { type: "RISK_MGMT_SET", patch: { stop_trading_on_drawdown_pct: 30 } });
    s = draftReducer(s, { type: "PRIORITY_SET", patch: { method: "market_cap_desc" } });
    expect(s.cash_management.enabled).toBe(true);
    expect(s.risk_management.stop_trading_on_drawdown_pct).toBe(30);
    expect(s.priority.method).toBe("market_cap_desc");
  });

  it("EXECUTION_TAX_ADD/REMOVE/UPDATE — 거래세 시계열 행 관리", () => {
    let s = emptyDraft();
    const initial = s.execution.tax_rate_timeseries.length;
    s = draftReducer(s, { type: "EXECUTION_TAX_ADD" });
    expect(s.execution.tax_rate_timeseries).toHaveLength(initial + 1);
    s = draftReducer(s, {
      type: "EXECUTION_TAX_UPDATE",
      index: initial,
      patch: { from: "2026-01-01", rate: 0.001 },
    });
    expect(s.execution.tax_rate_timeseries[initial]).toEqual({ from: "2026-01-01", rate: 0.001 });
    s = draftReducer(s, { type: "EXECUTION_TAX_REMOVE", index: initial });
    expect(s.execution.tax_rate_timeseries).toHaveLength(initial);
  });

  it("METADATA_ADD_TAG — 중복 무시 + trim", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "METADATA_ADD_TAG", tag: "  스윙  " });
    expect(s.metadata.tags).toEqual(["스윙"]);
    s = draftReducer(s, { type: "METADATA_ADD_TAG", tag: "스윙" });
    expect(s.metadata.tags).toEqual(["스윙"]); // 중복 추가 없음
    s = draftReducer(s, { type: "METADATA_REMOVE_TAG", tag: "스윙" });
    expect(s.metadata.tags).toEqual([]);
  });

  it("METADATA_SET — random_seed 입력 + 빈 문자열 처리", () => {
    let s = emptyDraft();
    s = draftReducer(s, { type: "METADATA_SET", patch: { random_seed: 42 } });
    expect(s.metadata.random_seed).toBe(42);
    s = draftReducer(s, { type: "METADATA_SET", patch: { random_seed: "" } });
    expect(s.metadata.random_seed).toBe("");
  });
});

describe("draftReducer (APPLY_TEMPLATE — Wave 12-030)", () => {
  beforeEach(() => _resetIdCounterForTests());

  it("APPLY_TEMPLATE — 임의의 draft로 전체 교체 + selected는 항상 null", () => {
    let s = emptyDraft("기존 이름");
    s = draftReducer(s, { type: "ADD_CONDITION", section: "entry", meta: PRICE_VS_MA });
    s = draftReducer(s, { type: "POSITION_SIZING_SET", patch: { enabled: true, amount: 999 } });

    const tplDraft = emptyDraft("새 템플릿 전략");
    tplDraft.position_sizing.enabled = true;
    tplDraft.position_sizing.amount = 1_500_000;
    tplDraft.execution.enabled = true;

    const next = draftReducer(s, { type: "APPLY_TEMPLATE", draft: tplDraft });
    expect(next.name).toBe("새 템플릿 전략");
    expect(next.sections.entry.conditions).toHaveLength(0); // 기존 조건 사라짐
    expect(next.position_sizing.amount).toBe(1_500_000); // 템플릿 값 적용
    expect(next.execution.enabled).toBe(true);
    expect(next.selected).toBeNull(); // 항상 null로 reset
  });

  it("APPLY_TEMPLATE — RESET과 다르게 빈 default가 아닌 임의 값 적용 가능", () => {
    const s = emptyDraft();
    const tplDraft = emptyDraft("골든");
    tplDraft.priority.enabled = true;
    tplDraft.priority.method = "market_cap_desc";
    const next = draftReducer(s, { type: "APPLY_TEMPLATE", draft: tplDraft });
    expect(next.priority.enabled).toBe(true);
    expect(next.priority.method).toBe("market_cap_desc");
  });
});
