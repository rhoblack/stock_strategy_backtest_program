/**
 * 백테스트 API hooks.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type BacktestRunOut = {
  id: number;
  user_id: number;
  strategy_id: number;
  run_name: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress_pct: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type BacktestListItem = {
  id: number;
  strategy_id: number;
  run_name: string;
  status: BacktestRunOut["status"];
  progress_pct: number;
  start_date: string | null;
  end_date: string | null;
  initial_cash: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
};

export type BacktestListResponse = {
  items: BacktestListItem[];
  total_count: number;
  total_pages: number;
  page: number;
  page_size: number;
};

export type BacktestSummaryOut = {
  run_id: number;
  status: BacktestRunOut["status"];
  progress_pct: number;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  summary: {
    initial_cash: number;
    final_equity: number;
    total_return_pct: number;
    annual_return_pct: number;
    mdd_pct: number;
    trade_count: number;
    open_position_count: number;
    win_rate: number;
    avg_holding_days: number;
    avg_profit_pct: number;
    avg_loss_pct: number;
    profit_factor: number | null;
  } | null;
};

export type BacktestCreatePayload = {
  strategy_id: number;
  run_name?: string;
  universe_config?: Record<string, unknown>;
  start_date: string;
  end_date: string;
  initial_cash: number;
  fee_rate: number;
  tax_rate: number;
  slippage: number;
  tick_rounding?: string;
};

export type TradeGroupOut = {
  trade_group_id: number;
  symbol: string;
  name: string;
  entry_date: string;
  entry_price: number;
  entry_quantity: number;
  remaining_quantity: number;
  fully_closed_at: string | null;
  final_profit: number | null;
  final_profit_rate: number | null;
  executions: Array<{
    execution_date: string;
    execution_type: "BUY" | "SELL" | "PARTIAL_SELL";
    price: number;
    quantity: number;
    realized_profit: number | null;
    exit_reason: string | null;
  }>;
};

export type DailyEquityOut = {
  date: string;
  cash: number;
  stock_value: number;
  total_equity: number;
  drawdown: number;
  positions_count: number;
};

// === API ===

export async function createBacktest(
  payload: BacktestCreatePayload,
): Promise<BacktestRunOut> {
  return (await api.post<BacktestRunOut>("/api/backtests", payload)).data;
}

export async function fetchBacktestStatus(runId: number): Promise<BacktestRunOut> {
  return (await api.get<BacktestRunOut>(`/api/backtests/${runId}/status`)).data;
}

export async function fetchBacktestSummary(runId: number): Promise<BacktestSummaryOut> {
  return (await api.get<BacktestSummaryOut>(`/api/backtests/${runId}/summary`)).data;
}

export async function fetchBacktestTrades(
  runId: number,
): Promise<{ items: TradeGroupOut[]; total_count: number }> {
  return (
    await api.get<{ items: TradeGroupOut[]; total_count: number }>(
      `/api/backtests/${runId}/trades`,
    )
  ).data;
}

export async function fetchDailyEquity(
  runId: number,
): Promise<{ items: DailyEquityOut[]; total_count: number }> {
  return (
    await api.get<{ items: DailyEquityOut[]; total_count: number }>(
      `/api/backtests/${runId}/daily-equity`,
    )
  ).data;
}

export async function fetchBacktestList(params?: {
  strategy_id?: number;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<BacktestListResponse> {
  return (
    await api.get<BacktestListResponse>("/api/backtests", { params })
  ).data;
}

// === Hooks ===

export function useCreateBacktest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createBacktest,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtests"] }),
  });
}

export function useBacktestStatus(runId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["backtest-status", runId],
    queryFn: () => fetchBacktestStatus(runId!),
    enabled: enabled && runId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 2_000;
      return data.status === "running" || data.status === "pending" ? 2_000 : false;
    },
  });
}

export function useBacktestSummary(runId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["backtest-summary", runId],
    queryFn: () => fetchBacktestSummary(runId!),
    enabled: enabled && runId !== null,
  });
}

export function useBacktestTrades(runId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["backtest-trades", runId],
    queryFn: () => fetchBacktestTrades(runId!),
    enabled: enabled && runId !== null,
  });
}

export function useDailyEquity(runId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["backtest-daily-equity", runId],
    queryFn: () => fetchDailyEquity(runId!),
    enabled: enabled && runId !== null,
  });
}

export function useBacktestList(params?: {
  strategy_id?: number;
  status?: string;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: ["backtest-list", params],
    queryFn: () => fetchBacktestList(params),
  });
}

/**
 * 전략의 최신 완료된 백테스트 run_id를 반환합니다.
 * completed 상태의 가장 최근 백테스트 (created_at DESC → items[0]).
 */
export function useLatestCompletedRunId(
  strategyId: number | null,
): { runId: number | null; isLoading: boolean } {
  const { data, isLoading } = useBacktestList(
    strategyId !== null
      ? { strategy_id: strategyId, status: "completed", page_size: 1 }
      : undefined,
  );
  const runId =
    strategyId !== null && data && data.items.length > 0
      ? data.items[0].id
      : null;
  return { runId, isLoading };
}
