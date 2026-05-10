/**
 * 02번 §12, §17 — metadata 폼.
 *
 * 정책:
 *   - schema_version: read-only fixed value ("1.0").
 *   - random_seed: 사용자가 명시 입력 시에만 직렬화. 자동 생성 금지.
 *   - tags: chip 추가/제거.
 */
import { useState } from "react";
import { useStrategyDraft } from "../../state/StrategyDraftContext";
import { STRATEGY_SCHEMA_VERSION } from "../../state/strategySections";
import { CheckboxField, FormSection, NumberField } from "./formControls";

export default function MetadataForm() {
  const { draft, dispatch } = useStrategyDraft();
  const m = draft.metadata;
  const [tagInput, setTagInput] = useState("");

  const onAddTag = () => {
    const t = tagInput.trim();
    if (!t) return;
    dispatch({ type: "METADATA_ADD_TAG", tag: t });
    setTagInput("");
  };

  return (
    <FormSection
      title="메타데이터 (metadata)"
      enabled={m.enabled}
      enabledLabel="활성화"
      onEnabledChange={(v) => dispatch({ type: "METADATA_SET", patch: { enabled: v } })}
    >
      <div style={{ fontSize: 12, color: "#6b7280" }}>
        schema_version: <code>{STRATEGY_SCHEMA_VERSION}</code> (고정 — 02번 §17)
      </div>
      <NumberField
        label="random_seed"
        value={m.random_seed}
        onChange={(v) => dispatch({ type: "METADATA_SET", patch: { random_seed: v } })}
        step={1}
        hint="결정론 보장. priority.random 사용 시 필수. 미입력 시 직렬화 제외."
      />
      <CheckboxField
        label="즐겨찾기"
        checked={m.favorite}
        onChange={(v) => dispatch({ type: "METADATA_SET", patch: { favorite: v } })}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span style={{ fontSize: 12, color: "#374151" }}>태그</span>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {m.tags.map((t) => (
            <span
              key={t}
              style={{
                background: "#eef2ff",
                color: "#3730a3",
                padding: "2px 8px",
                borderRadius: 12,
                fontSize: 12,
                display: "inline-flex",
                gap: 6,
                alignItems: "center",
              }}
            >
              {t}
              <button
                type="button"
                aria-label={`태그 ${t} 삭제`}
                onClick={() => dispatch({ type: "METADATA_REMOVE_TAG", tag: t })}
                style={{ border: "none", background: "transparent", cursor: "pointer", color: "#6366f1" }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <input
            type="text"
            aria-label="새 태그"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onAddTag();
              }
            }}
            placeholder="태그 입력 후 Enter"
            style={{
              fontSize: 12,
              padding: "4px 6px",
              border: "1px solid #d1d5db",
              borderRadius: 4,
              flex: 1,
            }}
          />
          <button
            type="button"
            onClick={onAddTag}
            style={{
              fontSize: 12,
              padding: "4px 10px",
              border: "1px solid #d1d5db",
              borderRadius: 4,
              background: "white",
              cursor: "pointer",
            }}
          >
            추가
          </button>
        </div>
      </div>
    </FormSection>
  );
}
