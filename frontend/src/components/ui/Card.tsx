/**
 * 공통 Card UI (11-f) — 결과 페이지의 카드 박스를 추출.
 *
 * BacktestResultPage 내부에 동일 시그니처 Card가 있어 점진적 교체 대상.
 * 본 step에서는 정의만 노출; 호출부 마이그레이션은 후속.
 */

import type { CSSProperties, ReactNode } from "react";

export type CardProps = {
  label: string;
  value: ReactNode;
  /** 색상 강조 (예: 음수 손실 표시). 미지정 시 기본 텍스트 색. */
  valueColor?: string;
  style?: CSSProperties;
};

export default function Card({ label, value, valueColor, style }: CardProps) {
  return (
    <div
      style={{
        padding: 12,
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        background: "white",
        ...style,
      }}
    >
      <div style={{ fontSize: 11, color: "#6b7280" }}>{label}</div>
      <div
        style={{
          fontSize: 18,
          fontWeight: 600,
          marginTop: 4,
          color: valueColor,
        }}
      >
        {value}
      </div>
    </div>
  );
}
