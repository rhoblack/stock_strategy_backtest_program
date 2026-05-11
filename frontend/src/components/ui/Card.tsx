/**
 * 공통 Card UI 컴포넌트 (11-m, 11-f 확장)
 *
 * 두 가지 사용 패턴:
 *   1. 컨테이너 카드: title? + children (일반 섹션 래퍼)
 *   2. SummaryCard:  label + value + valueColor (요약 지표 카드)
 *
 * BacktestResultPage 등에서 인라인으로 쓰던 스타일을 이 컴포넌트로 교체.
 *
 * padding: "sm"(8px) | "md"(12px, 기본) | "lg"(20px)
 */

import type { CSSProperties, ReactNode } from "react";

// --- 컨테이너 카드 Props ---
export interface ContainerCardProps {
  title?: string;
  padding?: "sm" | "md" | "lg";
  children: ReactNode;
  style?: CSSProperties;
  "data-testid"?: string;
}

const paddingMap: Record<NonNullable<ContainerCardProps["padding"]>, number> = {
  sm: 8,
  md: 12,
  lg: 20,
};

export function ContainerCard({
  title,
  padding = "md",
  children,
  style,
  "data-testid": testId,
}: ContainerCardProps) {
  return (
    <div
      data-testid={testId}
      style={{
        padding: paddingMap[padding],
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        background: "white",
        ...style,
      }}
    >
      {title && (
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "#1f2937",
            marginBottom: paddingMap[padding] / 2,
          }}
        >
          {title}
        </div>
      )}
      {children}
    </div>
  );
}

// --- 지표 요약 카드 Props (기존 Card.tsx 시그니처 호환) ---
export type SummaryCardProps = {
  label: string;
  value: ReactNode;
  /** 색상 강조 (예: 음수 손실 표시). 미지정 시 기본 텍스트 색. */
  valueColor?: string;
  style?: CSSProperties;
  "data-testid"?: string;
};

export function SummaryCard({ label, value, valueColor, style, "data-testid": testId }: SummaryCardProps) {
  return (
    <div
      data-testid={testId}
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

/**
 * 기본 export: SummaryCard (기존 Card.tsx 호환).
 *
 * 새 코드에서는 ContainerCard / SummaryCard 명명 export를 직접 사용 권장.
 */
export default SummaryCard;
