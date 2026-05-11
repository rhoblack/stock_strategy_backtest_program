/**
 * 공통 Input UI 컴포넌트 (11-m)
 *
 * label, error 메시지, type(text/number), onChange 콜백.
 * 사용자 노출 라벨은 모두 한국어.
 */

import type { CSSProperties } from "react";

export interface InputProps {
  label?: string;
  error?: string;
  type?: "text" | "number";
  value: string | number;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  min?: number;
  max?: number;
  step?: number;
  id?: string;
  "data-testid"?: string;
  style?: CSSProperties;
}

const inputBase: CSSProperties = {
  width: "100%",
  padding: "6px 10px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  fontSize: 13,
  fontFamily: "inherit",
  boxSizing: "border-box",
  outline: "none",
  transition: "border-color 0.15s",
};

export default function Input({
  label,
  error,
  type = "text",
  value,
  onChange,
  placeholder,
  disabled = false,
  min,
  max,
  step,
  id,
  "data-testid": testId,
  style,
}: InputProps) {
  const inputStyle: CSSProperties = {
    ...inputBase,
    borderColor: error ? "#dc2626" : "#d1d5db",
    background: disabled ? "#f9fafb" : "#ffffff",
    color: disabled ? "#9ca3af" : "#1f2937",
    cursor: disabled ? "not-allowed" : "text",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, ...style }}>
      {label && (
        <label
          htmlFor={id}
          style={{ fontSize: 12, fontWeight: 500, color: "#374151" }}
        >
          {label}
        </label>
      )}
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        min={min}
        max={max}
        step={step}
        data-testid={testId}
        style={inputStyle}
      />
      {error && (
        <span
          role="alert"
          style={{ fontSize: 11, color: "#dc2626" }}
        >
          {error}
        </span>
      )}
    </div>
  );
}
