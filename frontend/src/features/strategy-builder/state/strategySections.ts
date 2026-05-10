/**
 * 02번 schema의 6 비조건 섹션 상태 정의.
 * (entry/exit_signal/exit_position/filters는 types.ts의 SectionState로 관리.)
 *
 * 절번 매핑:
 *   - PositionSizing: 02번 §8
 *   - CashManagement: 02번 §9
 *   - RiskManagement: 02번 §10
 *   - Execution     : 02번 §11 (+ 13.6 거래세 시계열, 13.7 수정주가)
 *   - Priority      : 02번 §7
 *   - Metadata      : 02번 §12, §17 (schema_version)
 *
 * "정책: 결정론" — random_seed 기본은 null (사용자 명시 입력),
 *               schema_version은 fixed "1.0".
 */

// --------------------------------------------------------------------------
// PositionSizing (02번 §8)
// --------------------------------------------------------------------------

export type PositionSizingMethod =
  | "fixed_amount"
  | "fixed_ratio"
  | "equal_weight"
  | "daily_budget";

export const POSITION_SIZING_METHODS: { value: PositionSizingMethod; label: string }[] = [
  { value: "fixed_amount", label: "종목당 고정 금액" },
  { value: "fixed_ratio", label: "총자산 대비 고정 비율" },
  { value: "equal_weight", label: "균등 비중" },
  { value: "daily_budget", label: "1일 매수 예산" },
];

export type PositionSizingState = {
  enabled: boolean;
  method: PositionSizingMethod;
  /** fixed_amount 시 종목당 고정 금액 */
  amount: number | "";
  /** fixed_ratio 시 (0, 1] */
  ratio: number | "";
  /** 보유 가능 종목 수 (>=1) */
  max_positions: number | "";
  /** 1일 신규 진입 종목 수 (>=0) */
  max_daily_entries: number | "";
  /** 1일 매수 예산 (>=0) */
  daily_buy_budget: number | "";
  /** 추가매수 허용 여부 */
  allow_pyramiding: boolean;
};

export function defaultPositionSizing(): PositionSizingState {
  return {
    enabled: false,
    method: "fixed_amount",
    amount: 1_000_000,
    ratio: "",
    max_positions: 10,
    max_daily_entries: 3,
    daily_buy_budget: 1_000_000,
    allow_pyramiding: false,
  };
}

// --------------------------------------------------------------------------
// CashManagement (02번 §9)
// --------------------------------------------------------------------------

export type CashShortageTriggerType =
  | "cash_below_daily_buy_budget"
  | "cash_below_threshold";

export type CashShortageActionType = "partial_sell";

export type CashTargetSelectionMethod =
  | "lowest_return"
  | "highest_return"
  | "largest_value"
  | "oldest_position"
  | "newest_position";

export const CASH_TRIGGER_TYPES: { value: CashShortageTriggerType; label: string }[] = [
  { value: "cash_below_daily_buy_budget", label: "예수금 < 당일 매수 예산" },
  { value: "cash_below_threshold", label: "예수금 < 절대 금액" },
];

export const CASH_TARGET_METHODS: { value: CashTargetSelectionMethod; label: string }[] = [
  { value: "lowest_return", label: "수익률 가장 낮은 종목부터" },
  { value: "highest_return", label: "수익률 가장 높은 종목부터" },
  { value: "largest_value", label: "보유 평가금액 가장 큰 종목부터" },
  { value: "oldest_position", label: "가장 오래 보유한 종목부터" },
  { value: "newest_position", label: "가장 최근 매수한 종목부터" },
];

export type CashManagementState = {
  enabled: boolean;
  trigger_type: CashShortageTriggerType;
  /** trigger_type=cash_below_threshold 시 사용 */
  trigger_threshold: number | "";
  action_type: CashShortageActionType;
  /** 한 번에 매도할 비율 (0, 1] */
  sell_fraction: number | "";
  target_method: CashTargetSelectionMethod;
  repeat_until_cash_sufficient: boolean;
};

export function defaultCashManagement(): CashManagementState {
  return {
    enabled: false,
    trigger_type: "cash_below_daily_buy_budget",
    trigger_threshold: "",
    action_type: "partial_sell",
    sell_fraction: 0.25,
    target_method: "lowest_return",
    repeat_until_cash_sufficient: true,
  };
}

// --------------------------------------------------------------------------
// RiskManagement (02번 §10)
// --------------------------------------------------------------------------

export type RiskManagementState = {
  enabled: boolean;
  /** 누적 MDD가 N% 초과 시 신규 매수 중단 (0~100) */
  stop_trading_on_drawdown_pct: number | "";
  /** 한 종목당 총자산 대비 최대 비율 (0, 1] */
  max_position_ratio: number | "";
  /** 하루 손실이 N% 초과 시 당일 매수 중단 */
  max_daily_loss_pct: number | "";
};

export function defaultRiskManagement(): RiskManagementState {
  return {
    enabled: false,
    stop_trading_on_drawdown_pct: 20,
    max_position_ratio: "",
    max_daily_loss_pct: "",
  };
}

// --------------------------------------------------------------------------
// Execution (02번 §11)
// --------------------------------------------------------------------------

export type ExecutionPriceField = "open" | "close" | "next_open" | "next_close";

export const EXECUTION_PRICE_FIELDS: { value: ExecutionPriceField; label: string }[] = [
  { value: "open", label: "당일 시가" },
  { value: "close", label: "당일 종가" },
  { value: "next_open", label: "다음날 시가 (권장)" },
  { value: "next_close", label: "다음날 종가" },
];

