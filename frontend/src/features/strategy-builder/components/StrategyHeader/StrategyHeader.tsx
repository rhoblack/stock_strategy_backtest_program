/**
 * 전략 빌더 상단 헤더 (Wave 12-030, 01-j + 01-k 부분).
 *
 * 구성:
 *   - 좌측: 전략 목록 링크 + 전략 이름 입력
 *   - 우측: 모드 토글 (초보자/전문가) + 템플릿 + 복사 + JSON 보기 + 백테스트 실행
 *
 * 버튼 동작:
 *   - 복사: savedStrategyId가 있으면 POST /api/strategies/{id}/duplicate (new_name=현재 이름 + " (복사)")
 *           savedStrategyId가 없으면 disabled (먼저 저장해야 함)
 *   - JSON 보기: serializeDraft(draft)를 modal에서 read-only로 표시 + clipboard 복사
 *   - 백테스트 실행: 저장 후(or 이미 저장된 경우) /backtests/new?strategy_id={id} 이동
 *   - 템플릿: TemplateSelector를 모달에서 표시
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { serializeDraft } from "../../utils/serializeDraft";
import { useStrategyDraft } from "../../state/StrategyDraftContext";
import { useBuilderMode } from "../../state/useBuilderMode";
import {
  useCreateStrategy,
  useDuplicateStrategy,
} from "../../../../api/strategies";
import TemplateSelector from "../../templates/TemplateSelector";
import type { StrategyTemplate } from "../../templates/templates";

type Props = {
  /** 이미 저장된 전략 id (목록에서 진입 시). 새 전략이면 null */
  savedStrategyId?: number | null;
  /** "전략 저장" 가능 여부 (이름 + 검증 통과) */
  canSave: boolean;
  /** 저장 액션 (이름이 비었거나 검증 실패면 호출 안 됨) */
  onSave: () => Promise<number | null> | number | null;
  /** 저장 진행 중 표시 */
  isSaving?: boolean;
  /** 저장 실패 메시지 (있으면 노출) */
  saveErrorMessage?: string | null;
};

