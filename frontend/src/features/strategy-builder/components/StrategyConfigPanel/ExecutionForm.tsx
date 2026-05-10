/**
 * 02번 §11 — execution 폼.
 *
 * 정확성 정책 정합:
 *   - 13.6: 거래세 시계열 — 한국 거래세 2022~2025 변동 (0.23% → 0.15%).
 *           단일 float 또는 [{from, rate}] 배열 모두 지원.
 *   - 13.7: use_adjusted_price — 모든 가격 평가/체결에 수정주가 사용 (기본 true).
 *   - tick_rounding: 매수 올림 / 매도 내림 (보수적, 13.4).
 */
import { useStrategyDraft } from "../../state/StrategyDraftContext";
import {
  EXECUTION_PRICE_FIELDS,
  TICK_ROUNDING_MODES,
  type TaxRateBracket,
} from "../../state/strategySections";
import {
  CheckboxField,
  FormSection,
  NumberField,
  SelectField,
} from "./formControls";

export default function ExecutionForm() {
  const { draft, dispatch } = useStrategyDraft();
  const ex = draft.execution;

  return (
    <FormSection
      title="체결/비용 (execution)"
      enabled={ex.enabled}
      enabledLabel="활성화"
      onEnabledChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { enabled: v } })}
    >
      <SelectField
        label="진입 체결가"
        value={ex.entry_price}
        onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { entry_price: v } })}
        options={EXECUTION_PRICE_FIELDS}
      />
      <SelectField
        label="청산 체결가"
        value={ex.exit_price}
        onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { exit_price: v } })}
        options={EXECUTION_PRICE_FIELDS}
      />
      <NumberField
        label="수수료율 (fee_rate)"
        value={ex.fee_rate}
        onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { fee_rate: v } })}
        min={0}
        step="any"
        hint="예: 0.00015 → 0.015%"
      />
      <NumberField
        label="슬리피지 (slippage)"
        value={ex.slippage}
        onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { slippage: v } })}
        min={0}
        step="any"
        hint="예: 0.001 → 0.1%"
      />

      <TaxRateEditor />

      <CheckboxField
        label="수정주가 사용 (use_adjusted_price)"
        checked={ex.use_adjusted_price}
        onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { use_adjusted_price: v } })}
        hint="정확성 정책 13.7 — 권장 true"
      />
      <NumberField
        label="진입 시 갭 한도 (%)"
        value={ex.max_gap_pct_for_entry}
        onChange={(v) =>
          dispatch({ type: "EXECUTION_SET", patch: { max_gap_pct_for_entry: v } })
        }
        min={0}
        step="any"
      />
      <CheckboxField
        label="상한가에도 매수 허용 (allow_buy_limit_up)"
        checked={ex.allow_buy_limit_up}
        onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { allow_buy_limit_up: v } })}
      />
      <CheckboxField
        label="하한가에도 매도 허용 (allow_sell_limit_down)"
        checked={ex.allow_sell_limit_down}
        onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { allow_sell_limit_down: v } })}
      />
      <SelectField
        label="호가 단위 처리 (tick_rounding)"
        value={ex.tick_rounding}
        onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { tick_rounding: v } })}
        options={TICK_ROUNDING_MODES}
      />
    </FormSection>
  );
}

/**
 * 거래세 시계열 GUI (02-k).
 *
 * single 모드: 단일 float (전체 기간 동일 세율).
 * timeseries 모드: [{from, rate}] 배열, from은 ISO 날짜 문자열 (오름차순 권장).
 */
