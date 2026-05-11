import { useEffect, useRef, useState, useCallback } from "react";
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
 * 설계 원칙: 마커만, 수익률 라벨 X, 마우스 오버 툴팁은 crosshairMove 이벤트로 커스텀 구현.
 *
 * 툴팁 항목 (08번 §9):
 *   - 날짜, 시가/고가/저가/종가
 *   - 매수/매도 마커 있을 때: 마커 정보 (체결가, 수량, exit_reason)
 *
 * visibleRange (033 / 08-m): 거래 클릭 시 해당 entry_date~exit_date로 차트 줌.
 *   - lightweight-charts timeScale().setVisibleRange({ from, to }) 호출
 *   - exit_date가 없으면 (보유 중) entry_date에서 마지막 봉까지 표시
 */
export type VisibleRange = {
  from: string; // YYYY-MM-DD
  to: string | null; // YYYY-MM-DD or null (보유 중)
};

type TooltipInfo = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  markers: ChartMarker[];
  x: number;
  y: number;
} | null;

/** 마커 exit_reason → 한국어 표시 */
function markerReasonLabel(reason: string | null): string {
  if (!reason) return "—";
  if (reason.includes("take_profit") || reason.includes("profit")) return "익절";
  if (reason.includes("stop_loss") || reason.includes("loss")) return "손절";
  if (reason.includes("time") || reason.includes("expire")) return "시간청산";
  if (reason.includes("partial") || reason.includes("cash")) return "예수금 확보";
  return reason;
}

/** 마커 type → 한국어 표시 */
function markerTypeLabel(type: ChartMarker["type"]): string {
  if (type === "BUY") return "매수";
  if (type === "PARTIAL_SELL") return "일부매도";
  return "매도";
}

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
  const [tooltip, setTooltip] = useState<TooltipInfo>(null);

  // markers를 ref로 유지 — crosshairMove 핸들러 클로저에서 최신 값 참조
  const markersRef = useRef<ChartMarker[]>(markers);
  markersRef.current = markers;

  const candlesRef = useRef<CandleBar[]>(candles);
  candlesRef.current = candles;

  const handleCrosshairMove = useCallback(
    (param: { time?: Time; point?: { x: number; y: number } }) => {
      if (!param.time || !param.point) {
        setTooltip(null);
        return;
      }
      const timeStr = param.time as string;
      const candle = candlesRef.current.find((c) => c.time === timeStr);
      if (!candle) {
        setTooltip(null);
        return;
      }
      const dayMarkers = markersRef.current.filter((m) => m.time === timeStr);
      setTooltip({
        date: timeStr,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        markers: dayMarkers,
        x: param.point.x,
        y: param.point.y,
      });
    },
    [],
  );

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

    // crosshairMove 이벤트 구독 (08번 §9 툴팁)
    chart.subscribeCrosshairMove(handleCrosshairMove);

    const onResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height, handleCrosshairMove]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    series.setData(candles.map((c) => ({ ...c, time: c.time as Time })));

    // 마커는 같은 날짜에 BUY와 SELL이 섞이면 안 되니 정렬 필수
    const sorted = [...markers].sort((a, b) => a.time.localeCompare(b.time));
    const sm: SeriesMarker<Time>[] = sorted.map((m) => {
      const isBuy = m.type === "BUY";
      const isPartial = m.type === "PARTIAL_SELL";
      // 마커 색상: 익절=초록, 손절=빨강, 시간청산=회색, 일부매도=보라 (08번 §8)
      const exitReason = m.exit_reason ?? "";
      let color: string;
      if (isBuy) {
        color = "#16a34a";
      } else if (isPartial) {
        color = "#9333ea"; // 보라
      } else if (exitReason.includes("stop") || exitReason.includes("loss")) {
        color = "#dc2626"; // 손절 — 빨강
      } else if (exitReason.includes("time") || exitReason.includes("expire")) {
        color = "#6b7280"; // 시간청산 — 회색
      } else {
        color = "#16a34a"; // 익절 — 초록
      }
      return {
        time: m.time as Time,
        position: isBuy ? "belowBar" : "aboveBar",
        color,
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
    <div style={{ position: "relative" }}>
      <div
        data-testid="candle-trade-chart"
        ref={containerRef}
        style={{ width: "100%", height }}
      />

      {/* 커스텀 툴팁 (08번 §9) */}
      {tooltip && (
        <div
          role="tooltip"
          data-testid="candle-tooltip"
          style={{
            position: "absolute",
            left: Math.min(tooltip.x + 12, (containerRef.current?.clientWidth ?? 400) - 180),
            top: Math.max(tooltip.y - 10, 0),
            background: "rgba(17,24,39,0.92)",
            color: "white",
            padding: "8px 12px",
            borderRadius: 4,
            fontSize: 12,
            pointerEvents: "none",
            whiteSpace: "nowrap",
            zIndex: 20,
            minWidth: 160,
          }}
        >
          {/* 날짜 */}
          <div style={{ fontWeight: 600, marginBottom: 4, color: "#f3f4f6" }}>
            {tooltip.date}
          </div>
          {/* OHLC */}
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <tbody>
              <tr>
                <td style={{ color: "#9ca3af", paddingRight: 8 }}>시가</td>
                <td style={{ textAlign: "right" }}>{tooltip.open.toLocaleString()}</td>
                <td style={{ color: "#9ca3af", paddingLeft: 12, paddingRight: 8 }}>고가</td>
                <td style={{ textAlign: "right", color: "#fca5a5" }}>{tooltip.high.toLocaleString()}</td>
              </tr>
              <tr>
                <td style={{ color: "#9ca3af", paddingRight: 8 }}>저가</td>
                <td style={{ textAlign: "right", color: "#93c5fd" }}>{tooltip.low.toLocaleString()}</td>
                <td style={{ color: "#9ca3af", paddingLeft: 12, paddingRight: 8 }}>종가</td>
                <td style={{ textAlign: "right" }}>{tooltip.close.toLocaleString()}</td>
              </tr>
            </tbody>
          </table>
          {/* 마커 정보 */}
          {tooltip.markers.length > 0 && (
            <div style={{ marginTop: 6, borderTop: "1px solid rgba(255,255,255,0.15)", paddingTop: 5 }}>
              {tooltip.markers.map((m, i) => (
                <div key={i} style={{ marginTop: i > 0 ? 4 : 0 }}>
                  <span
                    style={{
                      fontWeight: 600,
                      color:
                        m.type === "BUY"
                          ? "#4ade80"
                          : m.type === "PARTIAL_SELL"
                            ? "#c084fc"
                            : (m.exit_reason ?? "").includes("stop") || (m.exit_reason ?? "").includes("loss")
                              ? "#f87171"
                              : "#4ade80",
                    }}
                  >
                    {markerTypeLabel(m.type)}
                  </span>
                  {" "}
                  <span style={{ color: "#d1d5db" }}>
                    {m.price.toLocaleString()}원 × {m.quantity}주
                  </span>
                  {m.exit_reason && (
                    <span style={{ color: "#9ca3af", marginLeft: 6 }}>
                      ({markerReasonLabel(m.exit_reason)})
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
