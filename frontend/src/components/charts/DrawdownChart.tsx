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
 * MDD (최대 낙폭) 그래프 — 08번 §5.
 *
 * equity_curve의 drawdown(0~음수)을 area series로 시각화.
 * 빨강 계열로 손실 구간 강조. 입력은 chart-data API의 equity_curve[] 그대로.
 *
 * 정렬 보장: time ASC (decisional/look-ahead 안전).
 */
export default function DrawdownChart({
  equity,
  height = 180,
}: {
  equity: EquityPoint[];
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

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
      rightPriceScale: { borderColor: "#e5e7eb" },
    });
    chartRef.current = chart;
    seriesRef.current = chart.addAreaSeries({
      lineColor: "#dc2626",
      topColor: "rgba(220, 38, 38, 0.4)",
      bottomColor: "rgba(220, 38, 38, 0.05)",
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
    // drawdown은 0 또는 음수. 음수가 깊을수록 손실. ASC 정렬 보장.
    const sorted = [...equity].sort((a, b) => a.time.localeCompare(b.time));
    series.setData(
      sorted.map((p) => ({
        time: p.time as Time,
        value: p.drawdown ?? 0,
      })),
    );
  }, [equity]);

  return (
    <div
      data-testid="drawdown-chart"
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
