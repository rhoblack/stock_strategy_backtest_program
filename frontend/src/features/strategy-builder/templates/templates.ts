/**
 * 전략 템플릿 카탈로그 (Wave 12-030, 01-k).
 *
 * 정책:
 *   - 템플릿은 fixed shape (랜덤성 없음 — 결정론).
 *   - 조건은 type + values만 명세 (ConditionMeta는 백엔드 카탈로그에서 lookup).
 *     → buildDraftFromTemplate(template, metaCatalog)로 완전한 StrategyDraft 생성.
 *   - 6 비조건 섹션은 템플릿 별로 합리적인 default를 명시 (enabled 여부 포함).
 *   - random_seed는 사용자가 명시 입력 — 템플릿은 빈 문자열 default 유지.
 */
import type { StrategyDraft, GroupOperator, Logic } from "../state/types";
import type { ConditionMeta } from "../../../types/condition";
import {
  defaultCashManagement,
  defaultExecution,
  defaultMetadata,
  defaultPositionSizing,
  defaultPriority,
  defaultRiskManagement,
  type PositionSizingState,
  type CashManagementState,
  type RiskManagementState,
  type ExecutionState,
  type PriorityState,
  type MetadataState,
} from "../state/strategySections";
import { emptyDraft } from "../state/types";

// --------------------------------------------------------------------------
// Template type
// --------------------------------------------------------------------------

export type TemplateConditionSpec = {
  /** 백엔드 ConditionMeta.type와 일치해야 함 */
  type: string;
  /** parameter name → value. 누락 시 ConditionMeta default로 채움 */
  values?: Record<string, string | number | boolean>;
};

export type TemplateSectionSpec = {
  logic?: Logic; // default "AND"
  conditions?: TemplateConditionSpec[];
  group_operator?: GroupOperator;
  groups?: { logic: "AND" | "OR"; conditions: TemplateConditionSpec[] }[];
};

export type StrategyTemplate = {
  id: string;
  name: string;
  /** 짧은 한 줄 설명 */
  description: string;
  /** 추천 카테고리 (UI 그룹화용) */
  category: "기본" | "추세" | "역추세" | "모멘텀";

  /** 4 조건 섹션 */
  entry?: TemplateSectionSpec;
  exit_signal?: TemplateSectionSpec;
  exit_position?: TemplateSectionSpec;
  filters?: TemplateSectionSpec;

  /** 6 비조건 섹션 — 각각 부분 패치 (defaultXxx() 위에 덮어씀) */
  position_sizing?: Partial<PositionSizingState>;
  cash_management?: Partial<CashManagementState>;
  risk_management?: Partial<RiskManagementState>;
  execution?: Partial<ExecutionState>;
  priority?: Partial<PriorityState>;
  metadata?: Partial<MetadataState>;
};

// --------------------------------------------------------------------------
// 템플릿 정의 (4종)
// --------------------------------------------------------------------------

const EMPTY_TEMPLATE: StrategyTemplate = {
  id: "empty",
  name: "빈 전략",
  description: "처음부터 직접 조립합니다. 자금/실행 섹션은 비활성화 상태로 시작.",
  category: "기본",
};

const GOLDEN_CROSS_TEMPLATE: StrategyTemplate = {
  id: "golden_cross",
  name: "골든 크로스 (5/20 MA)",
  description: "5일 이동평균이 20일 이동평균을 상향 돌파할 때 매수, 익절/손절 7%/-5%.",
  category: "추세",
  entry: {
    logic: "AND",
    conditions: [
      {
        type: "price_vs_ma",
        values: { price_field: "adj_close", ma_period: 20, operator: ">" },
      },
    ],
  },
  exit_position: {
    logic: "OR",
    conditions: [
      { type: "take_profit", values: { percent: 7.0 } },
      { type: "stop_loss", values: { percent: 5.0 } },
    ],
  },
  position_sizing: {
    enabled: true,
    method: "fixed_amount",
    amount: 1_000_000,
    max_positions: 10,
  },
  execution: {
    enabled: true,
    entry_price: "next_open",
    exit_price: "next_open",
  },
  priority: {
    enabled: true,
    method: "trading_value_desc",
    tie_breaker: "symbol_asc",
  },
};

const RSI_OVERSOLD_TEMPLATE: StrategyTemplate = {
  id: "rsi_oversold",
  name: "RSI 과매도 진입",
  description: "RSI(14)가 30 이하로 떨어진 다음날 매수, 50 이상 도달 시 매도 + 손절 -7%.",
  category: "역추세",
  entry: {
    logic: "AND",
    conditions: [
      { type: "rsi", values: { period: 14, operator: "<", threshold: 30 } },
    ],
  },
  exit_signal: {
    logic: "OR",
    conditions: [
      { type: "rsi", values: { period: 14, operator: ">", threshold: 50 } },
    ],
  },
  exit_position: {
    logic: "OR",
    conditions: [{ type: "stop_loss", values: { percent: 7.0 } }],
  },
  position_sizing: {
    enabled: true,
    method: "fixed_amount",
    amount: 1_000_000,
    max_positions: 5,
  },
  execution: {
    enabled: true,
    entry_price: "next_open",
    exit_price: "next_open",
  },
};

