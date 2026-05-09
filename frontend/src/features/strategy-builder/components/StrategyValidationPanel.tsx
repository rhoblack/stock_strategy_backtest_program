import { useStrategyDraft } from "../state/StrategyDraftContext";
import { validateDraft } from "../utils/validateDraft";

/**
 * 전략 검증 패널 (설계서 01번 10절).
 * 오류는 빨강, 경고는 주황으로 표시.
 */
export default function StrategyValidationPanel() {
  const { draft } = useStrategyDraft();
  const items = validateDraft(draft);

  return (
    <section
      aria-label="전략 검증"
      style={{
        padding: 12,
        borderTop: "1px solid #e5e7eb",
      }}
    >
      <h3 style={{ fontSize: 13, fontWeight: 600, marginTop: 0 }}>검증 결과</h3>
      {items.length === 0 ? (
        <p style={{ fontSize: 12, color: "#16a34a", margin: 0 }}>모든 항목 통과 ✓</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          {items.map((item) => (
            <li
              key={item.code}
              data-level={item.level}
              style={{
                fontSize: 12,
                color: item.level === "error" ? "#dc2626" : "#d97706",
                display: "flex",
                gap: 6,
              }}
            >
              <strong>{item.level === "error" ? "✕" : "!"}</strong>
              <span>{item.message}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
