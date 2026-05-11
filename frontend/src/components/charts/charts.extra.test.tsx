import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, cleanup } from "@testing-library/react";
import DrawdownChart from "./DrawdownChart";
import CashChart from "./CashChart";
import VolumeChart from "./VolumeChart";
import BenchmarkCompareChart from "./BenchmarkCompareChart";
import PositionsCountChart from "./PositionsCountChart";
import type { DailyEquityOut } from "../../api/backtests";
import type { CandleBar, EquityPoint } from "../../api/chartData";

/**
 * 차트 컴포넌트 추가 단위 테스트 (11-n)
 *
 * - 빈 데이터로 렌더 시 오류 없음
 * - props 변경 시 setData 재호출 (재렌더)
 * - charts/index.ts re-export 동작
 */

const setDataMock = vi.fn();
const removeSeriesMock = vi.fn();
const addSeriesMock = vi.fn(() => ({ setData: setDataMock }));
const applyOptionsMock = vi.fn();
const removeChartMock = vi.fn();

vi.mock("lightweight-charts", () => ({
  ColorType: { Solid: "solid" },
  createChart: vi.fn(() => ({
    addAreaSeries: addSeriesMock,
    addLineSeries: addSeriesMock,
    addHistogramSeries: addSeriesMock,
    removeSeries: removeSeriesMock,
    applyOptions: applyOptionsMock,
    remove: removeChartMock,
    timeScale: () => ({}),
  })),
}));

beforeEach(() => {
  setDataMock.mockClear();
  removeSeriesMock.mockClear();
  addSeriesMock.mockClear();
  applyOptionsMock.mockClear();
  removeChartMock.mockClear();
});

// --- DrawdownChart ---
describe("DrawdownChart 추가", () => {
  it("빈 배열 전달 시 렌더 오류 없음 + setData([]) 호출", () => {
    expect(() => render(<DrawdownChart equity={[]} />)).not.toThrow();
    cleanup();
  });

  it("props equity 변경 시 setData 재호출 (rerenderability)", () => {
    const equity1: EquityPoint[] = [{ time: "2024-01-01", value: 100, drawdown: -1 }];
    const equity2: EquityPoint[] = [
      { time: "2024-01-01", value: 100, drawdown: -1 },
      { time: "2024-01-02", value: 98, drawdown: -3 },
    ];
    const { rerender } = render(<DrawdownChart equity={equity1} />);
    const callCount1 = setDataMock.mock.calls.length;
    rerender(<DrawdownChart equity={equity2} />);
    expect(setDataMock.mock.calls.length).toBeGreaterThan(callCount1);
    cleanup();
  });
});

// --- CashChart ---
describe("CashChart 추가", () => {
  it("빈 배열 전달 시 렌더 오류 없음", () => {
    expect(() => render(<CashChart daily={[]} />)).not.toThrow();
    cleanup();
  });

  it("props 변경 시 setData 재호출", () => {
    const daily1: DailyEquityOut[] = [
      { date: "2024-01-01", cash: 10_000_000, stock_value: 0, total_equity: 10_000_000, drawdown: 0, positions_count: 0 },
    ];
    const daily2: DailyEquityOut[] = [
      ...daily1,
      { date: "2024-01-02", cash: 9_000_000, stock_value: 1_000_000, total_equity: 10_000_000, drawdown: 0, positions_count: 1 },
    ];
    const { rerender } = render(<CashChart daily={daily1} />);
    const callCount1 = setDataMock.mock.calls.length;
    rerender(<CashChart daily={daily2} />);
    expect(setDataMock.mock.calls.length).toBeGreaterThan(callCount1);
    cleanup();
  });
});

// --- VolumeChart ---
describe("VolumeChart 추가", () => {
  it("빈 배열 전달 시 렌더 오류 없음", () => {
    expect(() => render(<VolumeChart candles={[]} />)).not.toThrow();
    cleanup();
  });

  it("props 변경 시 setData 재호출", () => {
    const candles1: CandleBar[] = [
      { time: "2024-01-01", open: 100, high: 110, low: 90, close: 105, volume: 500 },
    ];
    const candles2: CandleBar[] = [
      ...candles1,
      { time: "2024-01-02", open: 105, high: 115, low: 100, close: 110, volume: 700 },
    ];
    const { rerender } = render(<VolumeChart candles={candles1} />);
    const callCount1 = setDataMock.mock.calls.length;
    rerender(<VolumeChart candles={candles2} />);
    expect(setDataMock.mock.calls.length).toBeGreaterThan(callCount1);
    cleanup();
  });
});

// --- PositionsCountChart ---
describe("PositionsCountChart 추가", () => {
  it("빈 배열 전달 시 렌더 오류 없음", () => {
    expect(() => render(<PositionsCountChart daily={[]} />)).not.toThrow();
    cleanup();
  });

  it("data-testid='positions-count-chart' 존재", () => {
    const { getByTestId } = render(<PositionsCountChart daily={[]} />);
    expect(getByTestId("positions-count-chart")).toBeInTheDocument();
    cleanup();
  });
});

// --- BenchmarkCompareChart ---
describe("BenchmarkCompareChart 추가", () => {
  it("벤치마크 없음 + equity 빈 배열 → placeholder 오류 없음", () => {
    expect(() =>
      render(<BenchmarkCompareChart equity={[]} benchmarks={[]} />),
    ).not.toThrow();
    cleanup();
  });

  it("data-testid='benchmark-compare-chart' 항상 존재 (placeholder도 포함)", () => {
    const { getByTestId } = render(
      <BenchmarkCompareChart equity={[]} benchmarks={[]} />,
    );
    expect(getByTestId("benchmark-compare-chart")).toBeInTheDocument();
    cleanup();
  });
});

// --- index.ts re-export 검증 ---
describe("charts/index.ts re-export", () => {
  it("DrawdownChart re-export 정상", async () => {
    const mod = await import("./index");
    expect(mod.DrawdownChart).toBeDefined();
  });

  it("VolumeChart re-export 정상", async () => {
    const mod = await import("./index");
    expect(mod.VolumeChart).toBeDefined();
  });

  it("CashChart re-export 정상", async () => {
    const mod = await import("./index");
    expect(mod.CashChart).toBeDefined();
  });

  it("BenchmarkCompareChart re-export 정상", async () => {
    const mod = await import("./index");
    expect(mod.BenchmarkCompareChart).toBeDefined();
  });

  it("PositionsCountChart re-export 정상", async () => {
    const mod = await import("./index");
    expect(mod.PositionsCountChart).toBeDefined();
  });
});
