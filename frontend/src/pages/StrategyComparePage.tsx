/**
 * StrategyComparePage — 복수 전략 선택 + 지표 비교 테이블 (056 / 11-i).
 *
 * 구현 내용:
 *  - 드롭다운으로 전략 최대 5개 선택
 *  - 선택한 전략의 최신 완료된 백테스트 summary 조회
 *  - TanStack Table: 지표 행 × 전략 열 비교 테이블
 *  - 데이터 없는 전략은 "-" graceful 표시
 */

import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import { useStrategies } from "../api/strategies";
import {
  useLatestCompletedRunId,
  useBacktestSummary,
  type BacktestSummaryOut,
} from "../api/backtests";

// ──────────────────────────────────────────────────────────────────────────────
// 상수 / 타입
// ──────────────────────────────────────────────────────────────────────────────

const MAX_STRATEGIES = 5;

/** 비교 테이블에 표시할 지표 행 정의 */
type MetricRow = {
  label: string;
  key: keyof NonNullable<BacktestSummaryOut["summary"]>;
  format: (v: number | null | undefined) => string;
};

const METRICS: MetricRow[] = [
  {
    label: "총수익률",
    key: "total_return_pct",
    format: (v) => (v == null ? "-" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`),
  },
  {
    label: "연환산수익률",
    key: "annual_return_pct",
    format: (v) => (v == null ? "-" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`),
  },
  {
    label: "MDD",
    key: "mdd_pct",
    format: (v) => (v == null ? "-" : `${v.toFixed(1)}%`),
  },
  {
    label: "승률",
    key: "win_rate",
    format: (v) => (v == null ? "-" : `${(v * 100).toFixed(1)}%`),
  },
  {
    label: "샤프지수",
    key: "profit_factor",
    format: (v) => (v == null ? "-" : v.toFixed(2)),
  },
  {
    label: "평균보유일",
    key: "avg_holding_days",
    format: (v) => (v == null ? "-" : `${v.toFixed(1)}일`),
  },
  {
    label: "거래횟수",
    key: "trade_count",
    format: (v) => (v == null ? "-" : `${v}회`),
  },
  {
    label: "초기자금",
    key: "initial_cash",
    format: (v) =>
      v == null ? "-" : `${Math.round(v).toLocaleString("ko-KR")}원`,
  },
  {
    label: "최종자산",
    key: "final_equity",
    format: (v) =>
      v == null ? "-" : `${Math.round(v).toLocaleString("ko-KR")}원`,
  },
];

// ──────────────────────────────────────────────────────────────────────────────
// 서브 컴포넌트: 전략 1개의 summary 로더
// ──────────────────────────────────────────────────────────────────────────────

/**
 * 단일 전략 ID를 받아 최신 run_id → summary 를 순차 조회하는 훅.
 * 두 개 이상의 훅을 조건부로 부르면 안 되므로, 전략 슬롯별 컴포넌트를 분리함.
 */
function useStrategySummary(strategyId: number | null) {
  const { runId, isLoading: runLoading } = useLatestCompletedRunId(strategyId);
  const { data: summaryData, isLoading: summaryLoading } = useBacktestSummary(
    runId,
    runId !== null,
  );
  return {
    runId,
    summary: summaryData?.summary ?? null,
    isLoading: runLoading || summaryLoading,
  };
}

// TanStack Table 행 타입: 지표명 + 전략별 셀 값
type CompareRow = {
  label: string;
  values: string[];
};

// ──────────────────────────────────────────────────────────────────────────────
// 메인 비교 테이블 컴포넌트
// ──────────────────────────────────────────────────────────────────────────────

interface CompareTableProps {
  strategyNames: string[];
  summaries: (BacktestSummaryOut["summary"] | null)[];
  loadingFlags: boolean[];
}

