/**
 * TradesTable — TanStack Table 기반 거래 내역 테이블 (08-m / 033).
 *
 * 책임:
 *   - 거래 그룹(trade_groups) 정렬/필터/페이지네이션
 *   - 행 클릭 → onRowClick(tradeGroup): 부모는 selectedSymbol 변경 + 차트 탭 이동 + 차트 visibleRange 설정
 *
 * 컬럼 (08번 §5 · CLAUDE.md #4 — trade_groups 1:N 모델):
 *   - 종목 (symbol + name)
 *   - 매수일 (entry_date)
 *   - 청산일 (last sell.execution_date or "보유 중")
 *   - 매수가 (entry_price)
 *   - 청산가 (last sell.price or "—")
 *   - 수량 (entry_quantity)
 *   - 실현 손익 (final_profit)
 *   - 수익률 (final_profit_rate)
 *   - 매도 사유 (last sell.exit_reason)
 *
 * 정렬 기본: entry_date ASC (CLAUDE.md #8 결정론).
 * 페이지 크기: 기본 25 (frontend-developer.md "페이지네이션 기본 100"보다 작게 설정 —
 *   결과 페이지 단일 화면 가시성 우선; 향후 옵션화 가능).
 */

import { useMemo, useState } from "react";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import type { TradeGroupOut } from "../../../api/backtests";
import { formatInt, formatKrw, formatSignedPct } from "../../../utils/formatters";

export type TradeRowClickInfo = {
  tradeGroup: TradeGroupOut;
  /** 봉차트 시간 범위로 활용 (lightweight-charts setVisibleRange). */
  entryDate: string;
  exitDate: string | null;
};

