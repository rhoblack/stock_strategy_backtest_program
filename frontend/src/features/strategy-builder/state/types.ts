/**
 * 전략 편집 임시 상태 타입.
 * 저장 시 02번 schema의 strategy_json 형식으로 직렬화 (별도 함수).
 */

import type { ConditionMeta, AllowedSection } from "../../../types/condition";

export type Section = AllowedSection; // entry | exit_signal | exit_position | filters

export const SECTIONS: Section[] = ["entry", "exit_signal", "exit_position", "filters"];

export const SECTION_LABEL: Record<Section, string> = {
  entry: "매수 조건",
  exit_signal: "매도 시계열 조건",
  exit_position: "매도 포지션 조건",
  filters: "필터",
};

export type Logic = "AND" | "OR";

export type ConditionInstance = {
  /** 클라이언트 측 임시 ID — 저장 시에는 직렬화에서 제거. */
  instance_id: string;
  type: string;
  /** parameter name → value */
  values: Record<string, string | number | boolean>;
  meta: ConditionMeta;
};

export type SectionState = {
  logic: Logic;
  conditions: ConditionInstance[];
};

export type StrategyDraft = {
  name: string;
  sections: Record<Section, SectionState>;
  /** 마지막으로 클릭한 조건 (편집 패널에서 사용) */
  selected: { section: Section; instance_id: string } | null;
};

export function emptyDraft(name = ""): StrategyDraft {
  const empty: SectionState = { logic: "AND", conditions: [] };
  return {
    name,
    sections: {
      entry: { ...empty },
      exit_signal: { ...empty },
      exit_position: { logic: "OR", conditions: [] }, // 매도는 보통 OR
      filters: { ...empty },
    },
    selected: null,
  };
}

/** parameter default 값을 모아 초기 values 채움. */
export function initialValuesFromMeta(meta: ConditionMeta): Record<string, string | number | boolean> {
  const obj: Record<string, string | number | boolean> = {};
  for (const p of meta.parameters) {
    obj[p.name] = p.default;
  }
  return obj;
}
