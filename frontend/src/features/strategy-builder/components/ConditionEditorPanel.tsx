import { useStrategyDraft } from "../state/StrategyDraftContext";
import type { ConditionInstance, Section } from "../state/types";
import { SECTION_LABEL } from "../state/types";
import type { ConditionParameter } from "../../../types/condition";
import { renderSentence } from "../utils/renderSentence";

/**
 * 오른쪽 조건 편집 패널.
 * draft.selected → ConditionInstance.parameters로 자동 폼 생성.
 */
export default function ConditionEditorPanel() {
  const { draft, dispatch } = useStrategyDraft();
  const selected = draft.selected;

  let instance: ConditionInstance | null = null;
  let section: Section | null = null;
  if (selected) {
    section = selected.section;
    instance = draft.sections[section].conditions.find(
      (c) => c.instance_id === selected.instance_id,
    ) ?? null;
  }

  return (
    <aside
      aria-label="조건 편집 패널"
      style={{ borderLeft: "1px solid #e5e7eb", padding: 12, overflowY: "auto" }}
    >
      <h2 style={{ fontSize: 14, fontWeight: 600 }}>조건 편집</h2>

      {!instance || !section ? (
        <p style={{ fontSize: 12, color: "#9ca3af" }}>
          조립 영역의 조건 카드를 클릭하면 여기서 파라미터를 수정할 수 있습니다.
        </p>
      ) : (
        <div>
          <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
            {SECTION_LABEL[section]}
          </p>
          <h3 style={{ fontSize: 14, fontWeight: 500, margin: "4px 0 12px" }}>
            {instance.meta.name}
          </h3>
          <p
            data-testid="editor-preview"
            style={{
              fontSize: 12,
              color: "#374151",
              padding: 8,
              background: "#f3f4f6",
              borderRadius: 4,
              marginBottom: 12,
            }}
          >
            {renderSentence(instance)}
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {instance.meta.parameters.map((param) => (
              <ParamInput
                key={param.name}
                param={param}
                value={instance!.values[param.name]}
                onChange={(v) =>
                  dispatch({
                    type: "UPDATE_VALUE",
                    section: section!,
                    instance_id: instance!.instance_id,
                    name: param.name,
                    value: v,
                  })
                }
              />
            ))}
          </div>

          {instance.meta.description && (
            <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 12 }}>
              {instance.meta.description}
            </p>
          )}
        </div>
      )}
    </aside>
  );
}

function ParamInput({
  param,
  value,
  onChange,
}: {
  param: ConditionParameter;
  value: string | number | boolean | undefined;
  onChange: (v: string | number | boolean) => void;
}) {
  const inputId = `param-${param.name}`;

  if (param.input_type === "select") {
    return (
      <label htmlFor={inputId} style={{ fontSize: 12, color: "#374151" }}>
        {param.label}
        <select
          id={inputId}
          value={String(value ?? "")}
          onChange={(e) => {
            // options[].value 타입이 number일 수도 있으므로 매핑
            const opt = param.options?.find((o) => String(o.value) === e.target.value);
            onChange(opt ? opt.value : e.target.value);
          }}
          style={{ marginLeft: 8, fontSize: 12 }}
        >
          {param.options?.map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (param.input_type === "number") {
    return (
      <label htmlFor={inputId} style={{ fontSize: 12, color: "#374151" }}>
        {param.label}
        <input
          id={inputId}
          type="number"
          value={value === undefined || value === null ? "" : String(value)}
          min={param.min}
          max={param.max}
          step={Number.isInteger(param.default) ? 1 : "any"}
          onChange={(e) => {
            const v = e.target.value;
            onChange(v === "" ? "" : Number(v));
          }}
          style={{ marginLeft: 8, fontSize: 12, width: 100 }}
        />
      </label>
    );
  }

  // text or fallback
  return (
    <label htmlFor={inputId} style={{ fontSize: 12, color: "#374151" }}>
      {param.label}
      <input
        id={inputId}
        type="text"
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        style={{ marginLeft: 8, fontSize: 12 }}
      />
    </label>
  );
}
