/**
 * 조건 메타데이터 (백엔드 GET /api/conditions 응답 형식).
 * 백엔드 condition_definitions.py의 ALL_DEFINITIONS와 일치.
 */

export type ConditionParameterOption = {
  label: string;
  value: string | number;
};

export type ConditionParameter = {
  name: string;
  label: string;
  input_type: "number" | "select" | "text";
  default: string | number | boolean;
  min?: number;
  max?: number;
  options?: ConditionParameterOption[];
};

export type AllowedSection =
  | "entry"
  | "exit_signal"
  | "exit_position"
  | "filters";

export type ConditionMeta = {
  type: string;
  category: string;
  requires_position: boolean;
  name: string;
  description: string;
  sentence_template: string;
  parameters: ConditionParameter[];
  allowed_in: AllowedSection[];
};
