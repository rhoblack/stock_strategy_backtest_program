import type { StrategyDraft } from "../state/types";

export type ValidationLevel = "error" | "warning";

export type ValidationItem = {
  level: ValidationLevel;
  code: string;
  message: string;
};

/**
 * 설계서 01번 10절의 오류/경고 규칙.
 */
export function validateDraft(draft: StrategyDraft): ValidationItem[] {
  const items: ValidationItem[] = [];

  // 매수 조건 없음 — 오류
  if (draft.sections.entry.conditions.length === 0) {
    items.push({
      level: "error",
      code: "ENTRY_REQUIRED",
      message: "매수 조건이 없습니다.",
    });
  }

  // 매도 조건 (시계열 + 포지션) 모두 없음 — 경고
  const hasExitSignal = draft.sections.exit_signal.conditions.length > 0;
  const hasExitPosition = draft.sections.exit_position.conditions.length > 0;
  if (!hasExitSignal && !hasExitPosition) {
    items.push({
      level: "warning",
      code: "EXIT_MISSING",
      message: "매도 조건이 없습니다. 무한 보유 위험이 있습니다.",
    });
  }

  // 포지션 매도가 있는데 stop_loss 없음 — 경고
  if (hasExitPosition) {
    const hasStopLoss = draft.sections.exit_position.conditions.some(
      (c) => c.type === "stop_loss",
    );
    if (!hasStopLoss) {
      items.push({
        level: "warning",
        code: "NO_STOP_LOSS",
        message: "손절 조건이 없습니다.",
      });
    }
  }

  // 거래대금/유동성 필터 없음 — 경고
  const hasLiquidityFilter = draft.sections.filters.conditions.some(
    (c) => c.type === "avg_trading_value" || c.type === "volume_ratio",
  );
  if (!hasLiquidityFilter) {
    items.push({
      level: "warning",
      code: "NO_LIQUIDITY_FILTER",
      message: "거래대금 / 유동성 필터가 없습니다.",
    });
  }

  return items;
}

export function hasErrors(items: ValidationItem[]): boolean {
  return items.some((i) => i.level === "error");
}
