import { describe, expect, it, beforeEach } from "vitest";
import {
  STRATEGY_TEMPLATES,
  buildDraftFromTemplate,
  getTemplateById,
  _resetTemplateIdCounterForTests,
} from "./templates";
import type { ConditionMeta } from "../../../types/condition";

const PRICE_VS_MA: ConditionMeta = {
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
  allowed_in: ["entry", "exit_signal", "filters"],
};

const TAKE_PROFIT: ConditionMeta = {
  type: "take_profit",
  category: "exit_position",
  requires_position: true,
  name: "익절",
  description: "",
  sentence_template: "수익률 {percent}% 이상이면 익절",
  parameters: [{ name: "percent", label: "%", input_type: "number", default: 7.0 }],
  allowed_in: ["exit_position"],
};

const STOP_LOSS: ConditionMeta = {
  type: "stop_loss",
  category: "exit_position",
  requires_position: true,
  name: "손절",
  description: "",
  sentence_template: "수익률 {percent}% 이하면 손절",
  parameters: [{ name: "percent", label: "%", input_type: "number", default: 5.0 }],
  allowed_in: ["exit_position"],
};

const RSI: ConditionMeta = {
  type: "rsi",
  category: "oscillator",
  requires_position: false,
  name: "RSI",
  description: "",
  sentence_template: "RSI({period}) {operator} {threshold}",
  parameters: [
    { name: "period", label: "기간", input_type: "number", default: 14 },
    { name: "operator", label: "비교", input_type: "select", default: "<" },
    { name: "threshold", label: "기준값", input_type: "number", default: 30 },
  ],
  allowed_in: ["entry", "exit_signal", "filters"],
};

const NEW_HIGH: ConditionMeta = {
  type: "new_high",
  category: "price_action",
  requires_position: false,
  name: "신고가",
  description: "",
  sentence_template: "{period}일 신고가 돌파",
  parameters: [{ name: "period", label: "기간", input_type: "number", default: 20 }],
  allowed_in: ["entry", "exit_signal", "filters"],
};

const VOLUME_RATIO: ConditionMeta = {
  type: "volume_ratio",
  category: "volume",
  requires_position: false,
  name: "거래량 비율",
  description: "",
  sentence_template: "거래량이 {period}일 평균의 {threshold}배 {operator}",
  parameters: [
    { name: "period", label: "기간", input_type: "number", default: 20 },
    { name: "operator", label: "비교", input_type: "select", default: ">" },
    { name: "threshold", label: "배수", input_type: "number", default: 2.0 },
  ],
  allowed_in: ["entry", "exit_signal", "filters"],
};

const FULL_CATALOG: ConditionMeta[] = [
  PRICE_VS_MA,
  TAKE_PROFIT,
  STOP_LOSS,
  RSI,
  NEW_HIGH,
  VOLUME_RATIO,
];

describe("STRATEGY_TEMPLATES 카탈로그", () => {
  it("4종 정의: empty / golden_cross / rsi_oversold / momentum_breakout", () => {
    const ids = STRATEGY_TEMPLATES.map((t) => t.id);
    expect(ids).toContain("empty");
    expect(ids).toContain("golden_cross");
    expect(ids).toContain("rsi_oversold");
    expect(ids).toContain("momentum_breakout");
    expect(STRATEGY_TEMPLATES.length).toBe(4);
  });

  it("getTemplateById — id로 lookup", () => {
    expect(getTemplateById("golden_cross")?.name).toBe("골든 크로스 (5/20 MA)");
    expect(getTemplateById("does_not_exist")).toBeUndefined();
  });

  it("모든 템플릿이 필수 필드 보유", () => {
    for (const t of STRATEGY_TEMPLATES) {
      expect(t.id).toBeTruthy();
      expect(t.name).toBeTruthy();
      expect(t.description).toBeTruthy();
      expect(t.category).toBeTruthy();
    }
  });
});

