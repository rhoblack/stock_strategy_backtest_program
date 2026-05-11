/**
 * 공통 Button UI 컴포넌트 (11-m)
 *
 * variant: primary(파랑) / secondary(회색) / danger(빨강) / ghost(투명)
 * size:    sm / md / lg
 * loading: 로딩 스피너 + 클릭 비활성화
 */

import type { ReactNode } from "react";

export interface ButtonProps {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
  /** HTML button type (기본 "button") */
  type?: "button" | "submit" | "reset";
  /** data-testid 전달용 */
  "data-testid"?: string;
  style?: React.CSSProperties;
  title?: string;
}

const baseStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 6,
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontFamily: "inherit",
  fontWeight: 500,
  lineHeight: 1,
  transition: "background 0.15s, opacity 0.15s",
  userSelect: "none",
  whiteSpace: "nowrap",
};

const variantStyles: Record<NonNullable<ButtonProps["variant"]>, React.CSSProperties> = {
  primary: {
    background: "#2563eb",
    color: "#ffffff",
    border: "1px solid transparent",
  },
  secondary: {
    background: "#ffffff",
    color: "#1f2937",
    border: "1px solid #d1d5db",
  },
  danger: {
    background: "#dc2626",
    color: "#ffffff",
    border: "1px solid transparent",
  },
  ghost: {
    background: "transparent",
    color: "#4b5563",
    border: "1px solid transparent",
  },
};

const sizeStyles: Record<NonNullable<ButtonProps["size"]>, React.CSSProperties> = {
  sm: { padding: "4px 10px", fontSize: 12 },
  md: { padding: "7px 16px", fontSize: 13 },
  lg: { padding: "10px 22px", fontSize: 15 },
};

export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  onClick,
  children,
  type = "button",
  "data-testid": testId,
  style,
  title,
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      type={type}
      disabled={isDisabled}
      onClick={onClick}
      data-testid={testId}
      title={title}
      style={{
        ...baseStyle,
        ...variantStyles[variant],
        ...sizeStyles[size],
        opacity: isDisabled ? 0.5 : 1,
        cursor: isDisabled ? "not-allowed" : "pointer",
        ...style,
      }}
    >
      {loading && (
        <span
          aria-hidden="true"
          style={{
            display: "inline-block",
            width: size === "lg" ? 14 : 12,
            height: size === "lg" ? 14 : 12,
            border: "2px solid currentColor",
            borderTopColor: "transparent",
            borderRadius: "50%",
            animation: "spin 0.7s linear infinite",
          }}
        />
      )}
      {children}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </button>
  );
}
