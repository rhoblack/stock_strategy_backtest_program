/**
 * 전략 편집 임시 상태 타입.
 * 저장 시 02번 schema의 strategy_json 형식으로 직렬화 (별도 함수).
 *
 * 02번 schema 정합 (Wave 12-029):
 *   - 4 조건 섹션: entry / exit_signal / exit_position / filters
 *   - 6 비조건 섹션: position_sizing / cash_management / risk_management /
 *                    execution / priority / metadata
 *   - GROUP logic은 1단계 중첩만 지원 (02번 §4)
 */

import type { ConditionMeta, AllowedSection } from "../../../types/condition";
import {
  type CashManagementState,
  type ExecutionState,
  type MetadataState,
  type PositionSizingState,
  type PriorityState,
  type RiskManagementState,
  defaultCashManagement,
  defaultExecution,
  defaultMetadata,
  defaultPositionSizing,
  defaultPriority,
  defaultRiskManagement,
} from "./strategySections";

export type Section = AllowedSection; // entry | exit_signal | exit_position | filters

export const SECTIONS: Section[] = ["entry", "exit_signal", "exit_position", "filters"];

export const SECTION_LABEL: Record<Section, string> = {
  entry: "매수 조건",
  exit_signal: "매도 시계열 조건",
  exit_position: "매도 포지션 조건",
  filters: "필터",
};

export type Logic = "AND" | "OR" | "GROUP";

export type ConditionInstance = {
  /** 클라이언트 측 임시 ID — 저장 시에는 직렬화에서 제거. */
  instance_id: string;
  type: string;
  /** parameter name → value */
  values: Record<string, string | number | boolean>;
  meta: ConditionMeta;
};

/**
 * GROUP logic의 1단계 그룹 (02번 §4 — `(A AND B) OR (C AND D)`).
 * GROUP 안에는 AND/OR만 허용 — 그룹 안에 그룹 금지.
 */
export type GroupNode = {
  /** 클라이언트 측 임시 ID */
  group_id: string;
  /** AND or OR (GROUP은 여기 들어올 수 없음 — 1단계 정책) */
  logic: "AND" | "OR";
  conditions: ConditionInstance[];
};

export type GroupOperator = "AND" | "OR";

export type SectionState = {
  /** AND/OR/GROUP. GROUP일 때는 conditions 대신 groups 사용. */
  logic: Logic;
  conditions: ConditionInstance[];
  /** GROUP 모드 전용 — 그룹들끼리의 결합 연산자 (AND/OR만) */
  group_operator: GroupOperator;
  /** GROUP 모드 전용 — 1단계 그룹 배열 */
  groups: GroupNode[];
};

export type StrategyDraft = {
  name: string;
  sections: Record<Section, SectionState>;
  /** 마지막으로 클릭한 조건 (편집 패널에서 사용) */
  selected: { section: Section; instance_id: string } | null;
  /** 02번 6 비조건 섹션 (Wave 12-029) */
  position_sizing: PositionSizingState;
  cash_management: CashManagementState;
  risk_management: RiskManagementState;
  execution: ExecutionState;
  priority: PriorityState;
  metadata: MetadataState;
};

export function emptyDraft(name = ""): StrategyDraft {
  const empty = (logic: Logic = "AND"): SectionState => ({
    logic,
    conditions: [],
    group_operator: "OR",
    groups: [],
  });
  return {
    name,
    sections: {
      entry: empty("AND"),
      exit_signal: empty("AND"),
      exit_position: empty("OR"), // 매도는 보통 OR
      filters: empty("AND"),
    },
    selected: null,
    position_sizing: defaultPositionSizing(),
    cash_management: defaultCashManagement(),
    risk_management: defaultRiskManagement(),
    execution: defaultExecution(),
    priority: defaultPriority(),
    metadata: defaultMetadata(),
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