export default function TradesTable({
  items,
  onRowClick,
}: {
  items: TradeGroupOut[];
  onRowClick?: (info: TradeRowClickInfo) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "entry_date", desc: false }, // 결정론 default
  ]);
  const [filter, setFilter] = useState("");

  const columns = useMemo<ColumnDef<TradeGroupOut>[]>(
    () => [
      {
        id: "symbol",
        accessorFn: (row) => `${row.symbol} ${row.name ?? ""}`.trim(),
        header: "종목",
        cell: ({ row }) => (
          <span>
            <strong>{row.original.symbol}</strong>
            {row.original.name && (
              <span style={{ color: "#6b7280", marginLeft: 4 }}>
                ({row.original.name})
              </span>
            )}
          </span>
        ),
        enableSorting: true,
        filterFn: "includesString",
      },
      {
        id: "entry_date",
        accessorKey: "entry_date",
        header: "매수일",
        cell: (info) => info.getValue<string>(),
        enableSorting: true,
      },
      {
        id: "exit_date",
        accessorFn: (row) => lastSellDate(row),
        header: "청산일",
        cell: ({ row }) => lastSellDate(row.original) ?? "보유 중",
        enableSorting: true,
        sortUndefined: "last",
      },
      {
        id: "entry_price",
        accessorKey: "entry_price",
        header: "매수가",
        cell: (info) => formatInt(info.getValue<number>()),
        meta: { align: "right" },
        enableSorting: true,
      },
      {
        id: "exit_price",
        accessorFn: (row) => lastSellPrice(row),
        header: "청산가",
        cell: ({ row }) => formatInt(lastSellPrice(row.original)),
        meta: { align: "right" },
        enableSorting: true,
      },
      {
        id: "quantity",
        accessorKey: "entry_quantity",
        header: "수량",
        cell: (info) => formatInt(info.getValue<number>()),
        meta: { align: "right" },
        enableSorting: true,
      },
      {
        id: "realized_profit",
        accessorKey: "final_profit",
        header: "실현 손익",
        cell: (info) => formatKrw(info.getValue<number | null>()),
        meta: { align: "right" },
        enableSorting: true,
      },
      {
        id: "realized_profit_rate",
        accessorKey: "final_profit_rate",
        header: "수익률",
        cell: (info) => {
          const v = info.getValue<number | null>();
          if (v === null || v === undefined) return "—";
          return (
            <span
              style={{
                color: v >= 0 ? "#dc2626" : "#1d4ed8",
                fontWeight: 500,
              }}
            >
              {formatSignedPct(v)}
            </span>
          );
        },
        meta: { align: "right" },
        enableSorting: true,
      },
      {
        id: "exit_reason",
        accessorFn: (row) => lastSellReason(row) ?? "",
        header: "매도 사유",
        cell: ({ row }) => lastSellReason(row.original) ?? "—",
        enableSorting: true,
      },
    ],
    [],
  );

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting, globalFilter: filter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 25 } },
    globalFilterFn: "includesString",
  });

  const rows = table.getRowModel().rows;

  return (
    <div data-testid="trades-table-container">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 8,
          flexWrap: "wrap",
        }}
      >
        <input
          aria-label="거래 필터"
          data-testid="trades-filter"
          placeholder="종목 / 사유 검색…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{
            padding: "4px 8px",
            fontSize: 12,
            border: "1px solid #d1d5db",
            borderRadius: 4,
            minWidth: 200,
          }}
        />
        <span style={{ fontSize: 11, color: "#6b7280" }}>
          총 {table.getFilteredRowModel().rows.length}건 / 페이지{" "}
          {table.getState().pagination.pageIndex + 1} /{" "}
          {Math.max(1, table.getPageCount())}
        </span>
      </div>

      <table
        data-testid="trades-table"
        style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}
      >
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} style={{ background: "#f9fafb" }}>
              {hg.headers.map((h) => {
                const isSorted = h.column.getIsSorted();
                return (
                  <th
                    key={h.id}
                    onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                    data-testid={`th-${h.column.id}`}
                    style={{
                      textAlign:
                        (h.column.columnDef.meta as { align?: string } | undefined)?.align === "right"
                          ? "right"
                          : "left",
                      padding: "6px 8px",
                      fontWeight: 600,
                      cursor: h.column.getCanSort() ? "pointer" : "default",
                      userSelect: "none",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {isSorted === "asc" && " ▲"}
                    {isSorted === "desc" && " ▼"}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                style={{ padding: 12, color: "#9ca3af", textAlign: "center" }}
              >
                일치하는 거래가 없습니다.
              </td>
            </tr>
          )}
          {rows.map((row) => (
            <tr
              key={row.id}
              data-testid={`trade-row-${row.original.trade_group_id}`}
              onClick={
                onRowClick
                  ? () =>
                      onRowClick({
                        tradeGroup: row.original,
                        entryDate: row.original.entry_date,
                        exitDate: lastSellDate(row.original),
                      })
                  : undefined
              }
              style={{
                borderTop: "1px solid #f3f4f6",
                cursor: onRowClick ? "pointer" : "default",
              }}
            >
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  style={{
                    padding: "6px 8px",
                    textAlign:
                      (cell.column.columnDef.meta as { align?: string } | undefined)?.align === "right"
                        ? "right"
                        : "left",
                  }}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {/* 페이징 컨트롤 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 8,
          fontSize: 12,
        }}
      >
        <button
          data-testid="page-prev"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
          style={pageBtnStyle(!table.getCanPreviousPage())}
        >
          ◀ 이전
        </button>
        <button
          data-testid="page-next"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
          style={pageBtnStyle(!table.getCanNextPage())}
        >
          다음 ▶
        </button>
        <select
          data-testid="page-size"
          value={table.getState().pagination.pageSize}
          onChange={(e) => table.setPageSize(Number(e.target.value))}
          style={{
            padding: "4px 8px",
            fontSize: 12,
            border: "1px solid #d1d5db",
            borderRadius: 4,
          }}
        >
          {[10, 25, 50, 100].map((s) => (
            <option key={s} value={s}>
              {s}건/페이지
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

// --- helpers ---

function lastSell(tg: TradeGroupOut) {
  return tg.executions.filter((e) => e.execution_type !== "BUY").at(-1);
}

function lastSellDate(tg: TradeGroupOut): string | null {
  return lastSell(tg)?.execution_date ?? null;
}

function lastSellPrice(tg: TradeGroupOut): number | null {
  return lastSell(tg)?.price ?? null;
}

function lastSellReason(tg: TradeGroupOut): string | null {
  return lastSell(tg)?.exit_reason ?? null;
}

function pageBtnStyle(disabled: boolean): React.CSSProperties {
  return {
    padding: "4px 10px",
    fontSize: 12,
    border: "1px solid #d1d5db",
    borderRadius: 4,
    background: disabled ? "#f3f4f6" : "white",
    color: disabled ? "#9ca3af" : "#1f2937",
    cursor: disabled ? "not-allowed" : "pointer",
  };
}
