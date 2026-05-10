import type { ConditionMeta } from "../../../types/condition";
import {
  type GroupOperator,
  type Logic,
  type Section,
  type SectionState,
  type StrategyDraft,
  emptyDraft,
  initialValuesFromMeta,
} from "./types";
import {
  type CashManagementState,
  type ExecutionState,
  type MetadataState,
  type PositionSizingState,
  type PriorityState,
  type RiskManagementState,
  type TaxRateBracket,
} from "./strategySections";

export type DraftAction =
  // 4 조건 섹션
  | { type: "SET_NAME"; name: string }
  | { type: "ADD_CONDITION"; section: Section; meta: ConditionMeta; group_id?: string }
  | { type: "REMOVE_CONDITION"; section: Section; instance_id: string; group_id?: string }
  | {
      type: "UPDATE_VALUE";
      section: Section;
      instance_id: string;
      name: string;
      value: string | number | boolean;
      group_id?: string;
    }
  | { type: "SET_LOGIC"; section: Section; logic: Logic }
  | { type: "SET_GROUP_OPERATOR"; section: Section; operator: GroupOperator }
  | { type: "ADD_GROUP"; section: Section; logic?: "AND" | "OR" }
  | { type: "REMOVE_GROUP"; section: Section; group_id: string }
  | { type: "SET_GROUP_LOGIC"; section: Section; group_id: string; logic: "AND" | "OR" }
  | { type: "SELECT"; section: Section; instance_id: string }
  | { type: "CLEAR_SELECTION" }
  | { type: "RESET"; name?: string }
  // 6 비조건 섹션 (Wave 12-029)
  | { type: "POSITION_SIZING_SET"; patch: Partial<PositionSizingState> }
  | { type: "CASH_MGMT_SET"; patch: Partial<CashManagementState> }
  | { type: "RISK_MGMT_SET"; patch: Partial<RiskManagementState> }
  | { type: "EXECUTION_SET"; patch: Partial<ExecutionState> }
  | { type: "EXECUTION_TAX_ADD" }
  | { type: "EXECUTION_TAX_REMOVE"; index: number }
  | { type: "EXECUTION_TAX_UPDATE"; index: number; patch: Partial<TaxRateBracket> }
  | { type: "PRIORITY_SET"; patch: Partial<PriorityState> }
  | { type: "METADATA_SET"; patch: Partial<MetadataState> }
  | { type: "METADATA_ADD_TAG"; tag: string }
  | { type: "METADATA_REMOVE_TAG"; tag: string };

let _counter = 0;
function nextId(prefix = "c"): string {
  _counter += 1;
  return `${prefix}${_counter}_${Date.now()}`;
}

function setSection(
  state: StrategyDraft,
  section: Section,
  patch: Partial<SectionState>,
): StrategyDraft {
  return {
    ...state,
    sections: {
      ...state.sections,
      [section]: { ...state.sections[section], ...patch },
    },
  };
}

/**
 * AND/OR 모드: section.conditions 직접 수정.
 * GROUP 모드: section.groups[group_id].conditions 수정.
 */
function mapConditions(
  sec: SectionState,
  group_id: string | undefined,
  fn: (conds: SectionState["conditions"]) => SectionState["conditions"],
): SectionState {
  if (group_id === undefined) {
    return { ...sec, conditions: fn(sec.conditions) };
  }
  return {
    ...sec,
    groups: sec.groups.map((g) =>
      g.group_id === group_id ? { ...g, conditions: fn(g.conditions) } : g,
    ),
  };
}

