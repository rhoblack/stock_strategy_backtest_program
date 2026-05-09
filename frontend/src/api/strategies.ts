/**
 * 전략 CRUD API hooks.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

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
