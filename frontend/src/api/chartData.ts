/**
 * GET /api/backtests/{run_id}/chart-data hook.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type CandleBar = {
  time: string; // ISO yyyy-mm-dd
  open: number;
  high: number;
  low: number;
  close: number;
};

export type ChartMarker = {
  time: string;
  type: "BUY" | "SELL" | "PARTIAL_SELL";
  price: number;
  quantity: number;
  exit_reason: string | null;
};

export type EquityPoint = {
  time: string;
  value: number;
  drawdown: number;
};

export type ChartDataOut = {
  candles: CandleBar[];
  markers: ChartMarker[];
  equity_curve: EquityPoint[];
};

export async function fetchChartData(runId: number): Promise<ChartDataOut> {
  return (await api.get<ChartDataOut>(`/api/backtests/${runId}/chart-data`)).data;
}

export function useChartData(runId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["chart-data", runId],
    queryFn: () => fetchChartData(runId!),
    enabled: enabled && runId !== null,
  });
}
