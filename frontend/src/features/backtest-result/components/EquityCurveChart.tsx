import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { EquityPoint } from "../../../api/chartData";

/**
 * 자산 곡선 (08번 5절). 단순 line series.
 */
export default function EquityCurveChart({
  equity,
  height = 200,
}: {
  equity: EquityPoint[];
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
    seriesRef.current = chart.addLineSeries({ color: "#2563eb", lineWidth: 2 });

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
    series.setData(equity.map((p) => ({ time: p.time as Time, value: p.value })));
  }, [equity]);

  return (
    <div
      data-testid="equity-curve-chart"
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
