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
 * 보유 종목 수 변화 — 08번 §5.
 *
 * daily_equity의 positions_count 컬럼 (Wave C2). Histogram으로 정수 값 시각화.
 * 정렬: date ASC.
 */
export default function PositionsCountChart({
  daily,
  height = 160,
}: {
  daily: DailyEquityOut[];
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

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
    seriesRef.current = chart.addHistogramSeries({
      color: "#7c3aed",
      priceFormat: { type: "volume" },
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
        value: p.positions_count,
      })),
    );
  }, [daily]);

  return (
    <div
      data-testid="positions-count-chart"
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
