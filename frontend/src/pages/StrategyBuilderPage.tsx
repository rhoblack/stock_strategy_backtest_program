import BlockPalette from "../features/strategy-builder/components/BlockPalette";
import StrategyCanvas from "../features/strategy-builder/components/StrategyCanvas";
import ConditionEditorPanel from "../features/strategy-builder/components/ConditionEditorPanel";
import StrategyPreviewPanel from "../features/strategy-builder/components/StrategyPreviewPanel";
import StrategyValidationPanel from "../features/strategy-builder/components/StrategyValidationPanel";
import StrategyHeader from "../features/strategy-builder/components/StrategyHeader";
import {
  StrategyDraftProvider,
  useStrategyDraft,
} from "../features/strategy-builder/state/StrategyDraftContext";
import { hasErrors, validateDraft } from "../features/strategy-builder/utils/validateDraft";
import { serializeDraft } from "../features/strategy-builder/utils/serializeDraft";
import { useCreateStrategy } from "../api/strategies";
import { useState } from "react";

/**
 * 전략 빌더 페이지 — 3열 레이아웃 (설계서 01번 3절).
 * StrategyDraftProvider로 빌더 상태를 공유.
 */
export default function StrategyBuilderPage() {
  return (
    <StrategyDraftProvider>
      <BuilderShell />
    </StrategyDraftProvider>
  );
}

function BuilderShell() {
  const { draft } = useStrategyDraft();
  const createMutation = useCreateStrategy();

  // savedStrategyId — 새 전략에서 저장에 성공하면 채워짐 (라우팅 변경 없이 헤더 복사 활성)
  const [savedStrategyId, setSavedStrategyId] = useState<number | null>(null);

  const validation = validateDraft(draft);
  const hasError = hasErrors(validation);
  const canSave = !hasError && draft.name.trim().length > 0 && !createMutation.isPending;

  /**
   * 저장 액션. 성공 시 strategy id를 반환 (StrategyHeader가 백테스트 실행 흐름에서 사용).
   * 실패 시 null.
   */
  const onSave = async (): Promise<number | null> => {
    if (!canSave) return null;
    const { name, ...sections } = serializeDraft(draft);
    return new Promise<number | null>((resolve) => {
      createMutation.mutate(
        { name, strategy_json: sections, tags: [] },
        {
          onSuccess: (created) => {
            setSavedStrategyId(created.id);
            resolve(created.id);
          },
          onError: () => resolve(null),
        },
      );
    });
  };

  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: "auto 1fr",
        height: "100vh",
        fontFamily: "sans-serif",
      }}
    >
      <StrategyHeader
        savedStrategyId={savedStrategyId}
        canSave={canSave}
        onSave={onSave}
        isSaving={createMutation.isPending}
        saveErrorMessage={createMutation.isError ? "저장 실패" : null}
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "240px 1fr 320px",
          minHeight: 0,
        }}
      >
        <BlockPalette />
        <StrategyCanvas />
        <div
          style={{
            borderLeft: "1px solid #e5e7eb",
            display: "grid",
            gridTemplateRows: "1fr auto auto",
            minHeight: 0,
          }}
        >
          <ConditionEditorPanel />
          <StrategyPreviewPanel />
          <StrategyValidationPanel />
        </div>
      </div>
    </div>
  );
}
