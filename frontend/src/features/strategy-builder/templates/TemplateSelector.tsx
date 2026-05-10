/**
 * 전략 템플릿 선택 UI (Wave 12-030, 01-k).
 *
 * - STRATEGY_TEMPLATES 카탈로그를 카테고리별 그룹으로 표시
 * - 선택 시 useConditions()의 ConditionMeta 카탈로그로 lookup하여 완전한
 *   StrategyDraft를 생성하고, draftReducer.APPLY_TEMPLATE로 전체 교체
 * - "현재 작업 중인 전략을 템플릿으로 덮어쓰시겠습니까?" 확인 (window.confirm)
 *
 * Note: confirm() 호출은 빈 전략(empty)에서는 스킵 (덮어쓸 게 없음).
 */
import { useState } from "react";
import { useConditions } from "../../../api/conditions";
import { useStrategyDraft } from "../state/StrategyDraftContext";
import {
  STRATEGY_TEMPLATES,
  buildDraftFromTemplate,
  type StrategyTemplate,
} from "./templates";

type Props = {
  /** 템플릿 적용 후 호출 (예: 모달 닫기) */
  onApplied?: (template: StrategyTemplate) => void;
  /** 빈 전략을 적용 가능한지 여부 (기본 true) */
  showEmpty?: boolean;
};

function isDraftDirty(name: string, hasAnyCondition: boolean): boolean {
  return name.trim().length > 0 || hasAnyCondition;
}

export default function TemplateSelector({ onApplied, showEmpty = true }: Props) {
  const { data: catalog } = useConditions();
  const { draft, dispatch } = useStrategyDraft();
  const [errorTypes, setErrorTypes] = useState<string[] | null>(null);

  const totalConditions =
    draft.sections.entry.conditions.length +
    draft.sections.exit_signal.conditions.length +
    draft.sections.exit_position.conditions.length +
    draft.sections.filters.conditions.length;
  const dirty = isDraftDirty(draft.name, totalConditions > 0);

  const templates = showEmpty ? STRATEGY_TEMPLATES : STRATEGY_TEMPLATES.filter((t) => t.id !== "empty");

  function handleApply(template: StrategyTemplate) {
    if (template.id !== "empty" && dirty) {
      const ok = window.confirm(
        `현재 작업 중인 내용이 "${template.name}" 템플릿으로 교체됩니다. 계속하시겠습니까?`,
      );
      if (!ok) return;
    }
    const metaCatalog = catalog ?? [];
    const newDraft = buildDraftFromTemplate(template, metaCatalog);
    dispatch({ type: "APPLY_TEMPLATE", draft: newDraft });

    // 카탈로그에 없어 스킵된 condition type 경고
    const requested = collectRequestedTypes(template);
    const missing = requested.filter((t) => !metaCatalog.find((m) => m.type === t));
    setErrorTypes(missing.length > 0 ? missing : null);

    onApplied?.(template);
  }

  // 카테고리 그룹화
  const grouped = new Map<string, StrategyTemplate[]>();
  for (const t of templates) {
    if (!grouped.has(t.category)) grouped.set(t.category, []);
    grouped.get(t.category)!.push(t);
  }

  return (
    <section
      aria-label="전략 템플릿"
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        padding: 12,
        background: "white",
      }}
    >
      <header style={{ marginBottom: 8 }}>
        <h3 style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "#111827" }}>
          전략 템플릿
        </h3>
        <p style={{ fontSize: 11, color: "#9ca3af", margin: "4px 0 0" }}>
          템플릿을 선택하면 현재 작업 내용이 모두 교체됩니다.
        </p>
      </header>

      {[...grouped.entries()].map(([category, items]) => (
        <div key={category} style={{ marginTop: 8 }}>
          <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>{category}</div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 4 }}>
            {items.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => handleApply(t)}
                  aria-label={`${t.name} 템플릿 적용`}
                  title={t.description}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 10px",
                    border: "1px solid #e5e7eb",
                    borderRadius: 4,
                    background: "#f9fafb",
                    cursor: "pointer",
                    fontSize: 12,
                  }}
                >
                  <div style={{ fontWeight: 600, color: "#1f2937" }}>{t.name}</div>
                  <div style={{ color: "#6b7280", marginTop: 2, fontSize: 11 }}>
                    {t.description}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {errorTypes && errorTypes.length > 0 && (
        <p
          role="alert"
          style={{
            marginTop: 8,
            fontSize: 11,
            color: "#b45309",
            background: "#fffbeb",
            padding: 6,
            borderRadius: 4,
          }}
        >
          일부 조건이 백엔드 카탈로그에 없어 스킵되었습니다: {errorTypes.join(", ")}
        </p>
      )}
    </section>
  );
}

function collectRequestedTypes(t: StrategyTemplate): string[] {
  const types: string[] = [];
  for (const sec of [t.entry, t.exit_signal, t.exit_position, t.filters]) {
    if (!sec) continue;
    for (const c of sec.conditions ?? []) types.push(c.type);
    for (const g of sec.groups ?? []) for (const c of g.conditions) types.push(c.type);
  }
  return Array.from(new Set(types));
}
