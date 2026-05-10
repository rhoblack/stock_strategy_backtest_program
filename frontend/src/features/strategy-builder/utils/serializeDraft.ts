/**
 * StrategyDraft → 백엔드 strategy_json 형식 (02번 schema).
 *
 * 직렬화 규칙:
 *   - instance_id / group_id / meta는 직렬화에서 제거 (UI 전용)
 *   - 빈 섹션은 출력 키에서 제외 (예: filters에 조건이 없으면 키 자체 없음)
 *   - GROUP 모드: { logic: "GROUP", operator, groups: [{ logic, conditions }] }
 *   - AND/OR 모드: { logic, conditions }
 *
 * 6 비조건 섹션 (Wave 12-029):
 *   - 각 섹션 state.enabled === false 시 출력에서 제외 (사용자가 명시적으로
 *     켜지 않으면 백엔드 default를 사용하는 정책)
 *   - 빈 문자열("")은 "미입력"이며 출력에서 제외
 *   - random_seed는 숫자일 때만 직렬화 — 자동 생성/0 default 금지 (정책)
 *   - schema_version은 항상 fixed value ("1.0")
 *   - tax_rate는 모드에 따라 single float 또는 [{from, rate}] 시계열
 */

import type { ConditionInstance, GroupNode, SectionState, StrategyDraft, Section } from "../state/types";
import { STRATEGY_SCHEMA_VERSION } from "../state/strategySections";

const SECTIONS: Section[] = ["entry", "exit_signal", "exit_position", "filters"];

export type SerializedConditionsBlock = {
  logic: "AND" | "OR";
  conditions: SerializedCondition[];
};

export type SerializedGroupBlock = {
  logic: "GROUP";
  operator: "AND" | "OR";
  groups: SerializedConditionsBlock[];
};

export type SerializedSection = SerializedConditionsBlock | SerializedGroupBlock;

export type SerializedCondition = { type: string } & Record<string, unknown>;

export type SerializedTaxRateBracket = { from: string; rate: number };

export type SerializedExecution = {
  entry_price?: string;
  exit_price?: string;
  fee_rate?: number;
  slippage?: number;
  tax_rate?: number | SerializedTaxRateBracket[];
  use_adjusted_price?: boolean;
  max_gap_pct_for_entry?: number;
  allow_buy_limit_up?: boolean;
  allow_sell_limit_down?: boolean;
  tick_rounding?: string;
};

export type SerializedPositionSizing = {
  method: string;
  amount?: number;
  ratio?: number;
  max_positions?: number;
  max_daily_entries?: number;
  daily_buy_budget?: number;
  allow_pyramiding?: boolean;
};

export type SerializedCashManagement = {
  enabled: boolean;
  shortage_rule?: {
    trigger: { type: string; threshold?: number };
    action: { type: string; sell_fraction?: number };
    target_selection: { method: string };
    repeat_until_cash_sufficient?: boolean;
  };
};

export type SerializedRiskManagement = {
  stop_trading_on_drawdown_pct?: number;
  max_position_ratio?: number;
  max_daily_loss_pct?: number;
};

export type SerializedPriority = {
  method: string;
  tie_breaker: string;
};

export type SerializedMetadata = {
  schema_version: string;
  random_seed?: number;
  tags?: string[];
  favorite?: boolean;
};

export type SerializedStrategy = {
  name: string;
  entry?: SerializedSection;
  exit_signal?: SerializedSection;
  exit_position?: SerializedSection;
  filters?: SerializedSection;
  position_sizing?: SerializedPositionSizing;
  cash_management?: SerializedCashManagement;
  risk_management?: SerializedRiskManagement;
  execution?: SerializedExecution;
  priority?: SerializedPriority;
  metadata?: SerializedMetadata;
};

// --------------------------------------------------------------------------
// 조건 섹션 (entry/exit_signal/exit_position/filters)
// --------------------------------------------------------------------------

function serializeCondition(inst: ConditionInstance): SerializedCondition {
  return { type: inst.type, ...inst.values };
}

function serializeAndOrSection(sec: SectionState): SerializedConditionsBlock | null {
  if (sec.conditions.length === 0) return null;
  return {
    logic: sec.logic === "OR" ? "OR" : "AND",
    conditions: sec.conditions.map(serializeCondition),
  };
}

function serializeGroupSection(sec: SectionState): SerializedGroupBlock | null {
  // 비어있는 그룹은 백엔드 검증(C4)이 reject하므로 사전 필터링
  const nonEmptyGroups = sec.groups.filter((g: GroupNode) => g.conditions.length > 0);
  if (nonEmptyGroups.length === 0) return null;
  return {
    logic: "GROUP",
    operator: sec.group_operator,
    groups: nonEmptyGroups.map((g) => ({
      logic: g.logic,
      conditions: g.conditions.map(serializeCondition),
    })),
  };
}

function serializeSection(sec: SectionState): SerializedSection | null {
  if (sec.logic === "GROUP") return serializeGroupSection(sec);
  return serializeAndOrSection(sec);
}

// --------------------------------------------------------------------------
// 6 비조건 섹션 직렬화 헬퍼 (Wave 12-029)
// --------------------------------------------------------------------------

/** number | "" → number | undefined */
function num(v: number | "" | null | undefined): number | undefined {
  if (v === "" || v === null || v === undefined) return undefined;
  if (typeof v === "number" && !Number.isNaN(v)) return v;
  return undefined;
}

