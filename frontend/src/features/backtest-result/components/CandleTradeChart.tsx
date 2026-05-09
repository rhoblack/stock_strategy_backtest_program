import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { CandleBar, ChartMarker } from "../../../api/chartData";

/**
 * 봉차트 + 매수/매도 마커 (설계서 08번 7~8절).
 * 설계 원칙: 마커만, 수익률 라벨 X, 마우스 오버 툴팁은 lightweight-charts 기본.
 */
export default function CandleTradeChart({
  candles,
  markers,
  height = 360,
}: {
  candles: CandleBar[];
  markers: ChartMarker[];
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

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
      crosshair: { mode: CrosshairMode.Magnet },
      timeScale: { timeVisible: false, secondsVisible: false },
    });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: "#dc2626",
      downColor: "#1d4ed8",
      borderUpColor: "#dc2626",
      borderDownColor: "#1d4ed8",
      wickUpColor: "#dc2626",
      wickDownColor: "#1d4ed8",
    });
    seriesRef.current = series;

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
    series.setData(candles.map((c) => ({ ...c, time: c.time as Time })));

    // 마커는 같은 날짜에 BUY와 SELL이 섞이면 안 되니 정렬 필수
    const sorted = [...markers].sort((a, b) => a.time.localeCompare(b.time));
    const sm: SeriesMarker<Time>[] = sorted.map((m) => {
      const isBuy = m.type === "BUY";
      const isPartial = m.type === "PARTIAL_SELL";
      return {
        time: m.time as Time,
        position: isBuy ? "belowBar" : "aboveBar",
        color: isBuy
          ? "#16a34a"
          : isPartial
            ? "#9333ea"
            : m.exit_reason?.includes("stop") || m.exit_reason?.includes("loss")
              ? "#dc2626"
              : "#16a34a",
        shape: isBuy ? "arrowUp" : "arrowDown",
        text: isBuy ? "B" : isPartial ? "P" : "S",
      };
    });
    series.setMarkers(sm);
  }, [candles, markers]);

  return (
    <div
      data-testid="candle-trade-chart"
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
