/**
 * UniverseSelector UI (11-h / 033) — 019 백엔드 UniverseSelector config 입력 폼.
 *
 * 책임:
 *   - 시장 선택 (KOSPI / KOSDAQ)
 *   - 06번 §8 공통 필터 토글 (exclude_etf / etn / spac / preferred / managed / halted)
 *   - min_market_cap (원), min_avg_trading_value (원), avg_trading_value_window_days
 *   - selection_method (ALL / MARKET_CAP_TOP_N / LIQUIDITY_TOP_N) + top_n / window_days
 *   - 직접 종목 입력 fallback (universe preview API 미구현 시 사용)
 *
 * 본 step에서 universe preview API는 미구현 — placeholder 메시지로 표시.
 *
 * 출력: onChange로 백엔드 전달용 universe_config dict 전달
 *   (BacktestRunPage가 universe_config로 BacktestCreatePayload에 포함).
 *
 * 019 config schema 참조: backend/app/market_data/universe.py
 *   - DEFAULT_EXCLUDE_FLAGS / SUPPORTED_SELECTION_METHODS
 */

import { useEffect, useMemo, useState } from "react";

export type UniverseConfig = {
  market: "KOSPI" | "KOSDAQ";
  exclude_etf: boolean;
  exclude_etn: boolean;
  exclude_spac: boolean;
  exclude_preferred: boolean;
  exclude_managed: boolean;
  exclude_halted: boolean;
  min_market_cap: number | null;
  min_avg_trading_value: number | null;
  avg_trading_value_window_days: number;
  selection_method: "ALL" | "MARKET_CAP_TOP_N" | "LIQUIDITY_TOP_N" | "MANUAL";
  top_n: number | null;
  /** MANUAL fallback — 사용자가 직접 입력한 종목 코드 리스트 (쉼표 구분 입력). */
  symbols: string[] | null;
};

export const DEFAULT_UNIVERSE_CONFIG: UniverseConfig = {
  market: "KOSPI",
  exclude_etf: true,
  exclude_etn: true,
  exclude_spac: true,
  exclude_preferred: true,
  exclude_managed: true,
  exclude_halted: true,
  min_market_cap: null,
  min_avg_trading_value: null,
  avg_trading_value_window_days: 20,
  selection_method: "ALL",
  top_n: 100,
  symbols: null,
};

const EXCLUDE_FLAGS: { key: keyof UniverseConfig; label: string }[] = [
  { key: "exclude_etf", label: "ETF 제외" },
  { key: "exclude_etn", label: "ETN 제외" },
  { key: "exclude_spac", label: "SPAC 제외" },
  { key: "exclude_preferred", label: "우선주 제외" },
  { key: "exclude_managed", label: "관리종목 제외" },
  { key: "exclude_halted", label: "거래정지 제외" },
];

const SELECTION_METHODS: {
  value: UniverseConfig["selection_method"];
  label: string;
  needsTopN: boolean;
}[] = [
  { value: "ALL", label: "전체 (필터 통과 종목 모두)", needsTopN: false },
  { value: "MARKET_CAP_TOP_N", label: "시가총액 상위 N", needsTopN: true },
  { value: "LIQUIDITY_TOP_N", label: "거래대금 상위 N", needsTopN: true },
  { value: "MANUAL", label: "직접 종목 입력 (fallback)", needsTopN: false },
];