function serializePositionSizing(draft: StrategyDraft): SerializedPositionSizing | undefined {
  const ps = draft.position_sizing;
  if (!ps.enabled) return undefined;
  const out: SerializedPositionSizing = { method: ps.method };
  if (ps.method === "fixed_amount") {
    const v = num(ps.amount);
    if (v !== undefined) out.amount = v;
  }
  if (ps.method === "fixed_ratio") {
    const v = num(ps.ratio);
    if (v !== undefined) out.ratio = v;
  }
  const mp = num(ps.max_positions);
  if (mp !== undefined) out.max_positions = mp;
  const mde = num(ps.max_daily_entries);
  if (mde !== undefined) out.max_daily_entries = mde;
  const dbb = num(ps.daily_buy_budget);
  if (dbb !== undefined) out.daily_buy_budget = dbb;
  out.allow_pyramiding = ps.allow_pyramiding;
  return out;
}

function serializeCashManagement(draft: StrategyDraft): SerializedCashManagement | undefined {
  const cm = draft.cash_management;
  if (!cm.enabled) return undefined;
  const trigger: { type: string; threshold?: number } = { type: cm.trigger_type };
  if (cm.trigger_type === "cash_below_threshold") {
    const v = num(cm.trigger_threshold);
    if (v !== undefined) trigger.threshold = v;
  }
  const action: { type: string; sell_fraction?: number } = { type: cm.action_type };
  const sf = num(cm.sell_fraction);
  if (sf !== undefined) action.sell_fraction = sf;
  return {
    enabled: true,
    shortage_rule: {
      trigger,
      action,
      target_selection: { method: cm.target_method },
      repeat_until_cash_sufficient: cm.repeat_until_cash_sufficient,
    },
  };
}

function serializeRiskManagement(draft: StrategyDraft): SerializedRiskManagement | undefined {
  const rm = draft.risk_management;
  if (!rm.enabled) return undefined;
  const out: SerializedRiskManagement = {};
  const sd = num(rm.stop_trading_on_drawdown_pct);
  if (sd !== undefined) out.stop_trading_on_drawdown_pct = sd;
  const mpr = num(rm.max_position_ratio);
  if (mpr !== undefined) out.max_position_ratio = mpr;
  const mdl = num(rm.max_daily_loss_pct);
  if (mdl !== undefined) out.max_daily_loss_pct = mdl;
  if (Object.keys(out).length === 0) return undefined;
  return out;
}

function serializeExecution(draft: StrategyDraft): SerializedExecution | undefined {
  const ex = draft.execution;
  if (!ex.enabled) return undefined;
  const out: SerializedExecution = {
    entry_price: ex.entry_price,
    exit_price: ex.exit_price,
    use_adjusted_price: ex.use_adjusted_price,
    allow_buy_limit_up: ex.allow_buy_limit_up,
    allow_sell_limit_down: ex.allow_sell_limit_down,
    tick_rounding: ex.tick_rounding,
  };
  const fee = num(ex.fee_rate);
  if (fee !== undefined) out.fee_rate = fee;
  const sl = num(ex.slippage);
  if (sl !== undefined) out.slippage = sl;
  const gap = num(ex.max_gap_pct_for_entry);
  if (gap !== undefined) out.max_gap_pct_for_entry = gap;

  // tax_rate 시계열 또는 단일 (정확성 정책 13.6)
  if (ex.tax_rate_mode === "single") {
    const r = num(ex.tax_rate_single);
    if (r !== undefined) out.tax_rate = r;
  } else {
    const series: SerializedTaxRateBracket[] = [];
    for (const row of ex.tax_rate_timeseries) {
      const r = num(row.rate);
      const f = row.from?.trim();
      if (!f || r === undefined) continue;
      series.push({ from: f, rate: r });
    }
    if (series.length > 0) out.tax_rate = series;
  }
  return out;
}

function serializePriority(draft: StrategyDraft): SerializedPriority | undefined {
  const p = draft.priority;
  if (!p.enabled) return undefined;
  return { method: p.method, tie_breaker: p.tie_breaker };
}

function serializeMetadata(draft: StrategyDraft): SerializedMetadata | undefined {
  const m = draft.metadata;
  if (!m.enabled) return undefined;
  const out: SerializedMetadata = { schema_version: STRATEGY_SCHEMA_VERSION };
  const seed = num(m.random_seed);
  if (seed !== undefined) out.random_seed = seed;
  if (m.tags.length > 0) out.tags = [...m.tags];
  if (m.favorite) out.favorite = true;
  return out;
}

// --------------------------------------------------------------------------
// 최상위
// --------------------------------------------------------------------------

export function serializeDraft(draft: StrategyDraft): SerializedStrategy {
  const out: SerializedStrategy = { name: draft.name };

  // 4 조건 섹션
  for (const section of SECTIONS) {
    const ser = serializeSection(draft.sections[section]);
    if (ser) out[section] = ser;
  }

  // 6 비조건 섹션
  const ps = serializePositionSizing(draft);
  if (ps) out.position_sizing = ps;
  const cm = serializeCashManagement(draft);
  if (cm) out.cash_management = cm;
  const rm = serializeRiskManagement(draft);
  if (rm) out.risk_management = rm;
  const ex = serializeExecution(draft);
  if (ex) out.execution = ex;
  const pr = serializePriority(draft);
  if (pr) out.priority = pr;
  const md = serializeMetadata(draft);
  if (md) out.metadata = md;

  return out;
}
