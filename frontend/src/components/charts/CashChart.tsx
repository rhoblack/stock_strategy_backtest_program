import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { DailyEquityOut } from "../../api/backtests";

/**
 * 예수금 변화 그래프 — 08번 §5 / §13.
 *
 * daily_equity 응답의 cash 컬럼을 line series로. 자금 관리 탭의 핵심 시각화.
 * 입력: daily-equity API 응답의 items[]. (chart-data가 아니라 daily-equity 사용 — Wave C2)
 *
 * 정렬: date ASC.
 */
export default function CashChart({
  daily,
  height = 180,
}: {
  daily: DailyEquityOut[];
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
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
    seriesRef.current = chart.addLineSeries({
      color: "#0891b2",
      lineWidth: 2,
    });

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
      seriesRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const sorted = [...daily].sort((a, b) => a.date.localeCompare(b.date));
    series.setData(
      sorted.map((p) => ({
        time: p.date as Time,
        value: p.cash,
      })),
    );
  }, [daily]);

  return (
    <div
      data-testid="cash-chart"
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
