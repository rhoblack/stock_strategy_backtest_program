/**
 * BacktestResultPage 탭 컨테이너 — 08번 §4 (단순 state 기반).
 *
 * TanStack Table 미도입(033 영역) → 외부 의존성 없는 button 기반 탭.
 * 탭 키 / 라벨 ASC가 아닌 설계서 §3·§4 순서를 따름:
 *   요약 / 거래 / 자산 / 월별 성과 / 리스크 / 자금 관리
 */

export type ResultTabKey =
  | "summary"
  | "trades"
  | "equity"
  | "monthly"
  | "risk"
  | "cash";

export const RESULT_TABS: { key: ResultTabKey; label: string }[] = [
  { key: "summary", label: "요약" },
  { key: "trades", label: "거래" },
  { key: "equity", label: "자산" },
  { key: "monthly", label: "월별 성과" },
  { key: "risk", label: "리스크" },
  { key: "cash", label: "자금 관리" },
];

export default function ResultTabs({
  active,
  onChange,
}: {
  active: ResultTabKey;
  onChange: (key: ResultTabKey) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="백테스트 결과 탭"
      style={{
        display: "flex",
        gap: 4,
        borderBottom: "1px solid #e5e7eb",
        marginTop: 16,
        marginBottom: 16,
      }}
    >
      {RESULT_TABS.map((t) => {
        const selected = t.key === active;
        return (
          <button
            key={t.key}
            role="tab"
            aria-selected={selected}
            data-testid={`tab-${t.key}`}
            onClick={() => onChange(t.key)}
            style={{
              padding: "8px 16px",
              fontSize: 13,
              fontWeight: selected ? 600 : 400,
              color: selected ? "#1d4ed8" : "#374151",
              background: "none",
              border: "none",
              borderBottom: selected ? "2px solid #1d4ed8" : "2px solid transparent",
              cursor: "pointer",
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
