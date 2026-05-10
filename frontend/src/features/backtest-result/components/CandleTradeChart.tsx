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
 *
 * visibleRange (033 / 08-m): 거래 클릭 시 해당 entry_date~exit_date로 차트 줌.
 *   - lightweight-charts timeScale().setVisibleRange({ from, to }) 호출
 *   - exit_date가 없으면 (보유 중) entry_date에서 마지막 봉까지 표시
 */
export type VisibleRange = {
  from: string; // YYYY-MM-DD
  to: string | null; // YYYY-MM-DD or null (보유 중)
};

export default function CandleTradeChart({
  candles,
  markers,
  height = 360,
  visibleRange,
}: {
  candles: CandleBar[];
  markers: ChartMarker[];
  height?: number;
  visibleRange?: VisibleRange | null;
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

  // 033 / 08-m: visibleRange 변경 시 차트 zoom.
  // candles 갱신 직후에 setVisibleRange를 호출해야 함.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || candles.length === 0) return;
    if (!visibleRange) {
      chart.timeScale().fitContent();
      return;
    }
    const lastCandle = candles[candles.length - 1].time;
    const from = visibleRange.from as Time;
    const to = (visibleRange.to ?? lastCandle) as Time;
    try {
      chart.timeScale().setVisibleRange({ from, to });
    } catch {
      // lightweight-charts가 매칭 실패 시 throw하는 케이스 방지 — 무시 후 fitContent.
      chart.timeScale().fitContent();
    }
  }, [candles, visibleRange]);

  return (
    <div
      data-testid="candle-trade-chart"
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
