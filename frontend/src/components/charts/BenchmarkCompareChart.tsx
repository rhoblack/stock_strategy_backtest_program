import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { EquityPoint } from "../../api/chartData";

/**
 * 벤치마크 비교 — 08번 §5 / §11.
 *
 * 전략 자산 곡선(equity)과 벤치마크(KOSPI/KOSDAQ) 시계열을 normalized 100 기준
 * 누적 수익률 비교 line chart로 시각화.
 *
 * 데이터 출처:
 *   - equity: chart-data API의 equity_curve[].value
 *   - benchmark: market_indices API (027). 현재 미구현 → null/[] 전달 시 placeholder 표시.
 *
 * 입력 시계열은 모두 ASC 정렬 후, 각 series의 첫 값을 100으로 정규화.
 */
export type BenchmarkSeries = {
  name: string; // 예: "KOSPI" / "KOSDAQ"
  color?: string;
  points: { time: string; value: number }[];
};

export default function BenchmarkCompareChart({
  equity,
  benchmarks,
  height = 220,
}: {
  equity: EquityPoint[];
  benchmarks: BenchmarkSeries[];
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<ISeriesApi<"Line">[]>([]);

  // 벤치마크 데이터가 하나도 없을 때는 placeholder만 (chart 인스턴스 생성도 안함).
  const hasBenchmark = benchmarks.length > 0 && benchmarks.some((b) => b.points.length > 0);
  const hasEquity = equity.length > 0;
  const showPlaceholder = !hasBenchmark;

  useEffect(() => {
    if (showPlaceholder) return;
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#1f2937",
      },
      grid: {
        vertLines: { color: "#f3f4f6" },
        horzLines: { color: "#f3f4f6" },
      },
      width: containerRef.current.clientWidth,
      height,
      timeScale: { timeVisible: false, secondsVisible: false },
    });
    chartRef.current = chart;
    seriesRefs.current = [];

    const onResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
      chartRef.current = null;
      seriesRefs.current = [];
    };
  }, [height, showPlaceholder]);

  useEffect(() => {
    if (showPlaceholder) return;
    const chart = chartRef.current;
    if (!chart) return;

    // 기존 series 제거 (벤치마크 추가/제거 시 리셋)
    seriesRefs.current.forEach((s) => chart.removeSeries(s));
    seriesRefs.current = [];

    // 전략 자산 곡선
    if (hasEquity) {
      const sorted = [...equity].sort((a, b) => a.time.localeCompare(b.time));
      const base = sorted[0]?.value ?? 1;
      const stratSeries = chart.addLineSeries({
        color: "#2563eb",
        lineWidth: 2,
        title: "전략",
      });
      stratSeries.setData(
        sorted.map((p) => ({
          time: p.time as Time,
          value: base !== 0 ? (p.value / base) * 100 : 100,
        })),
      );
      seriesRefs.current.push(stratSeries);
    }

    // 벤치마크 series — name ASC로 정렬해 결정론 보장
    const sortedBenchmarks = [...benchmarks]
      .filter((b) => b.points.length > 0)
      .sort((a, b) => a.name.localeCompare(b.name));
    const palette = ["#16a34a", "#f59e0b", "#9333ea", "#0891b2"];
    sortedBenchmarks.forEach((bm, idx) => {
      const sorted = [...bm.points].sort((a, b) => a.time.localeCompare(b.time));
      const base = sorted[0]?.value ?? 1;
      const series = chart.addLineSeries({
        color: bm.color ?? palette[idx % palette.length],
        lineWidth: 1,
        title: bm.name,
      });
      series.setData(
        sorted.map((p) => ({
          time: p.time as Time,
          value: base !== 0 ? (p.value / base) * 100 : 100,
        })),
      );
      seriesRefs.current.push(series);
    });
  }, [equity, benchmarks, showPlaceholder, hasEquity]);

  if (showPlaceholder) {
    return (
      <div
        data-testid="benchmark-compare-chart"
        style={{
          width: "100%",
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f9fafb",
          border: "1px dashed #e5e7eb",
          borderRadius: 4,
          color: "#6b7280",
          fontSize: 13,
        }}
      >
        벤치마크 데이터(KOSPI/KOSDAQ) 미연동 — 027 market_indices API 도입 후 표시됩니다.
      </div>
    );
  }

  return (
    <div
      data-testid="benchmark-compare-chart"
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
