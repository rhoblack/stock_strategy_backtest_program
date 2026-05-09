import { Link } from "react-router-dom";
import { useStrategies } from "../api/strategies";

/**
 * 전략 목록 페이지 — useStrategies + 백테스트 실행 링크.
 */
export default function StrategyListPage() {
  const { data, isLoading, error } = useStrategies();

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 920 }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h1 style={{ fontSize: 18, fontWeight: 600 }}>주식 전략 연구소</h1>
        <Link
          to="/strategies/new"
          style={{
            padding: "6px 12px",
            background: "#2563eb",
            color: "white",
            borderRadius: 4,
            textDecoration: "none",
            fontSize: 14,
          }}
        >
          ＋ 새 전략 만들기
        </Link>
      </header>

      <h2 style={{ fontSize: 14, fontWeight: 500, marginTop: 24, color: "#6b7280" }}>
        저장된 전략
      </h2>

      {isLoading && <p>로딩 중...</p>}
      {error && (
        <p style={{ color: "crimson", fontSize: 13 }}>
          백엔드 연결 실패. <code>uvicorn app.main:app --reload --port 8000</code> 실행 필요.
        </p>
      )}
      {data && data.length === 0 && (
        <p style={{ color: "#9ca3af", fontSize: 13 }}>아직 저장된 전략이 없습니다.</p>
      )}
      {data && data.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {data.map((s) => (
            <li
              key={s.id}
              style={{
                padding: 12,
                border: "1px solid #e5e7eb",
                borderRadius: 6,
                marginTop: 8,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ fontWeight: 600 }}>{s.name}</div>
                <div style={{ fontSize: 12, color: "#6b7280" }}>
                  {s.tags.join(", ") || "태그 없음"}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <Link to={`/backtests/new?strategy_id=${s.id}`} style={btn}>
                  백테스트 실행
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const btn: React.CSSProperties = {
  padding: "4px 10px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  textDecoration: "none",
  color: "#1f2937",
  fontSize: 12,
};
