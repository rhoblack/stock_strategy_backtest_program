/**
 * 공통 포맷터 (11-g) — 페이지/컴포넌트가 중복 구현하지 않도록 추출.
 *
 * 본 step에서 도입; 향후 점진적으로 사용처 마이그레이션.
 * 한국어 UI / 한국 주식 시장 컨벤션 (원화, YYYY-MM-DD).
 */

/** 정수 원화 (예: 10000000 → "10,000,000원"). NaN/Infinity는 "—". */
export function formatKrw(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${Math.round(value).toLocaleString()}원`;
}

/** 정수 (예: 1234 → "1,234"). */
export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString();
}

/** 퍼센트 (예: 1.8857 → "1.89%"). digits 기본 2. */
export function formatPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

/** 부호 포함 퍼센트 (예: 1.5 → "+1.50%", -2.3 → "-2.30%"). */
export function formatSignedPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

/** ISO 날짜 (YYYY-MM-DD) 그대로 반환. invalid는 "—". */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  // 단순 검증; 추가 변환은 향후 필요 시.
  return value;
}
