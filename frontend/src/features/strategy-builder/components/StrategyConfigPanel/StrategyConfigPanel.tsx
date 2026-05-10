/**
 * 6 비조건 섹션 통합 패널 (탭 방식).
 *
 * 02번 §7~§12 + §17 — position_sizing, cash_management, risk_management,
 * execution, priority, metadata.
 *
 * 통합 패턴: 탭 (각 섹션은 독립적이고 길이가 길어 collapse보다 탭이 적합).
 * 활성화 토글은 각 폼 내부에서 처리 (FormSection enabled).
 *
 * StrategyBuilderPage의 메인 영역에 배치 (캔버스 하단 또는 별도 슬롯).
 */
import { useState } from "react";
import {
  CONFIG_SECTIONS,
  CONFIG_SECTION_LABEL,
  type ConfigSectionKey,
} from "../../state/strategySections";
import { useStrategyDraft } from "../../state/StrategyDraftContext";
import PositionSizingForm from "./PositionSizingForm";
import CashManagementForm from "./CashManagementForm";
import RiskManagementForm from "./RiskManagementForm";
import ExecutionForm from "./ExecutionForm";
import PriorityForm from "./PriorityForm";
import MetadataForm from "./MetadataForm";

const FORMS: Record<ConfigSectionKey, () => JSX.Element> = {
  position_sizing: PositionSizingForm,
  cash_management: CashManagementForm,
  risk_management: RiskManagementForm,
  execution: ExecutionForm,
  priority: PriorityForm,
  metadata: MetadataForm,
};

/** 각 섹션의 활성화 여부 (탭 라벨에 표시). */
function useSectionEnabled(): Record<ConfigSectionKey, boolean> {
  const { draft } = useStrategyDraft();
  return {
    position_sizing: draft.position_sizing.enabled,
    cash_management: draft.cash_management.enabled,
    risk_management: draft.risk_management.enabled,
    execution: draft.execution.enabled,
    priority: draft.priority.enabled,
    metadata: draft.metadata.enabled,
  };
}

export default function StrategyConfigPanel() {
  const [active, setActive] = useState<ConfigSectionKey>("position_sizing");
  const enabled = useSectionEnabled();
  const ActiveForm = FORMS[active];

  return (
    <section
      aria-label="전략 설정 패널"
      style={{
        marginTop: 16,
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        background: "white",
      }}
    >
      <header style={{ borderBottom: "1px solid #e5e7eb", padding: "8px 12px" }}>
        <h2 style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "#111827" }}>
          전략 설정 (자금/실행/우선순위/메타)
        </h2>
        <p style={{ fontSize: 11, color: "#9ca3af", margin: "4px 0 0" }}>
          각 섹션을 활성화해야 백테스트 시 적용됩니다. 비활성 섹션은 백엔드 기본값을 사용합니다.
        </p>
      </header>

      <nav
        role="tablist"
        aria-label="설정 섹션 탭"
        style={{ display: "flex", gap: 4, padding: "8px 8px 0", borderBottom: "1px solid #e5e7eb", flexWrap: "wrap" }}
      >
        {CONFIG_SECTIONS.map((key) => {
          const isActive = key === active;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={`config-panel-${key}`}
              id={`config-tab-${key}`}
              onClick={() => setActive(key)}
              style={{
                fontSize: 12,
                padding: "6px 10px",
                border: "1px solid",
                borderColor: isActive ? "#2563eb" : "#e5e7eb",
                borderBottom: isActive ? "1px solid white" : "1px solid #e5e7eb",
                marginBottom: -1,
                background: isActive ? "white" : "#f9fafb",
                color: isActive ? "#1d4ed8" : "#374151",
                cursor: "pointer",
                borderRadius: "4px 4px 0 0",
                display: "inline-flex",
                gap: 4,
                alignItems: "center",
              }}
            >
              {CONFIG_SECTION_LABEL[key]}
              {enabled[key] && (
                <span
                  aria-label="활성"
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "#16a34a",
                    display: "inline-block",
                  }}
                />
              )}
            </button>
          );
        })}
      </nav>

      <div
        role="tabpanel"
        id={`config-panel-${active}`}
        aria-labelledby={`config-tab-${active}`}
        style={{ padding: 12 }}
      >
        <ActiveForm />
      </div>
    </section>
  );
}
