/**
 * 초보자/전문가 모드 (Wave 12-030, 01-k 부분).
 *
 * - default = "expert" (현재 동작 유지 — 6 비조건 섹션 모두 노출)
 * - "beginner": 4 조건 섹션 + position_sizing만 노출 (StrategyConfigPanel 안에서
 *               position_sizing 탭만 보이고 나머지 5개는 숨김)
 * - localStorage key "stockstrategy.builder_mode" 에 영속화
 */
import { useEffect, useState } from "react";

export type BuilderMode = "beginner" | "expert";

const STORAGE_KEY = "stockstrategy.builder_mode";
const DEFAULT_MODE: BuilderMode = "expert";

function readStoredMode(): BuilderMode {
  if (typeof window === "undefined" || !window.localStorage) return DEFAULT_MODE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "beginner" || raw === "expert") return raw;
    return DEFAULT_MODE;
  } catch {
    return DEFAULT_MODE;
  }
}

function writeStoredMode(mode: BuilderMode): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function useBuilderMode(): {
  mode: BuilderMode;
  setMode: (m: BuilderMode) => void;
  toggle: () => void;
  isBeginner: boolean;
  isExpert: boolean;
} {
  const [mode, setModeState] = useState<BuilderMode>(() => readStoredMode());

  useEffect(() => {
    writeStoredMode(mode);
  }, [mode]);

  const setMode = (m: BuilderMode) => setModeState(m);
  const toggle = () => setModeState((m) => (m === "beginner" ? "expert" : "beginner"));

  return {
    mode,
    setMode,
    toggle,
    isBeginner: mode === "beginner",
    isExpert: mode === "expert",
  };
}

/**
 * 초보자 모드에서 노출할 ConfigSection 키 (StrategyConfigPanel 필터링용).
 * expert 모드에서는 모든 섹션 노출.
 */
export const BEGINNER_VISIBLE_CONFIG_SECTIONS = ["position_sizing"] as const;
