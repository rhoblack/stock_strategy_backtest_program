/**
 * 공통 Tabs UI 컴포넌트 (11-m)
 *
 * items: { label, value }[] — 한국어 라벨
 * active: 현재 선택된 value
 * onChange: 탭 변경 콜백
 */

import type { CSSProperties } from "react";

export interface TabItem {
  label: string;
  value: string;
}

export interface TabsProps {
  items: TabItem[];
  active: string;
  onChange: (value: string) => void;
  "data-testid"?: string;
  style?: CSSProperties;
}

export default function Tabs({
  items,
  active,
  onChange,
  "data-testid": testId,
  style,
}: TabsProps) {
  return (
    <div
      role="tablist"
      data-testid={testId}
      style={{
        display: "flex",
        borderBottom: "2px solid #e5e7eb",
        gap: 0,
        ...style,
      }}
    >
      {items.map((item) => {
        const isActive = item.value === active;
        return (
          <button
            key={item.value}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(item.value)}
            style={{
              padding: "8px 16px",
              fontSize: 13,
              fontWeight: isActive ? 600 : 400,
              background: "none",
              border: "none",
              borderBottom: isActive ? "2px solid #2563eb" : "2px solid transparent",
              marginBottom: -2,
              color: isActive ? "#2563eb" : "#6b7280",
              cursor: "pointer",
              fontFamily: "inherit",
              transition: "color 0.15s, border-color 0.15s",
              whiteSpace: "nowrap",
            }}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