export function draftReducer(state: StrategyDraft, action: DraftAction): StrategyDraft {
  switch (action.type) {
    case "SET_NAME":
      return { ...state, name: action.name };

    case "ADD_CONDITION": {
      const sec = state.sections[action.section];
      const newInstance = {
        instance_id: nextId(),
        type: action.meta.type,
        values: initialValuesFromMeta(action.meta),
        meta: action.meta,
      };
      const next = mapConditions(sec, action.group_id, (cs) => [...cs, newInstance]);
      return {
        ...state,
        sections: { ...state.sections, [action.section]: next },
        selected: { section: action.section, instance_id: newInstance.instance_id },
      };
    }

    case "REMOVE_CONDITION": {
      const sec = state.sections[action.section];
      const next = mapConditions(sec, action.group_id, (cs) =>
        cs.filter((c) => c.instance_id !== action.instance_id),
      );
      const stillSelected =
        state.selected &&
        state.selected.section === action.section &&
        state.selected.instance_id === action.instance_id;
      return {
        ...state,
        sections: { ...state.sections, [action.section]: next },
        selected: stillSelected ? null : state.selected,
      };
    }

    case "UPDATE_VALUE": {
      const sec = state.sections[action.section];
      const next = mapConditions(sec, action.group_id, (cs) =>
        cs.map((c) =>
          c.instance_id === action.instance_id
            ? { ...c, values: { ...c.values, [action.name]: action.value } }
            : c,
        ),
      );
      return { ...state, sections: { ...state.sections, [action.section]: next } };
    }

    case "SET_LOGIC":
      return setSection(state, action.section, { logic: action.logic });

    case "SET_GROUP_OPERATOR":
      return setSection(state, action.section, { group_operator: action.operator });

    case "ADD_GROUP": {
      const sec = state.sections[action.section];
      const newGroup = {
        group_id: nextId("g"),
        logic: action.logic ?? ("AND" as const),
        conditions: [],
      };
      return setSection(state, action.section, { groups: [...sec.groups, newGroup] });
    }

    case "REMOVE_GROUP": {
      const sec = state.sections[action.section];
      return setSection(state, action.section, {
        groups: sec.groups.filter((g) => g.group_id !== action.group_id),
      });
    }

    case "SET_GROUP_LOGIC": {
      const sec = state.sections[action.section];
      return setSection(state, action.section, {
        groups: sec.groups.map((g) =>
          g.group_id === action.group_id ? { ...g, logic: action.logic } : g,
        ),
      });
    }

    case "SELECT":
      return { ...state, selected: { section: action.section, instance_id: action.instance_id } };

    case "CLEAR_SELECTION":
      return { ...state, selected: null };

    case "RESET":
      return emptyDraft(action.name);

    // ---------------------------------------------------------------- 6 비조건 섹션

    case "POSITION_SIZING_SET":
      return { ...state, position_sizing: { ...state.position_sizing, ...action.patch } };

    case "CASH_MGMT_SET":
      return { ...state, cash_management: { ...state.cash_management, ...action.patch } };

    case "RISK_MGMT_SET":
      return { ...state, risk_management: { ...state.risk_management, ...action.patch } };

    case "EXECUTION_SET":
      return { ...state, execution: { ...state.execution, ...action.patch } };

    case "EXECUTION_TAX_ADD":
      return {
        ...state,
        execution: {
          ...state.execution,
          tax_rate_timeseries: [
            ...state.execution.tax_rate_timeseries,
            { from: "", rate: "" },
          ],
        },
      };

    case "EXECUTION_TAX_REMOVE":
      return {
        ...state,
        execution: {
          ...state.execution,
          tax_rate_timeseries: state.execution.tax_rate_timeseries.filter(
            (_, i) => i !== action.index,
          ),
        },
      };

    case "EXECUTION_TAX_UPDATE":
      return {
        ...state,
        execution: {
          ...state.execution,
          tax_rate_timeseries: state.execution.tax_rate_timeseries.map((row, i) =>
            i === action.index ? { ...row, ...action.patch } : row,
          ),
        },
      };

    case "PRIORITY_SET":
      return { ...state, priority: { ...state.priority, ...action.patch } };

    case "METADATA_SET":
      return { ...state, metadata: { ...state.metadata, ...action.patch } };

    case "METADATA_ADD_TAG": {
      const t = action.tag.trim();
      if (!t || state.metadata.tags.includes(t)) return state;
      return { ...state, metadata: { ...state.metadata, tags: [...state.metadata.tags, t] } };
    }

    case "METADATA_REMOVE_TAG":
      return {
        ...state,
        metadata: {
          ...state.metadata,
          tags: state.metadata.tags.filter((t) => t !== action.tag),
        },
      };

    default:
      return state;
  }
}

/** 테스트에서 결정론을 위해 카운터 리셋. */
export function _resetIdCounterForTests() {
  _counter = 0;
}
