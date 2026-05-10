/**
 * GET /api/backtests/{run_id}/chart-data hook.
 *
 * 031에서 chart-data 응답이 daily_prices DB 기반으로 전환됨.
 * 응답 형식 (호환):
 *   - candles[]: time/open/high/low/close/(volume)
 *   - markers[]: time/type/price/quantity/exit_reason
 *   - equity_curve[]: time/value/(drawdown)
 *   - 신규 메타: symbol/source/downsampled/downsample_stride/date_range/use_adjusted/resolution
 *
 * 5 query options (031): symbol / start_date / end_date / use_adjusted / downsample
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type CandleBar = {
  time: string; // ISO yyyy-mm-dd
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
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

/** chart-data API의 신규 메타데이터 (031). */
export type ChartDataMeta = {
  symbol?: string;
  source?: "daily_prices" | "synthetic";
  resolution?: string;
  downsampled?: boolean;
  downsample_stride?: number;
  date_range?: { start: string; end: string };
  use_adjusted?: boolean;
};

export type ChartDataOut = {
  candles: CandleBar[];
  markers: ChartMarker[];
  equity_curve: EquityPoint[];
} & ChartDataMeta;

/** 031에서 추가된 chart-data query option. 모두 optional. */
export type ChartDataQuery = {
  symbol?: string;
  start_date?: string;
  end_date?: string;
  use_adjusted?: boolean;
  downsample?: number;
};

export async function fetchChartData(
  runId: number,
  query: ChartDataQuery = {},
): Promise<ChartDataOut> {
  return (
    await api.get<ChartDataOut>(`/api/backtests/${runId}/chart-data`, {
      params: query,
    })
  ).data;
}

export function useChartData(
  runId: number | null,
  enabled = true,
  query: ChartDataQuery = {},
) {
  return useQuery({
    queryKey: ["chart-data", runId, query],
    queryFn: () => fetchChartData(runId!, query),
    enabled: enabled && runId !== null,
  });
}
