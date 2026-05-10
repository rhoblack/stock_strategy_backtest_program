/**
 * 02번 §9 — cash_management 폼.
 *
 * 매매 차별화 핵심: 예수금 부족 시 보유 종목 일부 매도 규칙 (CLAUDE.md "차별화 포인트").
 */
import { useStrategyDraft } from "../../state/StrategyDraftContext";
import { CASH_TARGET_METHODS, CASH_TRIGGER_TYPES } from "../../state/strategySections";
import { CheckboxField, FormSection, NumberField, SelectField } from "./formControls";

export default function CashManagementForm() {
  const { draft, dispatch } = useStrategyDraft();
  const cm = draft.cash_management;

  return (
    <FormSection
      title="예수금 관리 (cash_management)"
      enabled={cm.enabled}
      enabledLabel="활성화"
      onEnabledChange={(v) => dispatch({ type: "CASH_MGMT_SET", patch: { enabled: v } })}
    >
      <SelectField
        label="부족 판단"
        value={cm.trigger_type}
        onChange={(v) => dispatch({ type: "CASH_MGMT_SET", patch: { trigger_type: v } })}
        options={CASH_TRIGGER_TYPES}
      />
      {cm.trigger_type === "cash_below_threshold" && (
        <NumberField
          label="기준 금액 (원)"
          value={cm.trigger_threshold}
          onChange={(v) => dispatch({ type: "CASH_MGMT_SET", patch: { trigger_threshold: v } })}
          min={0}
        />
      )}
      <NumberField
        label="회당 매도 비율"
        value={cm.sell_fraction}
        onChange={(v) => dispatch({ type: "CASH_MGMT_SET", patch: { sell_fraction: v } })}
        min={0}
        max={1}
        step="any"
        hint="0 < x ≤ 1 (예: 0.25 → 평가금액 25%씩 매도)"
      />
      <SelectField
        label="대상 선정 방식"
        value={cm.target_method}
        onChange={(v) => dispatch({ type: "CASH_MGMT_SET", patch: { target_method: v } })}
        options={CASH_TARGET_METHODS}
      />
      <CheckboxField
        label="예수금이 충분해질 때까지 반복"
        checked={cm.repeat_until_cash_sufficient}
        onChange={(v) =>
          dispatch({ type: "CASH_MGMT_SET", patch: { repeat_until_cash_sufficient: v } })
        }
      />
    </FormSection>
  );
}
