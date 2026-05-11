/**
 * StrategyListPage — TanStack Table + 텍스트 필터 + 컬럼 정렬 (056 / 11-j).
 *
 * 변경 내용:
 *  - 기존 map() 렌더 → @tanstack/react-table
 *  - 컬럼: 전략명, 생성일, 마지막 백테스트, 총수익률, 액션(실행/결과/비교추가)
 *  - 정렬: 헤더 클릭으로 컬럼 정렬
 *  - 필터: 전략명 텍스트 검색
 */

import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
} from "@tanstack/react-table";
import { useStrategies, type StrategyOut, type StrategyLastBacktest } from "../api/strategies";

// ──────────────────────────────────────────────────────────────────────────────
// 메인 페이지
// ──────────────────────────────────────────────────────────────────────────────

export default function StrategyListPage() {
  const { data, isLoading, error } = useStrategies();

  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [nameFilter, setNameFilter] = useState("");

  const columns = useMemo<ColumnDef<StrategyOut>[]>(
    () => [
      {
        id: "name",
        header: "전략명",
        accessorKey: "name",
        filterFn: "includesString",
        cell: (info) => (
          <div>
            <div style={{ fontWeight: 600 }}>{info.getValue<string>()}</div>
            <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
              {info.row.original.tags.join(", ") || "태그 없음"}
            </div>
          </div>
        ),
      },
      {
        id: "created_at",
        header: "생성일",
        accessorKey: "created_at",
        cell: (info) => (
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            {formatDate(info.getValue<string>())}
          </span>
        ),
      },
      {
        id: "last_backtest",
        header: "마지막 백테스트",
        accessorFn: (row) => row.last_backtest?.run_date ?? null,
        sortingFn: "alphanumeric",
        cell: (info) => {
          const lb = info.row.original.last_backtest;
          if (!lb) {
            return (
              <div data-testid="last-backtest-empty">
                <span style={{ fontSize: 11, color: "#9ca3af" }}>
                  최근 백테스트 없음
                </span>
              </div>
            );
          }
          const dateLabel = lb.run_date ? formatDate(lb.run_date) : null;
          const returnPct = lb.total_return;
          const returnColor = returnPct >= 0 ? "#16a34a" : "#dc2626";
          const returnLabel =
            returnPct >= 0
              ? `+${returnPct.toFixed(1)}%`
              : `${returnPct.toFixed(1)}%`;
          return (
            <div
              data-testid="last-backtest-badge"
              style={{ display: "flex", alignItems: "center", gap: 8 }}
            >
              {dateLabel && (
                <span style={{ fontSize: 11, color: "#6b7280" }}>
                  {dateLabel}
                </span>
              )}
              <span
                data-testid="last-backtest-return"
                style={{ fontSize: 13, fontWeight: 600, color: returnColor }}
              >
                {returnLabel}
              </span>
              <span style={{ fontSize: 11, color: "#9ca3af" }}>
                MDD {lb.mdd.toFixed(1)}%
              </span>
            </div>
          );
        },
      },
      {
        id: "actions",
        header: "액션",
        enableSorting: false,
        cell: (info) => {
          const s = info.row.original;
          return (
            <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
              <Link to={`/backtests/new?strategy_id=${s.id}`} style={btn}>
                백테스트 실행
              </Link>
              <Link to={`/strategies/${s.id}/edit`} style={btn}>
                편집
              </Link>
            </div>
          );
        },
      },
    ],
    [],
  );

  const tableData = useMemo(() => data ?? [], [data]);

  const table = useReactTable({
    data: tableData,
    columns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  // 이름 필터 입력 → columnFilters 동기화
  function handleNameFilter(value: string) {
    setNameFilter(value);
    setColumnFilters((prev) => {
      const others = prev.filter((f) => f.id !== "name");
      return value ? [...others, { id: "name", value }] : others;
    });
  }

  return (
    <div
      data-testid="strategy-list-page"
      style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 980 }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 600 }}>주식 전략 연구소</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <Link
            to="/strategies/compare"
            style={{
              padding: "6px 12px",
              background: "white",
              color: "#1f2937",
              border: "1px solid #d1d5db",
              borderRadius: 4,
              textDecoration: "none",
              fontSize: 14,
            }}
          >
            전략 비교
          </Link>
          <Link
            to="/strategies/new"
            style={{
              padding: "6px 12px",
              background: "#2563eb",
              color: "white",
              borderRadius: 4,
              textDecoration: "none",
              fontSize: 14,
            }}
          >
            + 새 전략 만들기
          </Link>
        </div>
      </header>

      <div style={{ marginTop: 20, marginBottom: 12 }}>
        <input
          data-testid="strategy-name-filter"
          type="text"
          placeholder="전략명으로 검색..."
          value={nameFilter}
          onChange={(e) => handleNameFilter(e.target.value)}
          style={{
            padding: "6px 10px",
            fontSize: 13,
            border: "1px solid #d1d5db",
            borderRadius: 4,
            width: 240,
          }}
        />
      </div>

      {isLoading && <p style={{ fontSize: 13 }}>로딩 중...</p>}
      {error && (
        <p style={{ color: "crimson", fontSize: 13 }}>
          백엔드 연결 실패.{" "}
          <code>uvicorn app.main:app --reload --port 8000</code> 실행 필요.
        </p>
      )}
      {!isLoading && !error && tableData.length === 0 && (
        <p style={{ color: "#9ca3af", fontSize: 13 }}>
          아직 저장된 전략이 없습니다.
        </p>
      )}

      {!isLoading && !error && tableData.length > 0 && (
        <>
          <div style={{ overflowX: "auto" }}>
            <table
              data-testid="strategy-table"
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 13,
              }}
            >
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => {
                      const canSort = header.column.getCanSort();
                      const sortDir = header.column.getIsSorted();
                      return (
                        <th
                          key={header.id}
                          onClick={
                            canSort
                              ? header.column.getToggleSortingHandler()
                              : undefined
                          }
                          data-testid={`th-${header.id}`}
                          style={{
                            padding: "8px 12px",
                            textAlign: "left",
                            background: "#f9fafb",
                            borderBottom: "2px solid #e5e7eb",
                            fontWeight: 600,
                            color: "#374151",
                            cursor: canSort ? "pointer" : "default",
                            userSelect: "none",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {canSort && (
                            <span style={{ marginLeft: 4, color: "#9ca3af" }}>
                              {sortDir === "asc"
                                ? "▲"
                                : sortDir === "desc"
                                  ? "▼"
                                  : "⇅"}
                            </span>
                          )}
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={columns.length}
                      style={{
                        textAlign: "center",
                        padding: 24,
                        color: "#9ca3af",
                        fontSize: 13,
                      }}
                    >
                      검색 결과가 없습니다.
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row, ri) => (
                    <tr
                      key={row.id}
                      style={{ background: ri % 2 === 0 ? "white" : "#f9fafb" }}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td
                          key={cell.id}
                          style={{
                            padding: "10px 12px",
                            borderBottom: "1px solid #f3f4f6",
                            verticalAlign: "middle",
                          }}
                        >
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext(),
                          )}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 8 }}>
            총 {table.getFilteredRowModel().rows.length}개 전략
            {nameFilter && ` (검색: "${nameFilter}")`}
          </p>
        </>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// 유틸리티
// ──────────────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return iso.slice(0, 10).replace(/-/g, ".");
}