export default function UniverseSelector({
  value,
  onChange,
}: {
  value: UniverseConfig;
  onChange: (next: UniverseConfig) => void;
}) {
  // MANUAL 입력 textarea state (쉼표 구분 → 배열 변환)
  const [symbolsText, setSymbolsText] = useState<string>(
    value.symbols ? value.symbols.join(", ") : "",
  );

  useEffect(() => {
    if (value.selection_method !== "MANUAL") return;
    const parsed = symbolsText
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    if (
      JSON.stringify(parsed) !== JSON.stringify(value.symbols ?? [])
    ) {
      onChange({ ...value, symbols: parsed.length > 0 ? parsed : null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbolsText, value.selection_method]);

  const currentMethod = useMemo(
    () =>
      SELECTION_METHODS.find((m) => m.value === value.selection_method) ??
      SELECTION_METHODS[0],
    [value.selection_method],
  );

  const update = <K extends keyof UniverseConfig>(
    key: K,
    next: UniverseConfig[K],
  ) => {
    onChange({ ...value, [key]: next });
  };

  return (
    <fieldset
      data-testid="universe-selector"
      style={{
        border: "1px solid #e5e7eb",
        padding: 12,
        borderRadius: 6,
        display: "grid",
        gap: 12,
      }}
    >
      <legend style={{ fontSize: 13, color: "#374151", fontWeight: 600 }}>
        유니버스 (대상 종목) 설정
      </legend>

      {/* 시장 */}
      <label style={fieldStyle}>
        <span style={labelStyle}>시장</span>
        <select
          aria-label="시장 선택"
          data-testid="universe-market"
          value={value.market}
          onChange={(e) => update("market", e.target.value as UniverseConfig["market"])}
        >
          <option value="KOSPI">코스피 (KOSPI)</option>
          <option value="KOSDAQ">코스닥 (KOSDAQ)</option>
        </select>
      </label>

      {/* 공통 필터 */}
      <div>
        <div style={{ ...labelStyle, marginBottom: 6 }}>공통 필터</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4 }}>
          {EXCLUDE_FLAGS.map((f) => (
            <label
              key={f.key}
              style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}
            >
              <input
                type="checkbox"
                data-testid={`universe-${f.key}`}
                checked={Boolean(value[f.key])}
                onChange={(e) =>
                  update(f.key, e.target.checked as UniverseConfig[typeof f.key])
                }
              />
              {f.label}
            </label>
          ))}
        </div>
      </div>

      {/* 시가총액 / 거래대금 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <label style={fieldStyle}>
          <span style={labelStyle}>최소 시가총액 (원)</span>
          <input
            type="number"
            data-testid="universe-min-market-cap"
            min={0}
            value={value.min_market_cap ?? ""}
            placeholder="예: 100000000000"
            onChange={(e) =>
              update("min_market_cap", e.target.value === "" ? null : Number(e.target.value))
            }
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>최소 거래대금 평균 (원)</span>
          <input
            type="number"
            data-testid="universe-min-avg-trading-value"
            min={0}
            value={value.min_avg_trading_value ?? ""}
            placeholder="예: 1000000000"
            onChange={(e) =>
              update(
                "min_avg_trading_value",
                e.target.value === "" ? null : Number(e.target.value),
              )
            }
          />
        </label>
      </div>

      <label style={fieldStyle}>
        <span style={labelStyle}>거래대금 평균 산출 기간 (일)</span>
        <input
          type="number"
          data-testid="universe-avg-window-days"
          min={1}
          max={120}
          value={value.avg_trading_value_window_days}
          onChange={(e) =>
            update("avg_trading_value_window_days", Math.max(1, Number(e.target.value)))
          }
        />
      </label>

      {/* selection_method */}
      <label style={fieldStyle}>
        <span style={labelStyle}>선정 방식 (selection_method)</span>
        <select
          data-testid="universe-selection-method"
          value={value.selection_method}
          onChange={(e) =>
            update(
              "selection_method",
              e.target.value as UniverseConfig["selection_method"],
            )
          }
        >
          {SELECTION_METHODS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      {currentMethod.needsTopN && (
        <label style={fieldStyle}>
          <span style={labelStyle}>상위 N 종목</span>
          <input
            type="number"
            data-testid="universe-top-n"
            min={1}
            max={3000}
            value={value.top_n ?? 100}
            onChange={(e) => update("top_n", Math.max(1, Number(e.target.value)))}
          />
        </label>
      )}

      {value.selection_method === "MANUAL" && (
        <label style={fieldStyle}>
          <span style={labelStyle}>종목 코드 (쉼표 구분)</span>
          <textarea
            data-testid="universe-manual-symbols"
            rows={3}
            placeholder="예: 005930, 035720, 000660"
            value={symbolsText}
            onChange={(e) => setSymbolsText(e.target.value)}
            style={{ fontFamily: "monospace", fontSize: 12 }}
          />
        </label>
      )}

      {/* preview placeholder — universe preview API 미구현 */}
      <div
        data-testid="universe-preview-placeholder"
        style={{
          padding: 8,
          background: "#f9fafb",
          border: "1px dashed #d1d5db",
          borderRadius: 4,
          fontSize: 12,
          color: "#6b7280",
        }}
      >
        ※ 유니버스 미리보기 API는 후속 step에서 추가됩니다. 현재는 백엔드
        UniverseSelector(019)가 백테스트 실행 시 직접 종목을 선정합니다.
      </div>
    </fieldset>
  );
}

const fieldStyle: React.CSSProperties = {
  display: "grid",
  gap: 4,
  fontSize: 13,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#374151",
};