export type TickRoundingMode = "buy_up_sell_down" | "nearest";

export const TICK_ROUNDING_MODES: { value: TickRoundingMode; label: string }[] = [
  { value: "buy_up_sell_down", label: "매수 올림 / 매도 내림 (보수적)" },
  { value: "nearest", label: "반올림" },
];

/** 시계열 거래세 1행 — execution.tax_rate (정확성 정책 13.6) */
export type TaxRateBracket = {
  /** ISO 날짜 (YYYY-MM-DD) — 비어 있으면 직렬화에서 제외 */
  from: string;
  /** 세율 (0 이상). 빈 문자열은 직렬화에서 제외 */
  rate: number | "";
};

export type ExecutionState = {
  enabled: boolean;
  entry_price: ExecutionPriceField;
  exit_price: ExecutionPriceField;
  /** 수수료율 (0 이상) */
  fee_rate: number | "";
  /** 슬리피지 (0 이상) */
  slippage: number | "";
  /** true=시계열 배열, false=단일 float */
  tax_rate_mode: "single" | "timeseries";
  /** tax_rate_mode=single 시 사용 */
  tax_rate_single: number | "";
  /** tax_rate_mode=timeseries 시 사용 (정확성 정책 13.6.2) */
  tax_rate_timeseries: TaxRateBracket[];
  use_adjusted_price: boolean;
  /** 진입 시 갭 한도 % */
  max_gap_pct_for_entry: number | "";
  allow_buy_limit_up: boolean;
  allow_sell_limit_down: boolean;
  tick_rounding: TickRoundingMode;
};

export function defaultExecution(): ExecutionState {
  return {
    enabled: false,
    entry_price: "next_open",
    exit_price: "next_open",
    fee_rate: 0.00015,
    slippage: 0.001,
    // 한국 거래세 시계열 기본값 (정확성 정책 13.6 — 2020~2025 변동)
    tax_rate_mode: "timeseries",
    tax_rate_single: 0.0015,
    tax_rate_timeseries: [
      { from: "2020-01-01", rate: 0.0023 },
      { from: "2023-01-01", rate: 0.0020 },
      { from: "2024-01-01", rate: 0.0018 },
      { from: "2025-01-01", rate: 0.0015 },
    ],
    use_adjusted_price: true,
    max_gap_pct_for_entry: 5.0,
    allow_buy_limit_up: false,
    allow_sell_limit_down: false,
    tick_rounding: "buy_up_sell_down",
  };
}

// --------------------------------------------------------------------------
// Priority (02번 §7)
// --------------------------------------------------------------------------

export type PriorityMethod =
  | "trading_value_desc"
  | "market_cap_desc"
  | "market_cap_asc"
  | "volume_ratio_desc"
  | "price_change_desc"
  | "random";

export const PRIORITY_METHODS: { value: PriorityMethod; label: string }[] = [
  { value: "trading_value_desc", label: "20일 평균 거래대금 큰 순 (기본)" },
  { value: "market_cap_desc", label: "시가총액 큰 순" },
  { value: "market_cap_asc", label: "시가총액 작은 순" },
  { value: "volume_ratio_desc", label: "거래량 급증 비율 큰 순" },
  { value: "price_change_desc", label: "당일 등락률 큰 순" },
  { value: "random", label: "무작위 (random_seed 필요)" },
];

export type TieBreaker = "symbol_asc" | "symbol_desc";

export const TIE_BREAKERS: { value: TieBreaker; label: string }[] = [
  { value: "symbol_asc", label: "종목코드 오름차순 (기본)" },
  { value: "symbol_desc", label: "종목코드 내림차순" },
];

export type PriorityState = {
  enabled: boolean;
  method: PriorityMethod;
  tie_breaker: TieBreaker;
};

export function defaultPriority(): PriorityState {
  return {
    enabled: false,
    method: "trading_value_desc",
    tie_breaker: "symbol_asc",
  };
}

// --------------------------------------------------------------------------
// Metadata (02번 §12, §17)
// --------------------------------------------------------------------------

/** schema_version은 코드에 fixed value로 박음 (02번 §17). 변경은 마이그레이션 문서. */
export const STRATEGY_SCHEMA_VERSION = "1.0";

export type MetadataState = {
  enabled: boolean;
  /** 사용자 입력 결정론 시드. null이면 직렬화에서 제외 — 자동 생성 금지 (정책) */
  random_seed: number | "";
  tags: string[];
  favorite: boolean;
};

export function defaultMetadata(): MetadataState {
  return {
    enabled: false,
    random_seed: "",
    tags: [],
    favorite: false,
  };
}

// --------------------------------------------------------------------------
// 섹션 식별자 + 라벨 (StrategyConfigPanel 탭 표시용)
// --------------------------------------------------------------------------

export type ConfigSectionKey =
  | "position_sizing"
  | "cash_management"
  | "risk_management"
  | "execution"
  | "priority"
  | "metadata";

export const CONFIG_SECTIONS: ConfigSectionKey[] = [
  "position_sizing",
  "cash_management",
  "risk_management",
  "execution",
  "priority",
  "metadata",
];

export const CONFIG_SECTION_LABEL: Record<ConfigSectionKey, string> = {
  position_sizing: "자금 배분",
  cash_management: "예수금 관리",
  risk_management: "리스크 관리",
  execution: "체결/비용",
  priority: "동시 신호 우선순위",
  metadata: "메타데이터",
};