describe("buildDraftFromTemplate", () => {
  beforeEach(() => _resetTemplateIdCounterForTests());

  it("빈 전략 — 모든 조건/섹션 비어있음", () => {
    const tpl = getTemplateById("empty")!;
    const draft = buildDraftFromTemplate(tpl, FULL_CATALOG);
    expect(draft.name).toBe("");
    expect(draft.sections.entry.conditions).toHaveLength(0);
    expect(draft.sections.exit_position.conditions).toHaveLength(0);
    expect(draft.position_sizing.enabled).toBe(false);
    expect(draft.execution.enabled).toBe(false);
  });

  it("골든 크로스 — entry + exit_position + position_sizing/execution/priority 활성", () => {
    const tpl = getTemplateById("golden_cross")!;
    const draft = buildDraftFromTemplate(tpl, FULL_CATALOG);
    expect(draft.name).toBe("골든 크로스 (5/20 MA)");
    expect(draft.sections.entry.conditions).toHaveLength(1);
    expect(draft.sections.entry.conditions[0].type).toBe("price_vs_ma");
    expect(draft.sections.entry.conditions[0].values.ma_period).toBe(20);

    expect(draft.sections.exit_position.conditions).toHaveLength(2);
    expect(draft.sections.exit_position.conditions[0].type).toBe("take_profit");
    expect(draft.sections.exit_position.conditions[0].values.percent).toBe(7.0);
    expect(draft.sections.exit_position.conditions[1].type).toBe("stop_loss");
    expect(draft.sections.exit_position.conditions[1].values.percent).toBe(5.0);

    expect(draft.position_sizing.enabled).toBe(true);
    expect(draft.position_sizing.amount).toBe(1_000_000);
    expect(draft.execution.enabled).toBe(true);
    expect(draft.priority.enabled).toBe(true);
    expect(draft.priority.method).toBe("trading_value_desc");
  });

  it("RSI 과매도 — entry + exit_signal + exit_position", () => {
    const tpl = getTemplateById("rsi_oversold")!;
    const draft = buildDraftFromTemplate(tpl, FULL_CATALOG);
    expect(draft.sections.entry.conditions[0].type).toBe("rsi");
    expect(draft.sections.entry.conditions[0].values.threshold).toBe(30);
    expect(draft.sections.exit_signal.conditions[0].type).toBe("rsi");
    expect(draft.sections.exit_signal.conditions[0].values.threshold).toBe(50);
    expect(draft.sections.exit_position.conditions[0].type).toBe("stop_loss");
  });

  it("모멘텀 — entry 2개 (new_high + volume_ratio) + filters/priority 활성", () => {
    const tpl = getTemplateById("momentum_breakout")!;
    const draft = buildDraftFromTemplate(tpl, FULL_CATALOG);
    expect(draft.sections.entry.conditions).toHaveLength(2);
    expect(draft.sections.entry.conditions.map((c) => c.type).sort()).toEqual(
      ["new_high", "volume_ratio"].sort(),
    );
    expect(draft.priority.enabled).toBe(true);
    expect(draft.priority.method).toBe("volume_ratio_desc");
  });

  it("카탈로그에 없는 condition type은 스킵 (skip silently)", () => {
    const tpl = getTemplateById("golden_cross")!;
    // catalog에 take_profit/stop_loss 빠뜨림
    const partialCatalog = [PRICE_VS_MA];
    const draft = buildDraftFromTemplate(tpl, partialCatalog);
    expect(draft.sections.entry.conditions).toHaveLength(1);
    expect(draft.sections.exit_position.conditions).toHaveLength(0); // 둘 다 스킵
  });

  it("결정론 — 같은 카탈로그/템플릿이면 conditions 순서 일치", () => {
    const tpl = getTemplateById("momentum_breakout")!;
    _resetTemplateIdCounterForTests();
    const d1 = buildDraftFromTemplate(tpl, FULL_CATALOG);
    _resetTemplateIdCounterForTests();
    const d2 = buildDraftFromTemplate(tpl, FULL_CATALOG);
    expect(d1.sections.entry.conditions.map((c) => c.type)).toEqual(
      d2.sections.entry.conditions.map((c) => c.type),
    );
  });

  it("name 인자 — 명시 시 override", () => {
    const tpl = getTemplateById("golden_cross")!;
    const draft = buildDraftFromTemplate(tpl, FULL_CATALOG, "내 골든");
    expect(draft.name).toBe("내 골든");
  });
});
