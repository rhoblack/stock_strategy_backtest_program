/**
 * 02번 §8 — position_sizing 폼.
 */
import { useStrategyDraft } from "../../state/StrategyDraftContext";
import { POSITION_SIZING_METHODS } from "../../state/strategySections";
import { CheckboxField, FormSection, NumberField, SelectField } from "./formControls";

export default function PositionSizingForm() {
  const { draft, dispatch } = useStrategyDraft();
  const ps = draft.position_sizing;

  return (
    <FormSection
      title="자금 배분 (position_sizing)"
      enabled={ps.enabled}
      enabledLabel="활성화"
      onEnabledChange={(v) => dispatch({ type: "POSITION_SIZING_SET", patch: { enabled: v } })}
    >
      <SelectField
        label="배분 방식"
        value={ps.method}
        onChange={(v) => dispatch({ type: "POSITION_SIZING_SET", patch: { method: v } })}
        options={POSITION_SIZING_METHODS}
      />
      {ps.method === "fixed_amount" && (
        <NumberField
          label="종목당 금액 (원)"
          value={ps.amount}
          onChange={(v) => dispatch({ type: "POSITION_SIZING_SET", patch: { amount: v } })}
          min={0}
          hint="0보다 커야 합니다."
        />
      )}
      {ps.method === "fixed_ratio" && (
        <NumberField
          label="총자산 대비 비율"
          value={ps.ratio}
          onChange={(v) => dispatch({ type: "POSITION_SIZING_SET", patch: { ratio: v } })}
          min={0}
          max={1}
          step="any"
          hint="0 < ratio ≤ 1"
        />
      )}
      <NumberField
        label="최대 보유 종목 수"
        value={ps.max_positions}
        onChange={(v) => dispatch({ type: "POSITION_SIZING_SET", patch: { max_positions: v } })}
        min={1}
        step={1}
      />
      <NumberField
        label="1일 신규 진입 종목 수"
        value={ps.max_daily_entries}
        onChange={(v) => dispatch({ type: "POSITION_SIZING_SET", patch: { max_daily_entries: v } })}
        min={0}
        step={1}
      />
      <NumberField
        label="1일 매수 예산 (원)"
        value={ps.daily_buy_budget}
        onChange={(v) => dispatch({ type: "POSITION_SIZING_SET", patch: { daily_buy_budget: v } })}
        min={0}
      />
      <CheckboxField
        label="추가매수 (pyramiding) 허용"
        checked={ps.allow_pyramiding}
        onChange={(v) => dispatch({ type: "POSITION_SIZING_SET", patch: { allow_pyramiding: v } })}
        hint="가중평균 평단가로 갱신 (정확성 정책 13.9)"
      />
    </FormSection>
  );
}