function CompareTable({
  strategyNames,
  summaries,
  loadingFlags,
}: CompareTableProps) {
  const rows: CompareRow[] = useMemo(
    () =>
      METRICS.map((m) => ({
        label: m.label,
        values: summaries.map((s, i) => {
          if (loadingFlags[i]) return "로딩...";
          if (!s) return "-";
          const raw = s[m.key] as number | null | undefined;
          return m.format(raw);
        }),
      })),
    [summaries, loadingFlags],
  );

  const columns = useMemo<ColumnDef<CompareRow>[]>(
    () => [
      {
        id: "label",
        header: "지표",
        accessorKey: "label",
        cell: (info) => (
          <span style={{ fontWeight: 500, color: "#374151" }}>
            {info.getValue<string>()}
          </span>
        ),
      },
      ...strategyNames.map((name, idx) => ({
        id: `strategy-${idx}`,
        header: name,
        cell: ({ row }: { row: { original: CompareRow } }) => {
          const val = row.original.values[idx];
          const isLoading = val === "로딩...";
          const isNegative =
            !isLoading && val !== "-" && val.startsWith("-") && val.includes("%");
          const isPositive =
            !isLoading && val !== "-" && val.startsWith("+") && val.includes("%");
          return (
            <span
              style={{
                color: isNegative
                  ? "#dc2626"
                  : isPositive
                    ? "#16a34a"
                    : "#1f2937",
                fontSize: 13,
              }}
            >
              {val}
            </span>
          );
        },
      })),
    ],
    [strategyNames],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div style={{ overflowX: "auto", marginTop: 24 }}>
      <table
        data-testid="compare-table"
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 13,
        }}
      >
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header, i) => (
                <th
                  key={header.id}
                  style={{
                    padding: "8px 12px",
                    textAlign: i === 0 ? "left" : "right",
                    background: "#f9fafb",
                    borderBottom: "2px solid #e5e7eb",
                    fontWeight: 600,
                    color: "#374151",
                    whiteSpace: "nowrap",
                  }}
                >
                  {flexRender(
                    header.column.columnDef.header,
                    header.getContext(),
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, ri) => (
            <tr
              key={row.id}
              style={{ background: ri % 2 === 0 ? "white" : "#f9fafb" }}
            >
              {row.getVisibleCells().map((cell, ci) => (
                <td
                  key={cell.id}
                  style={{
                    padding: "8px 12px",
                    textAlign: ci === 0 ? "left" : "right",
                    borderBottom: "1px solid #f3f4f6",
                  }}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// 슬롯 단위 summary 로더 (훅 규칙 준수를 위해 고정 5슬롯 사용)
// ──────────────────────────────────────────────────────────────────────────────

/** 고정 5개 슬롯을 항상 훅으로 등록하고, null이면 비활성화 */
function useAllSummaries(selectedIds: (number | null)[]) {
  // 훅 규칙: 조건부 호출 금지 → 슬롯 0~4 항상 호출
  const s0 = useStrategySummary(selectedIds[0] ?? null);
  const s1 = useStrategySummary(selectedIds[1] ?? null);
  const s2 = useStrategySummary(selectedIds[2] ?? null);
  const s3 = useStrategySummary(selectedIds[3] ?? null);
  const s4 = useStrategySummary(selectedIds[4] ?? null);
  return [s0, s1, s2, s3, s4];
}

// ──────────────────────────────────────────────────────────────────────────────
// 메인 페이지
// ──────────────────────────────────────────────────────────────────────────────

export default function StrategyComparePage() {
  const { data: strategies, isLoading: strategiesLoading } = useStrategies();

  // selectedIds: 최대 5개, null은 빈 슬롯
  const [selectedIds, setSelectedIds] = useState<(number | null)[]>([
    null,
    null,
  ]);

  const allSlotSummaries = useAllSummaries(
    // 항상 길이 5로 패딩
    [...selectedIds, null, null, null, null, null].slice(0, 5) as (
      | number
      | null
    )[],
  );

  // 실제 선택된 슬롯 수 기준 데이터 추출
  const activeSummaries = selectedIds.map((_, i) => allSlotSummaries[i]);

  const filledCount = selectedIds.filter((id) => id !== null).length;
  const canCompare = filledCount >= 2;

  // 드롭다운 변경
  function handleChange(slotIndex: number, value: string) {
    const next = [...selectedIds];
    next[slotIndex] = value ? Number(value) : null;
    setSelectedIds(next);
  }

  // 슬롯 추가
  function addSlot() {
    if (selectedIds.length < MAX_STRATEGIES) {
      setSelectedIds([...selectedIds, null]);
    }
  }

  // 슬롯 제거
  function removeSlot(index: number) {
    if (selectedIds.length <= 2) return;
    const next = selectedIds.filter((_, i) => i !== index);
    setSelectedIds(next);
  }

  // 선택된 전략 이름 목록 (비교 테이블 헤더용)
  const selectedStrategyNames = selectedIds.map((id) => {
    if (!id) return "미선택";
    return strategies?.find((s) => s.id === id)?.name ?? `전략 ${id}`;
  });

  // 이미 선택된 ID 집합 (중복 방지용)
  const usedIds = new Set(selectedIds.filter(Boolean));

  return (
    <div
      data-testid="strategy-compare-page"
      style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 1100 }}
    >
      <p>
        <Link to="/strategies" style={{ color: "#6b7280", fontSize: 13 }}>
          ← 전략 목록
        </Link>
      </p>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 4,
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>전략 비교</h1>
        {selectedIds.length < MAX_STRATEGIES && (
          <button onClick={addSlot} style={addBtn}>
            + 전략 추가
          </button>
        )}
      </div>
      <p style={{ fontSize: 12, color: "#9ca3af", margin: "4px 0 16px" }}>
        전략을 2~{MAX_STRATEGIES}개 선택하면 백테스트 결과를 나란히 비교합니다.
        최신 완료된 백테스트 결과를 자동으로 불러옵니다.
      </p>

      {strategiesLoading && <p style={{ fontSize: 13 }}>전략 목록 로딩 중...</p>}

      {/* 슬롯 드롭다운 행 */}
      <div
        style={{
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "flex-start",
        }}
      >
        {selectedIds.map((selectedId, slotIdx) => {
          const slotLabel = String.fromCharCode(65 + slotIdx); // A, B, C, D, E
          const { runId, isLoading: slotLoading } = activeSummaries[slotIdx];
          return (
            <div
              key={slotIdx}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 6,
                padding: 12,
                minWidth: 180,
                flex: "1 1 180px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <span
                  style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}
                >
                  전략 {slotLabel}
                </span>
                {selectedIds.length > 2 && (
                  <button
                    onClick={() => removeSlot(slotIdx)}
                    style={removeBtn}
                    aria-label={`전략 ${slotLabel} 슬롯 제거`}
                  >
                    ✕
                  </button>
                )}
              </div>
              <select
                aria-label={`전략 ${slotLabel} 선택`}
                data-testid={
                  slotIdx === 0
                    ? "compare-left"
                    : slotIdx === 1
                      ? "compare-right"
                      : `compare-slot-${slotIdx}`
                }
                value={selectedId !== null ? String(selectedId) : ""}
                onChange={(e) => handleChange(slotIdx, e.target.value)}
                style={selectStyle}
              >
                <option value="">전략을 선택하세요</option>
                {strategies?.map((s) => (
                  <option
                    key={s.id}
                    value={s.id}
                    disabled={usedIds.has(s.id) && s.id !== selectedId}
                  >
                    {s.name}
                  </option>
                ))}
              </select>
              {/* 백테스트 상태 표시 */}
              {selectedId && (
                <div style={{ marginTop: 6, fontSize: 11, color: "#6b7280" }}>
                  {slotLoading ? (
                    "백테스트 조회 중..."
                  ) : runId ? (
                    <>
                      백테스트 #{runId}{" "}
                      <Link
                        to={`/backtests/${runId}`}
                        style={{ color: "#2563eb" }}
                      >
                        결과 보기
                      </Link>
                    </>
                  ) : (
                    <span style={{ color: "#9ca3af" }}>
                      완료된 백테스트 없음
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 비교 영역 */}
      <div style={{ marginTop: 24 }}>
        {!canCompare ? (
          <div
            data-testid="compare-guide"
            style={{
              padding: 24,
              background: "#f9fafb",
              border: "1px dashed #d1d5db",
              borderRadius: 6,
              textAlign: "center",
              color: "#6b7280",
              fontSize: 13,
            }}
          >
            <p style={{ margin: 0 }}>
              전략을 2개 이상 선택하세요. (서로 다른 전략이어야 합니다)
            </p>
          </div>
        ) : (
          <div data-testid="compare-result">
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 8,
              }}
            >
              <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>
                지표 비교
              </h2>
              <span style={{ fontSize: 12, color: "#9ca3af" }}>
                (완료된 백테스트 없는 전략은 "-" 표시)
              </span>
            </div>
            <CompareTable
              strategyNames={selectedStrategyNames}
              summaries={activeSummaries.map((s) => s.summary)}
              loadingFlags={activeSummaries.map((s) => s.isLoading)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// 스타일
// ──────────────────────────────────────────────────────────────────────────────

const selectStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  fontSize: 13,
  border: "1px solid #d1d5db",
  borderRadius: 4,
};

const addBtn: React.CSSProperties = {
  padding: "5px 12px",
  fontSize: 13,
  background: "#2563eb",
  color: "white",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
};

const removeBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  color: "#9ca3af",
  fontSize: 12,
  padding: "2px 4px",
};
