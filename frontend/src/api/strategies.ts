/**
 * 전략 CRUD API hooks.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type StrategyLastBacktest = {
  total_return: number;
  mdd: number;
  win_rate: number;
  /** 백테스트 실행일 (ISO 날짜 문자열, 옵셔널) */
  run_date?: string | null;
};

export type StrategyOut = {
  id: number;
  user_id: number;
  name: string;
  description: string;
  strategy_json: Record<string, unknown>;
  tags: string[];
  favorite: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  /** API가 반환하지 않으면 undefined — graceful 처리 */
  last_backtest?: StrategyLastBacktest | null;
};

export type StrategyCreatePayload = {
  name: string;
  description?: string;
  strategy_json: Record<string, unknown>;
  tags?: string[];
  favorite?: boolean;
};

export async function fetchStrategies(): Promise<StrategyOut[]> {
  return (await api.get<StrategyOut[]>("/api/strategies")).data;
}

export async function createStrategy(
  payload: StrategyCreatePayload,
): Promise<StrategyOut> {
  return (await api.post<StrategyOut>("/api/strategies", payload)).data;
}

/**
 * 전략 복사. 백엔드 라우트(routes_strategies.py)는 new_name을 query parameter로 받음.
 */
export async function duplicateStrategy(
  strategyId: number,
  newName: string,
): Promise<StrategyOut> {
  return (
    await api.post<StrategyOut>(
      `/api/strategies/${strategyId}/duplicate`,
      undefined,
      { params: { new_name: newName } },
    )
  ).data;
}

export function useStrategies() {
  return useQuery({ queryKey: ["strategies"], queryFn: fetchStrategies });
}

export function useCreateStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createStrategy,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });
}

export function useDuplicateStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ strategyId, newName }: { strategyId: number; newName: string }) =>
      duplicateStrategy(strategyId, newName),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });
}