export default function StrategyHeader({
  savedStrategyId,
  canSave,
  onSave,
  isSaving,
  saveErrorMessage,
}: Props) {
  const { draft, dispatch } = useStrategyDraft();
  const navigate = useNavigate();
  const { mode, setMode } = useBuilderMode();
  const duplicateMutation = useDuplicateStrategy();
  // useCreateStrategy를 헤더에서 직접 호출하지 않음 — onSave를 부모 페이지가 제공
  // (단, 헤더에서 백테스트 실행 시 저장 흐름을 위해 isPending 상태는 부모에서 받음)
  void useCreateStrategy; // type import 회피

  const [showJson, setShowJson] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  // === 복사 ===
  const canDuplicate = savedStrategyId != null && !duplicateMutation.isPending;
  const onDuplicate = () => {
    if (!canDuplicate || savedStrategyId == null) return;
    const newName = `${draft.name || "전략"} (복사)`;
    duplicateMutation.mutate(
      { strategyId: savedStrategyId, newName },
      {
        onSuccess: (created) => {
          navigate(`/strategies/${created.id}`);
        },
      },
    );
  };

  // === JSON 보기 ===
  const serialized = serializeDraft(draft);
  const jsonText = JSON.stringify(serialized, null, 2);
  const onCopyJson = async () => {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(jsonText);
        setCopyMessage("클립보드에 복사되었습니다");
      } else {
        setCopyMessage("클립보드 API를 사용할 수 없습니다");
      }
    } catch {
      setCopyMessage("복사 실패");
    }
    setTimeout(() => setCopyMessage(null), 2000);
  };

  // === 백테스트 실행 ===
  const [runError, setRunError] = useState<string | null>(null);
  const onRunBacktest = async () => {
    setRunError(null);
    let id = savedStrategyId ?? null;
    if (id == null) {
      if (!canSave) {
        setRunError("백테스트 실행 전에 전략 이름과 조건을 입력하세요");
        return;
      }
      const created = await onSave();
      if (created == null) {
        setRunError("저장에 실패했습니다");
        return;
      }
      id = created;
    }
    navigate(`/backtests/new?strategy_id=${id}`);
  };

  return (
    <header
      aria-label="전략 빌더 헤더"
      style={{
        padding: "12px 16px",
        borderBottom: "1px solid #e5e7eb",
        display: "flex",
        alignItems: "center",
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <Link
        to="/strategies"
        style={{ fontSize: 14, color: "#6b7280", textDecoration: "none" }}
      >
        ← 전략 목록
      </Link>
      <input
        aria-label="전략 이름"
        placeholder="전략 이름 입력"
        value={draft.name}
        onChange={(e) => dispatch({ type: "SET_NAME", name: e.target.value })}
        style={{
          fontSize: 14,
          padding: "4px 8px",
          border: "1px solid #d1d5db",
          borderRadius: 4,
          minWidth: 200,
        }}
      />

      {/* 모드 토글 */}
      <div
        role="radiogroup"
        aria-label="빌더 모드"
        style={{ display: "inline-flex", border: "1px solid #d1d5db", borderRadius: 4, overflow: "hidden" }}
      >
        <button
          type="button"
          role="radio"
          aria-checked={mode === "beginner"}
          aria-label="초보자 모드"
          onClick={() => setMode("beginner")}
          style={modeButtonStyle(mode === "beginner")}
        >
          초보자
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={mode === "expert"}
          aria-label="전문가 모드"
          onClick={() => setMode("expert")}
          style={modeButtonStyle(mode === "expert")}
        >
          전문가
        </button>
      </div>

      <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
        <button
          type="button"
          onClick={() => setShowTemplates(true)}
          aria-label="템플릿 선택"
          style={secondaryButtonStyle}
        >
          템플릿
        </button>

        {/* 저장 버튼 (기존 동작 유지) */}
        <button
          type="button"
          onClick={() => onSave()}
          disabled={!canSave}
          aria-label="전략 저장"
          style={primaryButtonStyle(canSave)}
        >
          {isSaving ? "저장 중..." : "저장"}
        </button>

        {/* 복사 */}
        <button
          type="button"
          onClick={onDuplicate}
          disabled={!canDuplicate}
          aria-label="전략 복사"
          title={
            savedStrategyId == null
              ? "복사하려면 먼저 저장해야 합니다"
              : "현재 전략을 사본으로 만듭니다"
          }
          style={secondaryButtonStyle}
        >
          {duplicateMutation.isPending ? "복사 중..." : "복사"}
        </button>

        {/* JSON 보기 */}
        <button
          type="button"
          onClick={() => setShowJson(true)}
          aria-label="JSON 보기"
          style={secondaryButtonStyle}
        >
          JSON 보기
        </button>

        {/* 백테스트 실행 */}
        <button
          type="button"
          onClick={onRunBacktest}
          disabled={isSaving === true}
          aria-label="백테스트 실행"
          style={primaryButtonStyle(true, "#16a34a")}
        >
          백테스트 실행
        </button>
      </div>

      {saveErrorMessage && (
        <span style={{ fontSize: 12, color: "crimson", width: "100%" }}>{saveErrorMessage}</span>
      )}
      {runError && (
        <span style={{ fontSize: 12, color: "crimson", width: "100%" }}>{runError}</span>
      )}

      {/* JSON 모달 */}
      {showJson && (
        <Modal title="전략 JSON" onClose={() => setShowJson(false)}>
          <pre
            aria-label="직렬화된 전략 JSON"
            style={{
              maxHeight: "60vh",
              overflow: "auto",
              background: "#f9fafb",
              border: "1px solid #e5e7eb",
              borderRadius: 4,
              padding: 12,
              fontSize: 12,
              fontFamily: "ui-monospace, SFMono-Regular, monospace",
              margin: 0,
              whiteSpace: "pre",
            }}
          >
            {jsonText}
          </pre>
          <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
            <button type="button" onClick={onCopyJson} style={secondaryButtonStyle}>
              클립보드에 복사
            </button>
            {copyMessage && (
              <span style={{ fontSize: 12, color: "#16a34a" }}>{copyMessage}</span>
            )}
          </div>
        </Modal>
      )}

      {/* 템플릿 모달 */}
      {showTemplates && (
        <Modal title="전략 템플릿 선택" onClose={() => setShowTemplates(false)}>
          <TemplateSelector
            onApplied={(t: StrategyTemplate) => {
              setShowTemplates(false);
              void t;
            }}
          />
        </Modal>
      )}
    </header>
  );
}

// ----------------------------------------------------------------- styles

function primaryButtonStyle(enabled: boolean, color = "#2563eb"): React.CSSProperties {
  return {
    padding: "6px 12px",
    border: "1px solid #d1d5db",
    borderRadius: 4,
    background: enabled ? color : "white",
    color: enabled ? "white" : "#9ca3af",
    cursor: enabled ? "pointer" : "not-allowed",
    fontSize: 13,
  };
}

const secondaryButtonStyle: React.CSSProperties = {
  padding: "6px 10px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  background: "white",
  color: "#1f2937",
  cursor: "pointer",
  fontSize: 13,
};

function modeButtonStyle(active: boolean): React.CSSProperties {
  return {
    padding: "4px 10px",
    border: "none",
    borderRight: "1px solid #d1d5db",
    background: active ? "#2563eb" : "white",
    color: active ? "white" : "#374151",
    cursor: "pointer",
    fontSize: 12,
  };
}

// ----------------------------------------------------------------- modal

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,23,42,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white",
          borderRadius: 8,
          padding: 16,
          minWidth: 480,
          maxWidth: "min(90vw, 720px)",
          boxShadow: "0 8px 24px rgba(0,0,0,0.15)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 12,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontSize: 18,
              color: "#6b7280",
            }}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
