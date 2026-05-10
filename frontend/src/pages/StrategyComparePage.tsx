/**
 * StrategyComparePage — 11-h 골격 (033).
 *
 * 본 step 범위: 라우팅 + skeleton (전략 2개 선택 → "비교 기능 준비 중" 메시지).
 * 본격적 비교 기능 (실행 결과 비교 차트, summary 비교 표 등)은 후속 step에서.
 *
 * 사용자 흐름:
 *   1. 전략 목록에서 비교할 전략 2개 선택
 *   2. (TODO) 각 전략의 최신 백테스트 결과를 나란히 표시
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { useStrategies } from "../api/strategies";

export default function StrategyComparePage() {
  const { data: strategies, isLoading } = useStrategies();
  const [leftId, setLeftId] = useState<number | "">("");
  const [rightId, setRightId] = useState<number | "">("");

  const canCompare =
    leftId !== "" && rightId !== "" && Number(leftId) !== Number(rightId);

  return (
    <div
      data-testid="strategy-compare-page"
      style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 920 }}
    >
      <p>
        <Link to="/strategies" style={{ color: "#6b7280", fontSize: 13 }}>
          ← 전략 목록
        </Link>
      </p>
      <h1 style={{ fontSize: 18, fontWeight: 600 }}>전략 비교</h1>
      <p style={{ fontSize: 12, color: "#9ca3af" }}>
        전략 2개를 선택하면 백테스트 결과를 나란히 비교할 수 있습니다.
      </p>

      {isLoading && <p>로딩 중...</p>}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          marginTop: 16,
        }}
      >
        <fieldset style={fieldset}>
          <legend style={legend}>전략 A</legend>
          <select
            aria-label="전략 A 선택"
            data-testid="compare-left"
            value={String(leftId)}
            onChange={(e) =>
              setLeftId(e.target.value ? Number(e.target.value) : "")
            }
            style={selectStyle}
          >
            <option value="">전략을 선택하세요</option>
            {strategies?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </fieldset>

        <fieldset style={fieldset}>
          <legend style={legend}>전략 B</legend>
          <select
            aria-label="전략 B 선택"
            data-testid="compare-right"
            value={String(rightId)}
            onChange={(e) =>
              setRightId(e.target.value ? Number(e.target.value) : "")
            }
            style={selectStyle}
          >
            <option value="">전략을 선택하세요</option>
            {strategies?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </fieldset>
      </div>

      <div
        data-testid="compare-result-placeholder"
        style={{
          marginTop: 24,
          padding: 24,
          background: "#f9fafb",
          border: "1px dashed #d1d5db",
          borderRadius: 6,
          textAlign: "center",
          color: "#6b7280",
          fontSize: 13,
        }}
      >
        {canCompare ? (
          <>
            <strong>비교 기능 준비 중</strong>
            <p style={{ marginTop: 8, fontSize: 12 }}>
              선택한 전략 2개(ID {leftId} vs {rightId})의 백테스트 결과 비교 화면은
              후속 step에서 구현됩니다.
            </p>
          </>
        ) : (
          <p style={{ margin: 0 }}>
            비교할 두 전략을 각각 선택하세요. (서로 다른 전략이어야 합니다)
          </p>
        )}
      </div>
    </div>
  );
}

const fieldset: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  padding: 12,
  borderRadius: 6,
};

const legend: React.CSSProperties = {
  fontSize: 13,
  color: "#374151",
  fontWeight: 600,
};

const selectStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  fontSize: 13,
  border: "1px solid #d1d5db",
  borderRadius: 4,
};
