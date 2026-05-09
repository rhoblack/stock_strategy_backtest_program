import { useParams, Link } from "react-router-dom";
import {
  useBacktestStatus,
  useBacktestSummary,
  useBacktestTrades,
  useDailyEquity,
} from "../api/backtests";
import { useChartData } from "../api/chartData";
import CandleTradeChart from "../features/backtest-result/components/CandleTradeChart";
import EquityCurveChart from "../features/backtest-result/components/EquityCurveChart";

/**
 * 백테스트 결과 페이지 — status 폴링 + 요약 + 거래 내역 표.
 * 봉차트는 Phase 5에서 추가.
 */
export default function BacktestResultPage() {
  const { runId } = useParams<{ runId: string }>();
  const id = runId ? Number(runId) : null;
  const { data: status } = useBacktestStatus(id);
  const isCompleted = status?.status === "completed";

  const { data: summaryWrap } = useBacktestSummary(id, isCompleted);
  const { data: tradesWrap } = useBacktestTrades(id, isCompleted);
  const { data: equityWrap } = useDailyEquity(id, isCompleted);
  const { data: chartData } = useChartData(id, isCompleted);

  const summary = summaryWrap?.summary;

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 1100 }}>
      <p>
        <Link to="/strategies" style={{ color: "#6b7280" }}>
          ← 전략 목록
        </Link>
      </p>
      <h1 style={{ fontSize: 18, fontWeight: 600 }}>
        백테스트 결과 #{runId}
      </h1>

      {!status && <p>로딩 중...</p>}

      {status && (
        <p style={{ fontSize: 13, color: "#6b7280" }}>
          상태:{" "}
          <strong
            data-testid="run-status"
            style={{
              color:
                status.status === "completed"
                  ? "#16a34a"
                  : status.status === "failed"
                    ? "#dc2626"
                    : "#2563eb",
            }}
          >
            {status.status}
          </strong>{" "}
          ({status.progress_pct.toFixed(0)}%)
          {status.error_message && (
            <span style={{ color: "crimson" }}> — {status.error_message.slice(0, 200)}</span>
          )}
        </p>
      )}

      {summary && (
        <section aria-label="요약 카드" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(4, 1fr)", marginTop: 16 }}>
          <Card label="총 수익률" value={`${summary.total_return_pct.toFixed(2)}%`} />
          <Card label="연평균 수익률 (CAGR)" value={`${summary.annual_return_pct.toFixed(2)}%`} />
          <Card label="최대 낙폭 (MDD)" value={`${summary.mdd_pct.toFixed(2)}%`} />
          <Card label="최종 자산" value={`${Math.round(summary.final_equity).toLocaleString()}원`} />
          <Card label="거래 횟수" value={String(summary.trade_count)} />
          <Card label="승률" value={`${summary.win_rate.toFixed(1)}%`} />
          <Card label="평균 보유일" value={summary.avg_holding_days.toFixed(1)} />
          <Card
            label="Profit Factor"
            value={
              summary.profit_factor === null
                ? "—"
                : summary.profit_factor.toFixed(2)
            }
          />
        </section>
      )}

      {isCompleted && (
        <section aria-label="다운로드" style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>다운로드</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[
              { kind: "summary", label: "요약 (CSV)" },
              { kind: "trades", label: "거래 내역 (CSV)" },
              { kind: "daily-equity", label: "일별 자산 (CSV)" },
              { kind: "cash-events", label: "예수금 이벤트 (CSV)" },
              { kind: "strategy", label: "전략 스냅샷 (JSON)" },
              { kind: "zip", label: "전체 ZIP" },
            ].map(({ kind, label }) => (
              <a
                key={kind}
                href={`/api/backtests/${id}/export/${kind}`}
                download
                style={dlBtn}
              >
                ⬇ {label}
              </a>
            ))}
          </div>
        </section>
      )}

      {chartData && chartData.candles.length > 0 && (
        <section aria-label="봉차트" style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>봉차트 + 매수/매도 마커</h2>
          <CandleTradeChart candles={chartData.candles} markers={chartData.markers} />
        </section>
      )}

      {chartData && chartData.equity_curve.length > 0 && (
        <section aria-label="자산 곡선" style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>자산 곡선</h2>
          <EquityCurveChart equity={chartData.equity_curve} />
        </section>
      )}

      {tradesWrap && tradesWrap.items.length > 0 && (
        <section aria-label="거래 내역" style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>거래 내역</h2>
          <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f9fafb" }}>
                <th style={th}>종목</th>
                <th style={th}>매수일</th>
                <th style={th}>매수가</th>
                <th style={th}>수량</th>
                <th style={th}>청산일</th>
                <th style={th}>실현 손익</th>
                <th style={th}>수익률</th>
                <th style={th}>매도 사유</th>
              </tr>
            </thead>
            <tbody>
              {tradesWrap.items.map((tg) => {
                const lastSell = tg.executions
                  .filter((e) => e.execution_type !== "BUY")
                  .at(-1);
                return (
                  <tr key={tg.trade_group_id} style={{ borderTop: "1px solid #f3f4f6" }}>
                    <td style={td}>{tg.symbol}</td>
                    <td style={td}>{tg.entry_date}</td>
                    <td style={tdNum}>{Math.round(tg.entry_price).toLocaleString()}</td>
                    <td style={tdNum}>{tg.entry_quantity}</td>
                    <td style={td}>{lastSell?.execution_date ?? "보유 중"}</td>
                    <td style={tdNum}>
                      {tg.final_profit !== null
                        ? Math.round(tg.final_profit).toLocaleString()
                        : "—"}
                    </td>
                    <td style={tdNum}>
                      {tg.final_profit_rate !== null
                        ? `${tg.final_profit_rate.toFixed(2)}%`
                        : "—"}
                    </td>
                    <td style={td}>{lastSell?.exit_reason ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {equityWrap && equityWrap.items.length > 0 && (
        <section aria-label="일별 자산" style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>일별 자산 (요약)</h2>
          <p style={{ fontSize: 12, color: "#6b7280" }}>
            전체 {equityWrap.total_count}일. 첫/마지막만 표시 — 차트는 Phase 5에서.
          </p>
          <pre style={{ fontSize: 12, background: "#f9fafb", padding: 8, borderRadius: 4 }}>
            {`첫 날: ${equityWrap.items[0].date} → ${Math.round(equityWrap.items[0].total_equity).toLocaleString()}원
마지막: ${equityWrap.items.at(-1)!.date} → ${Math.round(equityWrap.items.at(-1)!.total_equity).toLocaleString()}원`}
          </pre>
        </section>
      )}
    </div>
  );
}

const th: React.CSSProperties = { textAlign: "left", padding: "6px 8px", fontWeight: 600 };
const td: React.CSSProperties = { padding: "6px 8px" };
const tdNum: React.CSSProperties = { padding: "6px 8px", textAlign: "right" };
const dlBtn: React.CSSProperties = {
  padding: "6px 12px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  textDecoration: "none",
  color: "#1f2937",
  fontSize: 12,
  background: "white",
};

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        padding: 12,
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        background: "white",
      }}
    >
      <div style={{ fontSize: 11, color: "#6b7280" }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4 }}>{value}</div>
    </div>
  );
}
