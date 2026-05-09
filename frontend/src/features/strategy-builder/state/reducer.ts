import type { ConditionMeta } from "../../../types/condition";
import {
  type Logic,
  type Section,
  type StrategyDraft,
  emptyDraft,
  initialValuesFromMeta,
} from "./types";

export type DraftAction =
  | { type: "SET_NAME"; name: string }
  | { type: "ADD_CONDITION"; section: Section; meta: ConditionMeta }
  | { type: "REMOVE_CONDITION"; section: Section; instance_id: string }
  | {
      type: "UPDATE_VALUE";
      section: Section;
      instance_id: string;
      name: string;
      value: string | number | boolean;
    }
  | { type: "SET_LOGIC"; section: Section; logic: Logic }
  | { type: "SELECT"; section: Section; instance_id: string }
  | { type: "CLEAR_SELECTION" }
  | { type: "RESET"; name?: string };

let _counter = 0;
function nextId(): string {
  _counter += 1;
  return `c${_counter}_${Date.now()}`;
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
      return {
        ...state,
        sections: {
          ...state.sections,
          [action.section]: {
            ...sec,
            conditions: [...sec.conditions, newInstance],
          },
        },
        selected: { section: action.section, instance_id: newInstance.instance_id },
      };
    }

    case "REMOVE_CONDITION": {
      const sec = state.sections[action.section];
      const next = sec.conditions.filter((c) => c.instance_id !== action.instance_id);
      const stillSelected =
        state.selected &&
        state.selected.section === action.section &&
        state.selected.instance_id === action.instance_id;
      return {
        ...state,
        sections: {
          ...state.sections,
          [action.section]: { ...sec, conditions: next },
        },
        selected: stillSelected ? null : state.selected,
      };
    }

    case "UPDATE_VALUE": {
      const sec = state.sections[action.section];
      return {
        ...state,
        sections: {
          ...state.sections,
          [action.section]: {
            ...sec,
            conditions: sec.conditions.map((c) =>
              c.instance_id === action.instance_id
                ? { ...c, values: { ...c.values, [action.name]: action.value } }
                : c,
            ),
          },
        },
      };
    }

    case "SET_LOGIC":
      return {
        ...state,
        sections: {
          ...state.sections,
          [action.section]: { ...state.sections[action.section], logic: action.logic },
        },
      };

    case "SELECT":
      return { ...state, selected: { section: action.section, instance_id: action.instance_id } };

    case "CLEAR_SELECTION":
      return { ...state, selected: null };

    case "RESET":
      return emptyDraft(action.name);

    default:
      return state;
  }
}

/** 테스트에서 결정론을 위해 카운터 리셋. */
export function _resetIdCounterForTests() {
  _counter = 0;
}
