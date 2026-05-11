/**
 * 월별 수익률 막대 차트 (08번 §4 월별 성과 탭).
 *
 * 설계 원칙 (08번 §7):
 *   - 양수 수익률 = 초록(#16a34a), 음수 = 빨강(#dc2626)
 *   - 수익률 숫자는 막대 위/아래에만 표시 (봉차트 위 매봉 표시 금지 원칙과 무관)
 *   - 마우스 오버 툴팁: 월, 수익률(%), 월말 자산
 *
 * 구현: 외부 차트 라이브러리 미설치 → SVG 기반 인라인 렌더.
 * ECharts/Recharts 도입 시 이 컴포넌트만 교체하면 됨.
 *
 * 입력 타입: MonthlyReturn[]
 */

import { useState } from "react";

export type MonthlyReturn = {
  ym: string;        // "YYYY-MM"
  returnPct: number; // 월간 수익률 (%)
  lastEquity: number; // 월말 자산 (원)
};

type TooltipState = {
  x: number;
  y: number;
  data: MonthlyReturn;
} | null;

const BAR_WIDTH = 28;
const BAR_GAP = 6;
const CHART_HEIGHT = 220;
const PADDING_TOP = 20;
const PADDING_BOTTOM = 40;
const PADDING_LEFT = 60;
const PADDING_RIGHT = 20;

export default function MonthlyReturnChart({
  data,
}: {
  data: MonthlyReturn[];
}) {
  const [tooltip, setTooltip] = useState<TooltipState>(null);

  if (data.length === 0) {
    return (
      <p
        data-testid="monthly-return-chart-empty"
        style={{ fontSize: 13, color: "#6b7280" }}
      >
        월별 성과 데이터가 없습니다.
      </p>
    );
  }

  const values = data.map((d) => d.returnPct);
  const maxAbs = Math.max(Math.abs(Math.min(...values)), Math.abs(Math.max(...values)), 1);

  const plotHeight = CHART_HEIGHT - PADDING_TOP - PADDING_BOTTOM;
  const zeroY = PADDING_TOP + (plotHeight / 2); // 중앙이 0
  const scale = (plotHeight / 2) / maxAbs; // px per %

  const totalWidth = PADDING_LEFT + data.length * (BAR_WIDTH + BAR_GAP) - BAR_GAP + PADDING_RIGHT;

  return (
    <div
      data-testid="monthly-return-chart"
      style={{ position: "relative", overflowX: "auto" }}
    >
      <svg
        width={totalWidth}
        height={CHART_HEIGHT}
        style={{ display: "block" }}
      >
        {/* 0선 */}
        <line
          x1={PADDING_LEFT}
          y1={zeroY}
          x2={totalWidth - PADDING_RIGHT}
          y2={zeroY}
          stroke="#d1d5db"
          strokeWidth={1}
        />

        {/* Y축 레이블 */}
        {[-maxAbs, -maxAbs / 2, 0, maxAbs / 2, maxAbs].map((v, i) => {
          const y = zeroY - v * scale;
          return (
            <g key={i}>
              <line
                x1={PADDING_LEFT - 4}
                y1={y}
                x2={PADDING_LEFT}
                y2={y}
                stroke="#9ca3af"
                strokeWidth={1}
              />
              <text
                x={PADDING_LEFT - 6}
                y={y + 4}
                textAnchor="end"
                fontSize={10}
                fill="#6b7280"
              >
                {v >= 0 ? "+" : ""}
                {v.toFixed(1)}%
              </text>
            </g>
          );
        })}

        {/* 막대 */}
        {data.map((d, i) => {
          const x = PADDING_LEFT + i * (BAR_WIDTH + BAR_GAP);
          const isPositive = d.returnPct >= 0;
          const barH = Math.abs(d.returnPct) * scale;
          const barY = isPositive ? zeroY - barH : zeroY;
          const color = isPositive ? "#16a34a" : "#dc2626";

          // 수익률 라벨 위치
          const labelY = isPositive ? barY - 3 : barY + barH + 12;

          return (
            <g
              key={d.ym}
              onMouseEnter={() => {
                setTooltip({
                  x: x + BAR_WIDTH / 2,
                  y: isPositive ? barY : barY + barH,
                  data: d,
                });
              }}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: "pointer" }}
            >
              <rect
                x={x}
                y={barY}
                width={BAR_WIDTH}
                height={Math.max(barH, 1)}
                fill={color}
                opacity={0.85}
                rx={2}
              />
              {/* 수익률 라벨 */}
              <text
                x={x + BAR_WIDTH / 2}
                y={labelY}
                textAnchor="middle"
                fontSize={9}
                fill={color}
                fontWeight={500}
              >
                {d.returnPct >= 0 ? "+" : ""}
                {d.returnPct.toFixed(1)}%
              </text>
              {/* X축 월 라벨 */}
              <text
                x={x + BAR_WIDTH / 2}
                y={CHART_HEIGHT - 6}
                textAnchor="middle"
                fontSize={9}
                fill="#6b7280"
                transform={`rotate(-45 ${x + BAR_WIDTH / 2} ${CHART_HEIGHT - 6})`}
              >
                {d.ym.slice(5)} {/* MM 부분만 */}
              </text>
              {/* 연도 변경 시 연도 표시 */}
              {(i === 0 || d.ym.slice(0, 4) !== data[i - 1].ym.slice(0, 4)) && (
                <text
                  x={x + BAR_WIDTH / 2}
                  y={CHART_HEIGHT - 22}
                  textAnchor="middle"
                  fontSize={9}
                  fill="#374151"
                  fontWeight={600}
                >
                  {d.ym.slice(0, 4)}
                </text>
              )}
            </g>
          );
        })}

        {/* Y축 선 */}
        <line
          x1={PADDING_LEFT}
          y1={PADDING_TOP}
          x2={PADDING_LEFT}
          y2={CHART_HEIGHT - PADDING_BOTTOM}
          stroke="#d1d5db"
          strokeWidth={1}
        />
      </svg>

      {/* 툴팁 */}
      {tooltip && (
        <div
          role="tooltip"
          style={{
            position: "absolute",
            left: tooltip.x + PADDING_LEFT,
            top: Math.max(tooltip.y - 60, 0),
            background: "rgba(17,24,39,0.92)",
            color: "white",
            padding: "6px 10px",
            borderRadius: 4,
            fontSize: 12,
            pointerEvents: "none",
            whiteSpace: "nowrap",
            zIndex: 10,
            transform: "translateX(-50%)",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 2 }}>{tooltip.data.ym}</div>
          <div>
            월간 수익률:{" "}
            <span
              style={{
                color: tooltip.data.returnPct >= 0 ? "#4ade80" : "#f87171",
                fontWeight: 600,
              }}
            >
              {tooltip.data.returnPct >= 0 ? "+" : ""}
              {tooltip.data.returnPct.toFixed(2)}%
            </span>
          </div>
          <div>월말 자산: {Math.round(tooltip.data.lastEquity).toLocaleString()}원</div>
        </div>
      )}
    </div>
  );
}
