/**
 * 종목 선택 드롭다운 — 08번 §6 / 032 (chart-data symbol query 활용).
 *
 * trades API 응답에서 unique symbol 추출 → symbol ASC 정렬 (결정론) →
 * <select>로 드롭다운 표시. 변경 시 onChange로 부모에 전달.
 *
 * symbols가 1개 이하이면 표시 안 함 (단일 종목 백테스트는 선택 의미 없음).
 */

export type SymbolOption = { symbol: string; name?: string };

export default function SymbolSelector({
  symbols,
  value,
  onChange,
}: {
  symbols: SymbolOption[];
  value: string | null;
  onChange: (symbol: string | null) => void;
}) {
  if (symbols.length <= 1) return null;
  // symbol ASC 정렬 (결정론)
  const sorted = [...symbols].sort((a, b) => a.symbol.localeCompare(b.symbol));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
      <label htmlFor="symbol-select" style={{ fontSize: 12, color: "#374151" }}>
        종목 선택:
      </label>
      <select
        id="symbol-select"
        data-testid="symbol-select"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        style={{
          padding: "4px 8px",
          fontSize: 12,
          border: "1px solid #d1d5db",
          borderRadius: 4,
          background: "white",
        }}
      >
        <option value="">전체 / 첫 종목</option>
        {sorted.map((opt) => (
          <option key={opt.symbol} value={opt.symbol}>
            {opt.name ? `${opt.symbol} (${opt.name})` : opt.symbol}
          </option>
        ))}
      </select>
    </div>
  );
}
