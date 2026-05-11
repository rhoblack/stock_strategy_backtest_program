import { Link } from "react-router-dom";
import { useStrategies, type StrategyLastBacktest } from "../api/strategies";

/**
 * 전략 목록 페이지 — useStrategies + 백테스트 실행 링크 + last_backtest 표시.
 */
export default function StrategyListPage() {
  const { data, isLoading, error } = useStrategies();

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 920 }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h1 style={{ fontSize: 18, fontWeight: 600 }}>주식 전략 연구소</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <Link
            to="/strategies/compare"
            style={{
              padding: "6px 12px",
              background: "white",
              color: "#1f2937",
              border: "1px solid #d1d5db",
              borderRadius: 4,
              textDecoration: "none",
              fontSize: 14,
            }}
          >
            전략 비교
          </Link>
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
        </div>
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
                gap: 12,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{s.name}</div>
                <div style={{ fontSize: 12, color: "#6b7280" }}>
                  {s.tags.join(", ") || "태그 없음"}
                </div>
              </div>

              {/* last_backtest 정보 */}
              <LastBacktestBadge lastBacktest={s.last_backtest} />

              <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
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

/** 마지막 백테스트 정보 뱃지 — API가 반환하지 않으면 "-" 표시 */
function LastBacktestBadge({
  lastBacktest,
}: {
  lastBacktest: StrategyLastBacktest | null | undefined;
}) {
  if (!lastBacktest) {
    return (
      <div style={badgeContainerStyle} data-testid="last-backtest-empty">
        <span style={{ fontSize: 11, color: "#9ca3af" }}>최근 백테스트 없음</span>
      </div>
    );
  }

  const returnPct = lastBacktest.total_return;
  const returnColor = returnPct >= 0 ? "#16a34a" : "#dc2626";
  const returnLabel = returnPct >= 0 ? `+${returnPct.toFixed(1)}%` : `${returnPct.toFixed(1)}%`;
  const dateLabel = lastBacktest.run_date
    ? formatDate(lastBacktest.run_date)
    : null;

  return (
    <div style={badgeContainerStyle} data-testid="last-backtest-badge">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {dateLabel && (
          <span style={{ fontSize: 11, color: "#6b7280" }}>{dateLabel}</span>
        )}
        <span
          data-testid="last-backtest-return"
          style={{ fontSize: 13, fontWeight: 600, color: returnColor }}
        >
          {returnLabel}
        </span>
        <span style={{ fontSize: 11, color: "#9ca3af" }}>
          MDD {lastBacktest.mdd.toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

/** "2026-05-11" → "2026.05.11" */
function formatDate(iso: string): string {
  return iso.slice(0, 10).replace(/-/g, ".");
}

const btn: React.CSSProperties = {
  padding: "4px 10px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  textDecoration: "none",
  color: "#1f2937",
  fontSize: 12,
};

const badgeContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "flex-end",
  minWidth: 140,
};