const MOMENTUM_TEMPLATE: StrategyTemplate = {
  id: "momentum_breakout",
  name: "단기 신고가 + 거래량 모멘텀",
  description: "20일 신고가 돌파 + 거래량이 20일 평균의 2배 이상일 때 매수, 익절 10% / 손절 -5%.",
  category: "모멘텀",
  entry: {
    logic: "AND",
    conditions: [
      { type: "new_high", values: { period: 20 } },
      { type: "volume_ratio", values: { period: 20, operator: ">", threshold: 2.0 } },
    ],
  },
  exit_position: {
    logic: "OR",
    conditions: [
      { type: "take_profit", values: { percent: 10.0 } },
      { type: "stop_loss", values: { percent: 5.0 } },
    ],
  },
  filters: {
    logic: "AND",
    conditions: [
      // 거래대금 1억 이상 (유동성 필터). type/parameter는 백엔드 카탈로그에 있어야 적용됨
      { type: "trading_value", values: { period: 20, operator: ">", threshold: 100_000_000 } },
    ],
  },
  position_sizing: {
    enabled: true,
    method: "fixed_amount",
    amount: 1_000_000,
    max_positions: 8,
  },
  execution: {
    enabled: true,
    entry_price: "next_open",
    exit_price: "next_open",
  },
  priority: {
    enabled: true,
    method: "volume_ratio_desc",
    tie_breaker: "symbol_asc",
  },
};

export const STRATEGY_TEMPLATES: StrategyTemplate[] = [
  EMPTY_TEMPLATE,
  GOLDEN_CROSS_TEMPLATE,
  RSI_OVERSOLD_TEMPLATE,
  MOMENTUM_TEMPLATE,
];

export function getTemplateById(id: string): StrategyTemplate | undefined {
  return STRATEGY_TEMPLATES.find((t) => t.id === id);
}

// --------------------------------------------------------------------------
// 템플릿 → StrategyDraft 변환
// --------------------------------------------------------------------------

/**
 * 템플릿의 조건 type을 백엔드 ConditionMeta 카탈로그에서 lookup하여
 * 완전한 ConditionInstance를 만들어냄. 카탈로그에 없는 type은 조용히 스킵.
 *
 * @param template 적용할 템플릿
 * @param metaCatalog 백엔드 GET /api/conditions 결과 (없으면 빈 배열)
 * @param name 새 전략 이름 (기본: 템플릿 이름)
 */
export function buildDraftFromTemplate(
  template: StrategyTemplate,
  metaCatalog: ConditionMeta[],
  name?: string,
): StrategyDraft {
  const metaByType = new Map<string, ConditionMeta>();
  for (const m of metaCatalog) metaByType.set(m.type, m);

  const baseName = name ?? (template.id === "empty" ? "" : template.name);
  const draft = emptyDraft(baseName);

  // 4 조건 섹션 적용
  applyTemplateSection(draft, "entry", template.entry, metaByType);
  applyTemplateSection(draft, "exit_signal", template.exit_signal, metaByType);
  applyTemplateSection(draft, "exit_position", template.exit_position, metaByType);
  applyTemplateSection(draft, "filters", template.filters, metaByType);

  // 6 비조건 섹션 patch
  if (template.position_sizing) {
    draft.position_sizing = { ...defaultPositionSizing(), ...template.position_sizing };
  }
  if (template.cash_management) {
    draft.cash_management = { ...defaultCashManagement(), ...template.cash_management };
  }
  if (template.risk_management) {
    draft.risk_management = { ...defaultRiskManagement(), ...template.risk_management };
  }
  if (template.execution) {
    draft.execution = { ...defaultExecution(), ...template.execution };
  }
  if (template.priority) {
    draft.priority = { ...defaultPriority(), ...template.priority };
  }
  if (template.metadata) {
    draft.metadata = { ...defaultMetadata(), ...template.metadata };
  }

  return draft;
}

let _idCounter = 0;
function templateInstanceId(): string {
  _idCounter += 1;
  return `tpl${_idCounter}_${Date.now()}`;
}

function applyTemplateSection(
  draft: StrategyDraft,
  section: keyof StrategyDraft["sections"],
  spec: TemplateSectionSpec | undefined,
  metaByType: Map<string, ConditionMeta>,
): void {
  if (!spec) return;

  const sec = draft.sections[section];

  // logic 적용 (default "AND" 유지)
  if (spec.logic) {
    sec.logic = spec.logic;
  }

  // group_operator 적용
  if (spec.group_operator) {
    sec.group_operator = spec.group_operator;
  }

  // GROUP 모드: groups 적용
  if (spec.groups && spec.groups.length > 0) {
    sec.groups = spec.groups.map((g) => ({
      group_id: templateInstanceId(),
      logic: g.logic,
      conditions: g.conditions
        .map((c) => buildInstance(c, metaByType))
        .filter((x): x is NonNullable<typeof x> => x !== null),
    }));
  }

  // AND/OR 모드: conditions 적용
  if (spec.conditions && spec.conditions.length > 0) {
    sec.conditions = spec.conditions
      .map((c) => buildInstance(c, metaByType))
      .filter((x): x is NonNullable<typeof x> => x !== null);
  }
}

function buildInstance(
  c: TemplateConditionSpec,
  metaByType: Map<string, ConditionMeta>,
): { instance_id: string; type: string; values: Record<string, string | number | boolean>; meta: ConditionMeta } | null {
  const meta = metaByType.get(c.type);
  if (!meta) {
    // 카탈로그에 없는 condition type은 스킵 (백엔드 미배포 등)
    return null;
  }
  // 메타 default + 템플릿 override
  const values: Record<string, string | number | boolean> = {};
  for (const p of meta.parameters) values[p.name] = p.default;
  if (c.values) Object.assign(values, c.values);
  return {
    instance_id: templateInstanceId(),
    type: c.type,
    values,
    meta,
  };
}

/** 테스트에서 결정론을 위해 카운터 리셋. */
export function _resetTemplateIdCounterForTests() {
  _idCounter = 0;
}