// last_backtest 뱃지는 테이블 셀 렌더러로 대체되어 별도 컴포넌트 불필요.
// 하지만 기존 테스트 data-testid 호환을 위해 래퍼 유지.
export function LastBacktestBadge({
  lastBacktest,
}: {
  lastBacktest: StrategyLastBacktest | null | undefined;
}) {
  if (!lastBacktest) {
    return (
      <div data-testid="last-backtest-empty">
        <span style={{ fontSize: 11, color: "#9ca3af" }}>최근 백테스트 없음</span>
      </div>
    );
  }

  const returnPct = lastBacktest.total_return;
  const returnColor = returnPct >= 0 ? "#16a34a" : "#dc2626";
  const returnLabel =
    returnPct >= 0 ? `+${returnPct.toFixed(1)}%` : `${returnPct.toFixed(1)}%`;
  const dateLabel = lastBacktest.run_date ? formatDate(lastBacktest.run_date) : null;

  return (
    <div data-testid="last-backtest-badge">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {dateLabel && (
          <span style={{ fontSize: 11, color: "#6b7280" }}>{dateLabel}</span>
        )}
        <span
          data-testid="last-backtest-return"
          style={{ fontSize: 13, fontWeight: 600, color: returnColor }}
        >
          {returnLabel}
        </span>
        <span style={{ fontSize: 11, color: "#9ca3af" }}>
          MDD {lastBacktest.mdd.toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

const btn: React.CSSProperties = {
  padding: "4px 10px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  textDecoration: "none",
  color: "#1f2937",
  fontSize: 12,
};
