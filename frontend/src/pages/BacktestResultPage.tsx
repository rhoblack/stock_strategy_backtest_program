import { useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  useBacktestStatus,
  useBacktestSummary,
  useBacktestTrades,
  useDailyEquity,
} from "../api/backtests";
import { useChartData } from "../api/chartData";
import CandleTradeChart, {
  type VisibleRange,
} from "../features/backtest-result/components/CandleTradeChart";
import EquityCurveChart from "../features/backtest-result/components/EquityCurveChart";
import ResultTabs, {
  RESULT_TABS,
  type ResultTabKey,
} from "../features/backtest-result/components/ResultTabs";
import SymbolSelector, {
  type SymbolOption,
} from "../features/backtest-result/components/SymbolSelector";
import TradesTable, {
  type TradeRowClickInfo,
} from "../features/backtest-result/components/TradesTable";
import { DrawdownChart, CashChart, PositionsCountChart, VolumeChart, BenchmarkCompareChart } from "../components/charts";
import { SummaryCard as Card } from "../components/ui";

/**
 * 백테스트 결과 페이지 — 08번 §3·§4 정합 6 탭 구조.
 *
 * 탭: 요약 / 거래 / 자산 / 월별 성과 / 리스크 / 자금 관리
 *
 * 데이터 소스:
 *   - 요약/거래/자산: useBacktestSummary, useBacktestTrades, useDailyEquity
 *   - 차트(봉/equity/drawdown/volume/benchmark): useChartData (031 chart-data, symbol query)
 *   - 자금 관리: useDailyEquity (cash, positions_count)
 *
 * 거래 탭의 TanStack Table 도입 / 거래 클릭 → 차트 이동 / UniverseSelector 등은 033에서.
 */
export default function BacktestResultPage() {
  const { runId } = useParams<{ runId: string }>();
  const id = runId ? Number(runId) : null;
  const { data: status } = useBacktestStatus(id);
  const isCompleted = status?.status === "completed";

  const { data: summaryWrap } = useBacktestSummary(id, isCompleted);
  const { data: tradesWrap } = useBacktestTrades(id, isCompleted);
  const { data: equityWrap } = useDailyEquity(id, isCompleted);

  const [activeTab, setActiveTab] = useState<ResultTabKey>("summary");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  // 거래 클릭 → 봉차트 visibleRange (08-m / 033).
  const [tradeRange, setTradeRange] = useState<VisibleRange | null>(null);

  // 거래 행 클릭 → 종목 변경 + 요약 탭 + 차트 시간 범위 zoom
  const handleTradeRowClick = (info: TradeRowClickInfo) => {
    setSelectedSymbol(info.tradeGroup.symbol);
    setActiveTab("summary");
    setTradeRange({ from: info.entryDate, to: info.exitDate });
  };

  // 종목을 사용자가 직접 변경하면 trade range를 해제 (전체 봉 보기로 복귀).
  const handleSymbolChange = (symbol: string | null) => {
    setSelectedSymbol(symbol);
    setTradeRange(null);
  };

  // trades에서 unique symbols 추출 (드롭다운용). 결정론: symbol ASC.
  const symbolOptions = useMemo<SymbolOption[]>(() => {
    if (!tradesWrap) return [];
    const seen = new Map<string, string>();
    for (const tg of tradesWrap.items) {
      if (!seen.has(tg.symbol)) {
        seen.set(tg.symbol, tg.name);
      }
    }
    return Array.from(seen.entries()).map(([symbol, name]) => ({ symbol, name }));
  }, [tradesWrap]);

  // 종목 선택을 chart-data query로 전달
  const chartQuery = useMemo(
    () => (selectedSymbol ? { symbol: selectedSymbol } : {}),
    [selectedSymbol],
  );
  const { data: chartData } = useChartData(id, isCompleted, chartQuery);

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

      {isCompleted && (
        <ResultTabs active={activeTab} onChange={setActiveTab} />
      )}

      {/* === 요약 탭 === */}
      {isCompleted && activeTab === "summary" && (
        <SummarySection
          summary={summary}
          chartData={chartData}
          symbolOptions={symbolOptions}
          selectedSymbol={selectedSymbol}
          onSymbolChange={handleSymbolChange}
          visibleRange={tradeRange}
          runId={id}
        />
      )}

      {/* === 거래 탭 === */}
      {isCompleted && activeTab === "trades" && (
        <TradesSection trades={tradesWrap} onRowClick={handleTradeRowClick} />
      )}

      {/* === 자산 탭 === */}
      {isCompleted && activeTab === "equity" && (
        <EquitySection
          chartData={chartData}
          equityItems={equityWrap?.items ?? []}
        />
      )}

      {/* === 월별 성과 탭 === */}
      {isCompleted && activeTab === "monthly" && (
        <MonthlySection equityItems={equityWrap?.items ?? []} />
      )}

      {/* === 리스크 탭 === */}
      {isCompleted && activeTab === "risk" && (
        <RiskSection
          chartData={chartData}
          summary={summary}
        />
      )}

      {/* === 자금 관리 탭 === */}
      {isCompleted && activeTab === "cash" && (
        <CashSection
          summary={summary}
          equityItems={equityWrap?.items ?? []}
        />
      )}
    </div>
  );
}