function TaxRateEditor() {
  const { draft, dispatch } = useStrategyDraft();
  const ex = draft.execution;

  return (
    <div
      aria-label="거래세 (tax_rate)"
      style={{
        border: "1px dashed #d1d5db",
        borderRadius: 6,
        padding: 10,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <strong style={{ fontSize: 12, color: "#374151" }}>거래세 (tax_rate)</strong>
        <label style={{ fontSize: 12, color: "#6b7280", display: "flex", gap: 6 }}>
          입력 방식:{" "}
          <select
            aria-label="거래세 입력 방식"
            value={ex.tax_rate_mode}
            onChange={(e) =>
              dispatch({
                type: "EXECUTION_SET",
                patch: { tax_rate_mode: e.target.value as "single" | "timeseries" },
              })
            }
            style={{ fontSize: 12 }}
          >
            <option value="timeseries">시계열 (권장)</option>
            <option value="single">단일 세율</option>
          </select>
        </label>
      </div>

      {ex.tax_rate_mode === "single" ? (
        <NumberField
          label="단일 세율"
          value={ex.tax_rate_single}
          onChange={(v) => dispatch({ type: "EXECUTION_SET", patch: { tax_rate_single: v } })}
          min={0}
          step="any"
          hint="예: 0.0015 → 0.15%"
        />
      ) : (
        <TaxTimeseriesTable rows={ex.tax_rate_timeseries} />
      )}
      <p style={{ fontSize: 11, color: "#9ca3af", margin: 0 }}>
        한국 거래세는 2022~2025년 사이 0.23% → 0.15%로 변동되었습니다 (정확성 정책 13.6).
      </p>
    </div>
  );
}

function TaxTimeseriesTable({ rows }: { rows: TaxRateBracket[] }) {
  const { dispatch } = useStrategyDraft();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <table
        aria-label="거래세 시계열"
        style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}
      >
        <thead>
          <tr style={{ background: "#f3f4f6" }}>
            <th style={{ textAlign: "left", padding: "4px 6px", border: "1px solid #e5e7eb" }}>
              적용 시작일 (YYYY-MM-DD)
            </th>
            <th style={{ textAlign: "left", padding: "4px 6px", border: "1px solid #e5e7eb" }}>
              세율
            </th>
            <th style={{ width: 50, border: "1px solid #e5e7eb" }} />
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={3}
                style={{ padding: 8, color: "#9ca3af", textAlign: "center", border: "1px solid #e5e7eb" }}
              >
                행이 없습니다. 추가 버튼을 눌러주세요.
              </td>
            </tr>
          )}
          {rows.map((row, i) => (
            <tr key={i}>
              <td style={{ padding: 4, border: "1px solid #e5e7eb" }}>
                <input
                  type="date"
                  aria-label={`tax_rate ${i + 1} from`}
                  value={row.from}
                  onChange={(e) =>
                    dispatch({
                      type: "EXECUTION_TAX_UPDATE",
                      index: i,
                      patch: { from: e.target.value },
                    })
                  }
                  style={{ fontSize: 12, width: "100%", border: "none" }}
                />
              </td>
              <td style={{ padding: 4, border: "1px solid #e5e7eb" }}>
                <input
                  type="number"
                  aria-label={`tax_rate ${i + 1} rate`}
                  step="any"
                  min={0}
                  value={row.rate === "" ? "" : String(row.rate)}
                  onChange={(e) =>
                    dispatch({
                      type: "EXECUTION_TAX_UPDATE",
                      index: i,
                      patch: { rate: e.target.value === "" ? "" : Number(e.target.value) },
                    })
                  }
                  style={{ fontSize: 12, width: "100%", border: "none" }}
                />
              </td>
              <td style={{ textAlign: "center", border: "1px solid #e5e7eb" }}>
                <button
                  type="button"
                  aria-label={`tax_rate ${i + 1} 삭제`}
                  onClick={() => dispatch({ type: "EXECUTION_TAX_REMOVE", index: i })}
                  style={{
                    border: "none",
                    background: "transparent",
                    color: "#9ca3af",
                    cursor: "pointer",
                  }}
                >
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={() => dispatch({ type: "EXECUTION_TAX_ADD" })}
        style={{
          alignSelf: "flex-start",
          padding: "4px 10px",
          fontSize: 12,
          border: "1px solid #d1d5db",
          borderRadius: 4,
          background: "white",
          cursor: "pointer",
        }}
      >
        + 거래세 행 추가
      </button>
    </div>
  );
}
