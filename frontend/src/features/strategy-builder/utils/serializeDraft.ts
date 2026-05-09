/**
 * StrategyDraft → 백엔드 strategy_json 형식 (02번 schema).
 * instance_id / meta는 제거하고 type + values만 평탄화.
 */

import type { StrategyDraft, Section, ConditionInstance } from "../state/types";

const SECTIONS: Section[] = ["entry", "exit_signal", "exit_position", "filters"];

export type SerializedSection = {
  logic: "AND" | "OR";
  conditions: Array<{ type: string } & Record<string, unknown>>;
};

export type SerializedStrategy = {
  name: string;
  entry?: SerializedSection;
  exit_signal?: SerializedSection;
  exit_position?: SerializedSection;
  filters?: SerializedSection;
};

function serializeCondition(inst: ConditionInstance): { type: string } & Record<string, unknown> {
  return { type: inst.type, ...inst.values };
}

export function serializeDraft(draft: StrategyDraft): SerializedStrategy {
  const out: SerializedStrategy = { name: draft.name };
  for (const section of SECTIONS) {
    const sec = draft.sections[section];
    if (sec.conditions.length === 0) continue;
    out[section] = {
      logic: sec.logic,
      conditions: sec.conditions.map(serializeCondition),
    };
  }
  return out;
}
