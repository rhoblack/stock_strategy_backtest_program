import { useStrategyDraft } from "../state/StrategyDraftContext";
import { buildPreviewText } from "../utils/buildPreviewText";

/**
 * 자연어 전략 설명 (설계서 01번 9절).
 */
export default function StrategyPreviewPanel() {
  const { draft } = useStrategyDraft();
  const lines = buildPreviewText(draft);

  return (
    <section
      aria-label="전략 미리보기"
      style={{
        padding: 12,
        borderTop: "1px solid #e5e7eb",
        background: "#fafafa",
      }}
    >
      <h3 style={{ fontSize: 13, fontWeight: 600, marginTop: 0 }}>전략 미리보기</h3>
      <div style={{ fontSize: 12, color: "#374151", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
        {lines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    </section>
  );
}
