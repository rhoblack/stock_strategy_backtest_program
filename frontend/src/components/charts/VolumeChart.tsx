import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { CandleBar } from "../../api/chartData";

/**
 * 거래량 차트 — 08번 §6.
 *
 * chart-data 응답의 candles[]에서 volume 추출. 양봉/음봉 색상은 close >= open 기준.
 * 한국 컨벤션: 양봉=빨강(#dc2626) / 음봉=파랑(#1d4ed8).
 *
 * volume이 누락된 봉은 0으로 처리. 정렬: time ASC.
 */
export default function VolumeChart({
  candles,
  height = 140,
}: {
  candles: CandleBar[];
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
    const sorted = [...candles].sort((a, b) => a.time.localeCompare(b.time));
    series.setData(
      sorted.map((c) => ({
        time: c.time as Time,
        value: c.volume ?? 0,
        // 한국 컨벤션: 양봉=빨강 / 음봉=파랑
        color: c.close >= c.open ? "#dc2626" : "#1d4ed8",
      })),
    );
  }, [candles]);

  return (
    <div
      data-testid="volume-chart"
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