// --- 탭별 섹션 ---

function SummarySection({
  summary,
  chartData,
  symbolOptions,
  selectedSymbol,
  onSymbolChange,
  visibleRange,
  runId,
}: {
  summary: NonNullable<ReturnType<typeof useBacktestSummary>["data"]>["summary"] | undefined;
  chartData: ReturnType<typeof useChartData>["data"];
  symbolOptions: SymbolOption[];
  selectedSymbol: string | null;
  onSymbolChange: (s: string | null) => void;
  visibleRange: VisibleRange | null;
  runId: number | null;
}) {
  return (
    <>
      {summary && (
        <section aria-label="요약 카드" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(4, 1fr)" }}>
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
              href={`/api/backtests/${runId}/export/${kind}`}
              download
              style={dlBtn}
            >
              ⬇ {label}
            </a>
          ))}
        </div>
      </section>

      {/* 종목 선택 + 봉차트 */}
      <section aria-label="봉차트" style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600 }}>봉차트 + 매수/매도 마커</h2>
        <SymbolSelector
          symbols={symbolOptions}
          value={selectedSymbol}
          onChange={onSymbolChange}
        />
        {chartData && chartData.candles.length > 0 ? (
          <CandleTradeChart
            candles={chartData.candles}
            markers={chartData.markers}
            visibleRange={visibleRange}
          />
        ) : (
          <p style={{ fontSize: 12, color: "#6b7280" }}>봉차트 데이터가 없습니다.</p>
        )}
      </section>
    </>
  );
}

function TradesSection({
  trades,
  onRowClick,
}: {
  trades: { items: ReturnType<typeof useBacktestTrades>["data"] extends infer T ? T extends { items: infer U } ? U : never : never; total_count: number } | undefined;
  onRowClick: (info: TradeRowClickInfo) => void;
}) {
  if (!trades || trades.items.length === 0) {
    return <p style={{ fontSize: 13, color: "#6b7280" }}>거래 내역이 없습니다.</p>;
  }
  return (
    <section aria-label="거래 내역">
      <h2 style={{ fontSize: 15, fontWeight: 600 }}>거래 내역</h2>
      <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 4, marginBottom: 8 }}>
        행을 클릭하면 요약 탭의 봉차트가 해당 거래 구간으로 이동합니다.
      </p>
      <TradesTable items={trades.items} onRowClick={onRowClick} />
    </section>
  );
}

function EquitySection({
  chartData,
  equityItems,
}: {
  chartData: ReturnType<typeof useChartData>["data"];
  equityItems: ReturnType<typeof useDailyEquity>["data"] extends infer T ? T extends { items: infer U } ? U : never : never;
}) {
  return (
    <>
      {chartData && chartData.equity_curve.length > 0 && (
        <section aria-label="자산 곡선" style={{ marginTop: 0 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>총자산 곡선</h2>
          <EquityCurveChart equity={chartData.equity_curve} />
        </section>
      )}

      {chartData && chartData.candles.length > 0 && (
        <section aria-label="거래량" style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>거래량</h2>
          <VolumeChart candles={chartData.candles} />
        </section>
      )}

      <section aria-label="벤치마크 비교" style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600 }}>벤치마크 비교 (KOSPI/KOSDAQ)</h2>
        <BenchmarkCompareChart
          equity={chartData?.equity_curve ?? []}
          benchmarks={[]}
        />
      </section>

      {equityItems.length > 0 && (
        <section aria-label="일별 자산" style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>일별 자산 (요약)</h2>
          <pre style={{ fontSize: 12, background: "#f9fafb", padding: 8, borderRadius: 4 }}>
            {`첫 날: ${equityItems[0].date} → ${Math.round(equityItems[0].total_equity).toLocaleString()}원
마지막: ${equityItems.at(-1)!.date} → ${Math.round(equityItems.at(-1)!.total_equity).toLocaleString()}원`}
          </pre>
        </section>
      )}
    </>
  );
}

