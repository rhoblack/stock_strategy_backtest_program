/**
 * 02번 §10 — risk_management 폼.
 * MVP는 stop_trading_on_drawdown_pct만 우선 구현 (02번 §10).
 */
import { useStrategyDraft } from "../../state/StrategyDraftContext";
import { FormSection, NumberField } from "./formControls";

export default function RiskManagementForm() {
  const { draft, dispatch } = useStrategyDraft();
  const rm = draft.risk_management;

  return (
    <FormSection
      title="리스크 관리 (risk_management)"
      enabled={rm.enabled}
      enabledLabel="활성화"
      onEnabledChange={(v) => dispatch({ type: "RISK_MGMT_SET", patch: { enabled: v } })}
    >
      <NumberField
        label="MDD 한도 (%)"
        value={rm.stop_trading_on_drawdown_pct}
        onChange={(v) =>
          dispatch({ type: "RISK_MGMT_SET", patch: { stop_trading_on_drawdown_pct: v } })
        }
        min={0}
        max={100}
        step="any"
        hint="누적 MDD가 N% 초과 시 신규 매수 중단 (보유는 유지)"
      />
      <NumberField
        label="종목당 최대 비중"
        value={rm.max_position_ratio}
        onChange={(v) => dispatch({ type: "RISK_MGMT_SET", patch: { max_position_ratio: v } })}
        min={0}
        max={1}
        step="any"
        hint="0 < ratio ≤ 1 (선택)"
      />
      <NumberField
        label="일일 손실 한도 (%)"
        value={rm.max_daily_loss_pct}
        onChange={(v) => dispatch({ type: "RISK_MGMT_SET", patch: { max_daily_loss_pct: v } })}
        min={0}
        max={100}
        step="any"
        hint="당일 손실이 N% 초과 시 추가 매수 중단 (선택)"
      />
    </FormSection>
  );
}
