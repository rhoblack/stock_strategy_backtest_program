import { Link } from "react-router-dom";
import BlockPalette from "../features/strategy-builder/components/BlockPalette";
import StrategyCanvas from "../features/strategy-builder/components/StrategyCanvas";
import ConditionEditorPanel from "../features/strategy-builder/components/ConditionEditorPanel";

/**
 * 전략 빌더 페이지 — 3열 레이아웃 (설계서 01번 3절).
 */
export default function StrategyBuilderPage() {
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
        <Link to="/strategies" style={{ fontSize: 14, color: "#6b7280", textDecoration: "none" }}>
          ← 전략 목록
        </Link>
        <h1 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>새 전략 만들기</h1>
        <button
          type="button"
          disabled
          style={{
            marginLeft: "auto",
            padding: "6px 12px",
            border: "1px solid #d1d5db",
            borderRadius: 4,
            background: "white",
            color: "#9ca3af",
            cursor: "not-allowed",
          }}
          title="구현 예정"
        >
          저장
        </button>
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
        <ConditionEditorPanel />
      </div>
    </div>
  );
}