function MonthlySection({
  equityItems,
}: {
  equityItems: ReturnType<typeof useDailyEquity>["data"] extends infer T ? T extends { items: infer U } ? U : never : never;
}) {
  // 월별 수익률: 각 월 마지막 day의 total_equity를 비교
  const monthly = useMemo(() => {
    if (equityItems.length === 0) return [];
    const sorted = [...equityItems].sort((a, b) => a.date.localeCompare(b.date));
    const byMonth = new Map<string, { last: number; date: string }>();
    for (const item of sorted) {
      const ym = item.date.slice(0, 7); // YYYY-MM
      byMonth.set(ym, { last: item.total_equity, date: item.date });
    }
    const monthsAsc = Array.from(byMonth.entries()).sort(([a], [b]) => a.localeCompare(b));
    let prev: number | null = null;
    return monthsAsc.map(([ym, info]) => {
      const ret = prev === null ? 0 : ((info.last - prev) / prev) * 100;
      prev = info.last;
      return { ym, lastEquity: info.last, returnPct: ret };
    });
  }, [equityItems]);

  if (monthly.length === 0) {
    return <p style={{ fontSize: 13, color: "#6b7280" }}>월별 성과 데이터가 없습니다.</p>;
  }

  return (
    <section aria-label="월별 성과">
      <h2 style={{ fontSize: 15, fontWeight: 600 }}>월별 성과</h2>
      <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse", maxWidth: 600 }}>
        <thead>
          <tr style={{ background: "#f9fafb" }}>
            <th style={th}>월</th>
            <th style={th}>월말 자산</th>
            <th style={th}>월간 수익률</th>
          </tr>
        </thead>
        <tbody>
          {monthly.map((m) => (
            <tr key={m.ym} style={{ borderTop: "1px solid #f3f4f6" }}>
              <td style={td}>{m.ym}</td>
              <td style={tdNum}>{Math.round(m.lastEquity).toLocaleString()}원</td>
              <td
                style={{
                  ...tdNum,
                  color: m.returnPct >= 0 ? "#dc2626" : "#1d4ed8",
                }}
              >
                {m.returnPct >= 0 ? "+" : ""}
                {m.returnPct.toFixed(2)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RiskSection({
  chartData,
  summary,
}: {
  chartData: ReturnType<typeof useChartData>["data"];
  summary: NonNullable<ReturnType<typeof useBacktestSummary>["data"]>["summary"] | undefined;
}) {
  return (
    <>
      {summary && (
        <section aria-label="리스크 지표" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(4, 1fr)" }}>
          <Card label="최대 낙폭 (MDD)" value={`${summary.mdd_pct.toFixed(2)}%`} />
          <Card label="평균 수익 거래" value={`${summary.avg_profit_pct.toFixed(2)}%`} />
          <Card label="평균 손실 거래" value={`-${summary.avg_loss_pct.toFixed(2)}%`} />
          <Card
            label="Profit Factor"
            value={summary.profit_factor === null ? "—" : summary.profit_factor.toFixed(2)}
          />
        </section>
      )}

      {chartData && chartData.equity_curve.length > 0 ? (
        <section aria-label="MDD 그래프" style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>MDD 그래프</h2>
          <DrawdownChart equity={chartData.equity_curve} />
        </section>
      ) : (
        <p style={{ fontSize: 13, color: "#6b7280", marginTop: 16 }}>MDD 데이터가 없습니다.</p>
      )}
    </>
  );
}

function CashSection({
  summary,
  equityItems,
}: {
  summary: NonNullable<ReturnType<typeof useBacktestSummary>["data"]>["summary"] | undefined;
  equityItems: ReturnType<typeof useDailyEquity>["data"] extends infer T ? T extends { items: infer U } ? U : never : never;
}) {
  // 자금 관리 통계 (08번 §13)
  const stats = useMemo(() => {
    if (equityItems.length === 0) return null;
    const cashes = equityItems.map((e) => e.cash);
    const minCash = Math.min(...cashes);
    const avgCash = cashes.reduce((a, b) => a + b, 0) / cashes.length;
    return { minCash, avgCash };
  }, [equityItems]);

  return (
    <>
      {summary && stats && (
        <section aria-label="자금 관리 카드" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(4, 1fr)" }}>
          <Card label="초기 자금" value={`${Math.round(summary.initial_cash).toLocaleString()}원`} />
          <Card label="최종 자산" value={`${Math.round(summary.final_equity).toLocaleString()}원`} />
          <Card label="평균 예수금" value={`${Math.round(stats.avgCash).toLocaleString()}원`} />
          <Card label="최소 예수금" value={`${Math.round(stats.minCash).toLocaleString()}원`} />
        </section>
      )}

      {equityItems.length > 0 && (
        <>
          <section aria-label="예수금 변화" style={{ marginTop: 24 }}>
            <h2 style={{ fontSize: 15, fontWeight: 600 }}>예수금 변화</h2>
            <CashChart daily={equityItems} />
          </section>

          <section aria-label="보유 종목 수" style={{ marginTop: 24 }}>
            <h2 style={{ fontSize: 15, fontWeight: 600 }}>보유 종목 수 변화</h2>
            <PositionsCountChart daily={equityItems} />
          </section>
        </>
      )}

      {equityItems.length === 0 && (
        <p style={{ fontSize: 13, color: "#6b7280", marginTop: 16 }}>자금 관리 데이터가 없습니다.</p>
      )}
    </>
  );
}

// --- 스타일 ---

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

// RESULT_TABS export — 다른 곳에서 라벨 표시용 (필요 시)
export { RESULT_TABS };
