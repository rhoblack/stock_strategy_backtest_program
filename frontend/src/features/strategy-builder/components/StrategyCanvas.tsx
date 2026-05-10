import { useStrategyDraft } from "../state/StrategyDraftContext";
import { type Section, SECTIONS, SECTION_LABEL } from "../state/types";
import ConditionCard from "./ConditionCard";
import StrategyConfigPanel from "./StrategyConfigPanel";

/**
 * 전략 조립 영역. 4 조건 섹션 + 6 비조건 섹션(StrategyConfigPanel).
 */
export default function StrategyCanvas() {
  const { draft, dispatch } = useStrategyDraft();

  return (
    <main aria-label="전략 조립 영역" style={{ padding: 16, overflowY: "auto" }}>
      <h2 style={{ fontSize: 14, fontWeight: 600 }}>전략 조립 영역</h2>

      {SECTIONS.map((section) => (
        <SectionBlock key={section} section={section} />
      ))}

      <StrategyConfigPanel />
    </main>
  );

  function SectionBlock({ section }: { section: Section }) {
    const sec = draft.sections[section];
    return (
      <section
        aria-label={SECTION_LABEL[section]}
        style={{
          marginTop: 16,
          padding: 12,
          border: "1px solid #e5e7eb",
          borderRadius: 6,
          background: "#f9fafb",
        }}
      >
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 6,
          }}
        >
          <h3 style={{ fontSize: 13, fontWeight: 500, color: "#374151", margin: 0 }}>
            {SECTION_LABEL[section]}
          </h3>
          <label style={{ fontSize: 12, color: "#6b7280" }}>
            조건 조합:{" "}
            <select
              aria-label={`${SECTION_LABEL[section]} 조합`}
              value={sec.logic}
              onChange={(e) =>
                dispatch({
                  type: "SET_LOGIC",
                  section,
                  logic: e.target.value as "AND" | "OR",
                })
              }
              style={{ fontSize: 12 }}
            >
              <option value="AND">모두 만족 (AND)</option>
              <option value="OR">하나라도 만족 (OR)</option>
            </select>
          </label>
        </header>

        {sec.conditions.length === 0 ? (
          <p style={{ fontSize: 12, color: "#9ca3af", margin: 0 }}>
            왼쪽 팔레트에서 조건을 추가하세요.
          </p>
        ) : (
          <div role="list">
            {sec.conditions.map((c) => (
              <ConditionCard key={c.instance_id} section={section} instance={c} />
            ))}
          </div>
        )}
      </section>
    );
  }
}

