import { createContext, useContext, useReducer, type ReactNode, type Dispatch } from "react";
import { type DraftAction, draftReducer } from "./reducer";
import { type StrategyDraft, emptyDraft } from "./types";

type ContextValue = {
  draft: StrategyDraft;
  dispatch: Dispatch<DraftAction>;
};

const StrategyDraftContext = createContext<ContextValue | null>(null);

export function StrategyDraftProvider({
  initial,
  children,
}: {
  initial?: StrategyDraft;
  children: ReactNode;
}) {
  const [draft, dispatch] = useReducer(draftReducer, initial ?? emptyDraft());
  return (
    <StrategyDraftContext.Provider value={{ draft, dispatch }}>
      {children}
    </StrategyDraftContext.Provider>
  );
}

export function useStrategyDraft(): ContextValue {
  const ctx = useContext(StrategyDraftContext);
  if (!ctx) {
    throw new Error(
      "useStrategyDraft는 <StrategyDraftProvider> 안에서만 사용 가능합니다",
    );
  }
  return ctx;
}
