import { describe, expect, it } from "vitest";
import {
  serializeDraft,
  type SerializedConditionsBlock,
  type SerializedGroupBlock,
  type SerializedSection,
  type SerializedTaxRateBracket,
} from "./serializeDraft";
import { emptyDraft } from "../state/types";
import type { ConditionMeta } from "../../../types/condition";
import { STRATEGY_SCHEMA_VERSION } from "../state/strategySections";

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

function asAndOr(s: SerializedSection | undefined): SerializedConditionsBlock {
  if (!s || s.logic === "GROUP") {
    throw new Error("expected AND/OR section");
  }
  return s;
}

function asGroup(s: SerializedSection | undefined): SerializedGroupBlock {
  if (!s || s.logic !== "GROUP") {
    throw new Error("expected GROUP section");
  }
  return s;
}

describe("serializeDraft (4 조건 섹션)", () => {
  it("빈 draft → name만 (6 비조건 섹션 모두 enabled=false)", () => {
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
    expect(asAndOr(out.entry)).toEqual({
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
    const block = asAndOr(out.exit_position);
    expect(block.logic).toBe("OR");
    expect(block.conditions).toEqual([
      { type: "take_profit", percent: 7 },
      { type: "stop_loss", percent: 3 },
    ]);
  });
});

describe("serializeDraft (GROUP — 02번 §4)", () => {
  it("entry GROUP OR + 두 그룹 (각 그룹 AND) — 1단계 중첩", () => {
    const draft = emptyDraft("S");
    draft.sections.entry.logic = "GROUP";
    draft.sections.entry.group_operator = "OR";
    draft.sections.entry.groups = [
      {
        group_id: "g1",
        logic: "AND",
        conditions: [
          {
            instance_id: "a",
            type: "price_vs_ma",
            values: { price_field: "adj_close", ma_period: 20, operator: ">" },
            meta: META("price_vs_ma"),
          },
          {
            instance_id: "b",
            type: "volume_ratio",
            values: { period: 20, operator: ">=", value: 2.0 },
            meta: META("volume_ratio"),
          },
        ],
      },
      {
        group_id: "g2",
        logic: "AND",
        conditions: [
          {
            instance_id: "c",
            type: "rsi_level",
            values: { period: 14, operator: "<=", value: 30 },
            meta: META("rsi_level"),
          },
        ],
      },
    ];
    const out = serializeDraft(draft);
    const block = asGroup(out.entry);
    expect(block).toEqual({
      logic: "GROUP",
      operator: "OR",
      groups: [
        {
          logic: "AND",
          conditions: [
            { type: "price_vs_ma", price_field: "adj_close", ma_period: 20, operator: ">" },
            { type: "volume_ratio", period: 20, operator: ">=", value: 2.0 },
          ],
        },
        {
          logic: "AND",
          conditions: [{ type: "rsi_level", period: 14, operator: "<=", value: 30 }],
        },
      ],
    });
  });

  it("GROUP 모드여도 빈 그룹은 출력에서 제외 — 모두 비면 섹션 자체 생략", () => {
    const draft = emptyDraft("S");
    draft.sections.entry.logic = "GROUP";
    draft.sections.entry.groups = [
      { group_id: "g1", logic: "AND", conditions: [] },
    ];
    const out = serializeDraft(draft);
    expect(out.entry).toBeUndefined();
  });
});

describe("serializeDraft (6 비조건 섹션 — Wave 12-029)", () => {
  it("position_sizing.enabled=true → method/amount/max_positions/allow_pyramiding", () => {
    const draft = emptyDraft("S");
    draft.position_sizing.enabled = true;
    draft.position_sizing.method = "fixed_amount";
    draft.position_sizing.amount = 1_500_000;
    draft.position_sizing.max_positions = 5;
    draft.position_sizing.max_daily_entries = 2;
    draft.position_sizing.daily_buy_budget = 1_500_000;
    draft.position_sizing.allow_pyramiding = false;
    const out = serializeDraft(draft);
    expect(out.position_sizing).toEqual({
      method: "fixed_amount",
      amount: 1_500_000,
      max_positions: 5,
      max_daily_entries: 2,
      daily_buy_budget: 1_500_000,
      allow_pyramiding: false,
    });
  });

  it("position_sizing.enabled=false → 출력에서 제외", () => {
    const draft = emptyDraft("S");
    expect(serializeDraft(draft).position_sizing).toBeUndefined();
  });

  it("cash_management 활성화 → shortage_rule 구조 포함", () => {
    const draft = emptyDraft("S");
    draft.cash_management.enabled = true;
    draft.cash_management.trigger_type = "cash_below_daily_buy_budget";
    draft.cash_management.sell_fraction = 0.25;
    draft.cash_management.target_method = "lowest_return";
    draft.cash_management.repeat_until_cash_sufficient = true;
    const out = serializeDraft(draft);
    expect(out.cash_management).toEqual({
      enabled: true,
      shortage_rule: {
        trigger: { type: "cash_below_daily_buy_budget" },
        action: { type: "partial_sell", sell_fraction: 0.25 },
        target_selection: { method: "lowest_return" },
        repeat_until_cash_sufficient: true,
      },
    });
  });

  it("cash_management trigger=cash_below_threshold + threshold 입력", () => {
    const draft = emptyDraft("S");
    draft.cash_management.enabled = true;
    draft.cash_management.trigger_type = "cash_below_threshold";
    draft.cash_management.trigger_threshold = 500_000;
    draft.cash_management.sell_fraction = 0.5;
    const out = serializeDraft(draft);
    expect(out.cash_management?.shortage_rule?.trigger).toEqual({
      type: "cash_below_threshold",
      threshold: 500_000,
    });
  });

  it("risk_management 활성화 → drawdown_pct만 입력", () => {
    const draft = emptyDraft("S");
    draft.risk_management.enabled = true;
    draft.risk_management.stop_trading_on_drawdown_pct = 25;
    const out = serializeDraft(draft);
    expect(out.risk_management).toEqual({ stop_trading_on_drawdown_pct: 25 });
  });

  it("execution 활성화 + tax_rate 시계열 (정확성 정책 13.6)", () => {
    const draft = emptyDraft("S");
    draft.execution.enabled = true;
    const out = serializeDraft(draft);
    expect(out.execution?.entry_price).toBe("next_open");
    expect(out.execution?.fee_rate).toBe(0.00015);
    expect(out.execution?.tick_rounding).toBe("buy_up_sell_down");
    expect(out.execution?.use_adjusted_price).toBe(true);
    // 기본 시계열
    const tax = out.execution?.tax_rate as SerializedTaxRateBracket[];
    expect(Array.isArray(tax)).toBe(true);
    expect(tax[0]).toEqual({ from: "2020-01-01", rate: 0.0023 });
    expect(tax.at(-1)).toEqual({ from: "2025-01-01", rate: 0.0015 });
  });

  it("execution tax_rate single 모드 → float 직렬화", () => {
    const draft = emptyDraft("S");
    draft.execution.enabled = true;
    draft.execution.tax_rate_mode = "single";
    draft.execution.tax_rate_single = 0.002;
    const out = serializeDraft(draft);
    expect(out.execution?.tax_rate).toBe(0.002);
  });

  it("execution tax_rate timeseries 빈 행은 제외", () => {
    const draft = emptyDraft("S");
    draft.execution.enabled = true;
    draft.execution.tax_rate_mode = "timeseries";
    draft.execution.tax_rate_timeseries = [
      { from: "2025-01-01", rate: 0.0015 },
      { from: "", rate: "" }, // 빈 행
      { from: "2026-01-01", rate: "" }, // rate 없음
    ];
    const out = serializeDraft(draft);
    expect(out.execution?.tax_rate).toEqual([{ from: "2025-01-01", rate: 0.0015 }]);
  });

  it("priority 활성화 → method + tie_breaker", () => {
    const draft = emptyDraft("S");
    draft.priority.enabled = true;
    draft.priority.method = "market_cap_desc";
    draft.priority.tie_breaker = "symbol_asc";
    const out = serializeDraft(draft);
    expect(out.priority).toEqual({ method: "market_cap_desc", tie_breaker: "symbol_asc" });
  });

  it("metadata 활성화 → schema_version fixed + random_seed 사용자 입력 시만", () => {
    const draft = emptyDraft("S");
    draft.metadata.enabled = true;
    draft.metadata.random_seed = 42;
    draft.metadata.tags = ["스윙", "거래량"];
    draft.metadata.favorite = true;
    const out = serializeDraft(draft);
    expect(out.metadata).toEqual({
      schema_version: STRATEGY_SCHEMA_VERSION,
      random_seed: 42,
      tags: ["스윙", "거래량"],
      favorite: true,
    });
  });

  it("metadata random_seed 미입력 → 직렬화에서 제외 (자동 생성 금지 정책)", () => {
    const draft = emptyDraft("S");
    draft.metadata.enabled = true;
    const out = serializeDraft(draft);
    expect(out.metadata?.schema_version).toBe(STRATEGY_SCHEMA_VERSION);
    expect(out.metadata?.random_seed).toBeUndefined();
  });
});
