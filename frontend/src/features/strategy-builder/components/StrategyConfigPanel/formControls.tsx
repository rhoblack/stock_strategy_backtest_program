/**
 * 6 폼 공통 입력 컴포넌트.
 *
 * 빈 문자열("")을 "미입력"으로 취급하는 number 입력은
 * NumberField로 통일하여 직렬화 정책(빈 값 제외)과 일치시킨다.
 */
import type { ChangeEvent } from "react";

const fieldStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(120px, 1fr) minmax(0, 1.4fr)",
  gap: 8,
  alignItems: "center",
  fontSize: 12,
  color: "#374151",
};

const inputStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "4px 6px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  width: "100%",
};

export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  placeholder,
  hint,
  ariaLabel,
}: {
  label: string;
  value: number | "";
  onChange: (v: number | "") => void;
  min?: number;
  max?: number;
  step?: number | "any";
  placeholder?: string;
  hint?: string;
  ariaLabel?: string;
}) {
  const handle = (e: ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    onChange(v === "" ? "" : Number(v));
  };
  return (
    <label style={fieldStyle}>
      <span>{label}</span>
      <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <input
          type="number"
          aria-label={ariaLabel ?? label}
          value={value === "" ? "" : String(value)}
          onChange={handle}
          min={min}
          max={max}
          step={step ?? "any"}
          placeholder={placeholder}
          style={inputStyle}
        />
        {hint && <span style={{ fontSize: 11, color: "#9ca3af" }}>{hint}</span>}
      </span>
    </label>
  );
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  ariaLabel,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  ariaLabel?: string;
}) {
  return (
    <label style={fieldStyle}>
      <span>{label}</span>
      <input
        type="text"
        aria-label={ariaLabel ?? label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={inputStyle}
      />
    </label>
  );
}

export function SelectField<T extends string>({
  label,
  value,
  onChange,
  options,
  ariaLabel,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  ariaLabel?: string;
}) {
  return (
    <label style={fieldStyle}>
      <span>{label}</span>
      <select
        aria-label={ariaLabel ?? label}
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        style={inputStyle}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function CheckboxField({
  label,
  checked,
  onChange,
  ariaLabel,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  ariaLabel?: string;
  hint?: string;
}) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#374151" }}>
      <input
        type="checkbox"
        aria-label={ariaLabel ?? label}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>{label}</span>
      {hint && <span style={{ fontSize: 11, color: "#9ca3af" }}>{hint}</span>}
    </label>
  );
}

export function FormSection({
  title,
  enabled,
  onEnabledChange,
  enabledLabel,
  children,
}: {
  title: string;
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  enabledLabel: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "#111827" }}>{title}</h3>
        <CheckboxField
          label={enabledLabel}
          checked={enabled}
          onChange={onEnabledChange}
          ariaLabel={`${title} 활성화`}
        />
      </header>
      <fieldset
        disabled={!enabled}
        style={{
          border: "1px solid #e5e7eb",
          borderRadius: 6,
          padding: 12,
          opacity: enabled ? 1 : 0.55,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          background: enabled ? "white" : "#f9fafb",
          margin: 0,
        }}
      >
        {children}
      </fieldset>
    </div>
  );
}
