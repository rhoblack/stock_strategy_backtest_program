/**
 * 오른쪽 조건 편집 패널 placeholder.
 * Step 5에서 선택된 조건의 parameters 메타로 자동 폼 생성.
 */
export default function ConditionEditorPanel() {
  return (
    <aside
      aria-label="조건 편집 패널"
      style={{ borderLeft: "1px solid #e5e7eb", padding: 12, overflowY: "auto" }}
    >
      <h2 style={{ fontSize: 14, fontWeight: 600 }}>조건 편집</h2>
      <p style={{ fontSize: 12, color: "#9ca3af" }}>
        조립 영역의 조건 카드를 클릭하면 여기서 파라미터를 수정할 수 있습니다 (구현 예정).
      </p>
    </aside>
  );
}
