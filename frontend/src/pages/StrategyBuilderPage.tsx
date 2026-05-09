import { Link, useNavigate } from "react-router-dom";
import BlockPalette from "../features/strategy-builder/components/BlockPalette";
import StrategyCanvas from "../features/strategy-builder/components/StrategyCanvas";
import ConditionEditorPanel from "../features/strategy-builder/components/ConditionEditorPanel";
import StrategyPreviewPanel from "../features/strategy-builder/components/StrategyPreviewPanel";
import StrategyValidationPanel from "../features/strategy-builder/components/StrategyValidationPanel";
import {
  StrategyDraftProvider,
  useStrategyDraft,
} from "../features/strategy-builder/state/StrategyDraftContext";
import { hasErrors, validateDraft } from "../features/strategy-builder/utils/validateDraft";
import { serializeDraft } from "../features/strategy-builder/utils/serializeDraft";
import { useCreateStrategy } from "../api/strategies";

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
  const { draft, dispatch } = useStrategyDraft();
  const navigate = useNavigate();
  const createMutation = useCreateStrategy();

  const validation = validateDraft(draft);
  const hasError = hasErrors(validation);
  const canSave = !hasError && draft.name.trim().length > 0 && !createMutation.isPending;

  const onSave = () => {
    if (!canSave) return;
    const { name, ...sections } = serializeDraft(draft);
    createMutation.mutate(
      { name, strategy_json: sections, tags: [] },
      {
        onSuccess: () => {
          navigate("/strategies");
        },
      },
    );
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
      <header
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <Link
          to="/strategies"
          style={{ fontSize: 14, color: "#6b7280", textDecoration: "none" }}
        >
          ← 전략 목록
        </Link>
        <input
          aria-label="전략 이름"
          placeholder="전략 이름 입력"
          value={draft.name}
          onChange={(e) => dispatch({ type: "SET_NAME", name: e.target.value })}
          style={{
            fontSize: 14,
            padding: "4px 8px",
            border: "1px solid #d1d5db",
            borderRadius: 4,
            minWidth: 200,
          }}
        />
        <button
          type="button"
          onClick={onSave}
          disabled={!canSave}
          aria-label="전략 저장"
          style={{
            marginLeft: "auto",
            padding: "6px 12px",
            border: "1px solid #d1d5db",
            borderRadius: 4,
            background: canSave ? "#2563eb" : "white",
            color: canSave ? "white" : "#9ca3af",
            cursor: canSave ? "pointer" : "not-allowed",
          }}
        >
          {createMutation.isPending ? "저장 중..." : "저장"}
        </button>
        {createMutation.isError && (
          <span style={{ fontSize: 12, color: "crimson" }}>저장 실패</span>
        )}
      </header>

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
