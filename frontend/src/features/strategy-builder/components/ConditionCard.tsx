import type { Section } from "../state/types";
import type { ConditionInstance } from "../state/types";
import { useStrategyDraft } from "../state/StrategyDraftContext";
import { renderSentence } from "../utils/renderSentence";

type Props = {
  section: Section;
  instance: ConditionInstance;
};

export default function ConditionCard({ section, instance }: Props) {
  const { draft, dispatch } = useStrategyDraft();
  const isSelected =
    draft.selected?.section === section &&
    draft.selected?.instance_id === instance.instance_id;

  return (
    <div
      role="listitem"
      onClick={() => dispatch({ type: "SELECT", section, instance_id: instance.instance_id })}
      style={{
        padding: "8px 10px",
        marginTop: 6,
        border: isSelected ? "2px solid #2563eb" : "1px solid #d1d5db",
        borderRadius: 4,
        background: "white",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        cursor: "pointer",
      }}
      data-testid={`condition-card-${instance.instance_id}`}
    >
      <span style={{ fontSize: 13 }}>{renderSentence(instance)}</span>
      <button
        type="button"
        aria-label="조건 삭제"
        onClick={(e) => {
          e.stopPropagation();
          dispatch({ type: "REMOVE_CONDITION", section, instance_id: instance.instance_id });
        }}
        style={{
          border: "none",
          background: "transparent",
          color: "#9ca3af",
          cursor: "pointer",
          fontSize: 16,
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </div>
  );
}
