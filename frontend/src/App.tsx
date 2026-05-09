import { useConditions } from "./api/conditions";

/**
 * 임시 루트 컴포넌트.
 * Step 3에서 router + StrategyBuilderPage로 교체.
 */
export default function App() {
  const { data, isLoading, error } = useConditions();

  return (
    <div style={{ fontFamily: "sans-serif", padding: 24 }}>
      <h1>주식 전략 연구소</h1>
      <p>Phase 3 / Step 2 — 프론트엔드 골격 + GET /api/conditions 연동 검증</p>

      {isLoading && <p>로딩 중...</p>}
      {error && (
        <p style={{ color: "crimson" }}>
          백엔드 연결 실패. uvicorn app.main:app --reload --port 8000 실행 필요.
        </p>
      )}
      {data && (
        <ul>
          {data.map((c) => (
            <li key={c.type}>
              <strong>{c.name}</strong> — {c.category} (
              {c.requires_position ? "포지션" : "시계열"})
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
