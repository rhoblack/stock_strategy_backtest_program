/**
 * 02번 §7 — priority 폼.
 *
 * 핵심 설계 원칙 8: 동시 매수 신호는 priority 알고리즘 + symbol_asc tie-breaker 필요.
 * Python dict/set 순서 의존 금지.
 */
import { useStrategyDraft } from "../../state/StrategyDraftContext";
import { PRIORITY_METHODS, TIE_BREAKERS } from "../../state/strategySections";
import { FormSection, SelectField } from "./formControls";

export default function PriorityForm() {
  const { draft, dispatch } = useStrategyDraft();
  const p = draft.priority;
  const isRandom = p.method === "random";

  return (
    <FormSection
      title="동시 신호 우선순위 (priority)"
      enabled={p.enabled}
      enabledLabel="활성화"
      onEnabledChange={(v) => dispatch({ type: "PRIORITY_SET", patch: { enabled: v } })}
    >
      <SelectField
        label="우선순위 방식"
        value={p.method}
        onChange={(v) => dispatch({ type: "PRIORITY_SET", patch: { method: v } })}
        options={PRIORITY_METHODS}
      />
      <SelectField
        label="동률 처리"
        value={p.tie_breaker}
        onChange={(v) => dispatch({ type: "PRIORITY_SET", patch: { tie_breaker: v } })}
        options={TIE_BREAKERS}
      />
      {isRandom && (
        <p
          style={{
            fontSize: 11,
            color: "#d97706",
            margin: 0,
            padding: 6,
            background: "#fffbeb",
            borderRadius: 4,
          }}
        >
          ! random 방식은 메타데이터 섹션에서 random_seed를 입력해야 결정론이 보장됩니다.
        </p>
      )}
    </FormSection>
  );
}
