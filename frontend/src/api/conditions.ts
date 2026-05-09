/**
 * GET /api/conditions — 조건 카탈로그 fetch + TanStack Query hook.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { ConditionMeta } from "../types/condition";

export async function fetchConditions(): Promise<ConditionMeta[]> {
  const res = await api.get<ConditionMeta[]>("/api/conditions");
  return res.data;
}

export function useConditions() {
  return useQuery({
    queryKey: ["conditions"],
    queryFn: fetchConditions,
    staleTime: 5 * 60 * 1000, // 5분 — 카탈로그는 자주 안 바뀜
  });
}
