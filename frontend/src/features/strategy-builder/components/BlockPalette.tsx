import { useConditions } from "../../../api/conditions";
import { useStrategyDraft } from "../state/StrategyDraftContext";
import type { ConditionMeta } from "../../../types/condition";

/**
 * 조건 블록 팔레트.
 * 클릭 시 allowed_in의 첫 섹션으로 ADD_CONDITION dispatch.
 */
export default function BlockPalette() {
  const { data, isLoading, error } = useConditions();
  const { dispatch } = useStrategyDraft();

  if (isLoading) return <aside aria-label="블록 팔레트">로딩 중...</aside>;
  if (error || !data)
    return (
      <aside aria-label="블록 팔레트" style={{ color: "crimson" }}>
        조건 카탈로그 불러오기 실패
      </aside>
    );

  const grouped = new Map<string, ConditionMeta[]>();
  for (const cond of data) {
    if (!grouped.has(cond.category)) grouped.set(cond.category, []);
    grouped.get(cond.category)!.push(cond);
  }

  return (
    <aside
      aria-label="블록 팔레트"
      style={{ borderRight: "1px solid #e5e7eb", padding: 12, overflowY: "auto" }}
    >
      <h2 style={{ fontSize: 14, fontWeight: 600 }}>블록 팔레트</h2>
      {[...grouped.entries()].map(([category, items]) => (
        <section key={category} style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 12, color: "#6b7280", textTransform: "uppercase" }}>{category}</h3>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((item) => (
              <li key={item.type}>
                <button
                  type="button"
                  onClick={() =>
                    dispatch({
                      type: "ADD_CONDITION",
                      section: item.allowed_in[0],
                      meta: item,
                    })
                  }
                  title={`${item.description}\n클릭하여 ${item.allowed_in[0]} 영역에 추가`}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "6px 8px",
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    fontSize: 13,
                    borderRadius: 4,
                  }}
                >
                  {item.name}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}
