import { useConditions } from "../../../api/conditions";

/**
 * 왼쪽 블록 팔레트 — GET /api/conditions 결과를 카테고리별로 그룹화하여 표시.
 * Step 4에서 클릭 → StrategyCanvas 추가 인터랙션을 붙임.
 */
export default function BlockPalette() {
  const { data, isLoading, error } = useConditions();

  if (isLoading) return <aside aria-label="블록 팔레트">로딩 중...</aside>;
  if (error || !data)
    return (
      <aside aria-label="블록 팔레트" style={{ color: "crimson" }}>
        조건 카탈로그 불러오기 실패
      </aside>
    );

  const grouped = new Map<string, typeof data>();
  for (const cond of data) {
    if (!grouped.has(cond.category)) grouped.set(cond.category, []);
    grouped.get(cond.category)!.push(cond);
  }

  return (
    <aside aria-label="블록 팔레트" style={{ borderRight: "1px solid #e5e7eb", padding: 12, overflowY: "auto" }}>
      <h2 style={{ fontSize: 14, fontWeight: 600 }}>블록 팔레트</h2>
      {[...grouped.entries()].map(([category, items]) => (
        <section key={category} style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 12, color: "#6b7280", textTransform: "uppercase" }}>{category}</h3>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((item) => (
              <li
                key={item.type}
                style={{
                  padding: "6px 8px",
                  borderRadius: 4,
                  cursor: "grab",
                  fontSize: 13,
                }}
                title={item.description}
              >
                {item.name}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}
