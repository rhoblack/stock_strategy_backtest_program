import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, cleanup } from "@testing-library/react";
import DrawdownChart from "./DrawdownChart";
import CashChart from "./CashChart";
import PositionsCountChart from "./PositionsCountChart";
import VolumeChart from "./VolumeChart";
import BenchmarkCompareChart from "./BenchmarkCompareChart";
import type { DailyEquityOut } from "../../api/backtests";
import type { CandleBar, EquityPoint } from "../../api/chartData";

/**
 * 차트 컴포넌트 단위 테스트.
 *
 * lightweight-charts는 jsdom에서 canvas 측정 안 됨 → 모듈 mock으로 setData 인자 검증.
 * 검증 포인트:
 *   - 정렬 (date/time ASC) 결정론
 *   - 데이터 변환 (volume 색상, normalized 100, drawdown 음수 등)
 *   - 빈 데이터 / placeholder 처리
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

describe("DrawdownChart", () => {
  it("equity_curve를 time ASC로 정렬해 drawdown 값 setData", () => {
    const equity: EquityPoint[] = [
      { time: "2024-01-03", value: 100, drawdown: -2.5 },
      { time: "2024-01-02", value: 100, drawdown: 0 },
      { time: "2024-01-04", value: 100, drawdown: -1.0 },
    ];
    render(<DrawdownChart equity={equity} />);
    const calls = setDataMock.mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    const last = calls[calls.length - 1][0];
    expect(last.map((p: { time: string }) => p.time)).toEqual([
      "2024-01-02",
      "2024-01-03",
      "2024-01-04",
    ]);
    expect(last.map((p: { value: number }) => p.value)).toEqual([0, -2.5, -1.0]);
    cleanup();
  });

  it("빈 equity_curve는 빈 배열 setData", () => {
    render(<DrawdownChart equity={[]} />);
    const last = setDataMock.mock.calls.at(-1);
    expect(last?.[0]).toEqual([]);
    cleanup();
  });
});

describe("CashChart", () => {
  it("daily_equity를 date ASC로 정렬해 cash 값 setData", () => {
    const daily: DailyEquityOut[] = [
      { date: "2024-02-01", cash: 5_000_000, stock_value: 0, total_equity: 5_000_000, drawdown: 0, positions_count: 0 },
      { date: "2024-01-01", cash: 10_000_000, stock_value: 0, total_equity: 10_000_000, drawdown: 0, positions_count: 0 },
    ];
    render(<CashChart daily={daily} />);
    const last = setDataMock.mock.calls.at(-1)?.[0];
    expect(last?.map((p: { time: string }) => p.time)).toEqual([
      "2024-01-01",
      "2024-02-01",
    ]);
    expect(last?.map((p: { value: number }) => p.value)).toEqual([10_000_000, 5_000_000]);
    cleanup();
  });
});

describe("PositionsCountChart", () => {
  it("positions_count를 date ASC로 정렬해 setData", () => {
    const daily: DailyEquityOut[] = [
      { date: "2024-01-03", cash: 0, stock_value: 0, total_equity: 0, drawdown: 0, positions_count: 3 },
      { date: "2024-01-02", cash: 0, stock_value: 0, total_equity: 0, drawdown: 0, positions_count: 1 },
      { date: "2024-01-04", cash: 0, stock_value: 0, total_equity: 0, drawdown: 0, positions_count: 5 },
    ];
    render(<PositionsCountChart daily={daily} />);
    const last = setDataMock.mock.calls.at(-1)?.[0];
    expect(last?.map((p: { value: number }) => p.value)).toEqual([1, 3, 5]);
    cleanup();
  });
});

describe("VolumeChart", () => {
  it("양봉=빨강 / 음봉=파랑 색상, time ASC 정렬", () => {
    const candles: CandleBar[] = [
      { time: "2024-01-02", open: 100, high: 110, low: 90, close: 105, volume: 1000 }, // 양봉
      { time: "2024-01-03", open: 105, high: 110, low: 95, close: 100, volume: 800 },  // 음봉
      { time: "2024-01-01", open: 95, high: 100, low: 90, close: 95, volume: 500 },    // 동가 → 양봉
    ];
    render(<VolumeChart candles={candles} />);
    const last = setDataMock.mock.calls.at(-1)?.[0];
    expect(last?.map((p: { time: string }) => p.time)).toEqual([
      "2024-01-01",
      "2024-01-02",
      "2024-01-03",
    ]);
    expect(last?.map((p: { color: string }) => p.color)).toEqual([
      "#dc2626", // 양봉 (close == open)
      "#dc2626", // 양봉
      "#1d4ed8", // 음봉
    ]);
    expect(last?.map((p: { value: number }) => p.value)).toEqual([500, 1000, 800]);
    cleanup();
  });

  it("volume이 누락된 봉은 0으로 처리", () => {
    const candles: CandleBar[] = [
      { time: "2024-01-02", open: 100, high: 110, low: 90, close: 105 },
    ];
    render(<VolumeChart candles={candles} />);
    const last = setDataMock.mock.calls.at(-1)?.[0];
    expect(last?.[0].value).toBe(0);
    cleanup();
  });
});

describe("BenchmarkCompareChart", () => {
  it("벤치마크가 없으면 placeholder 메시지 표시 (chart 인스턴스 미생성)", () => {
    const equity: EquityPoint[] = [
      { time: "2024-01-02", value: 10_000_000, drawdown: 0 },
    ];
    const { getByTestId } = render(
      <BenchmarkCompareChart equity={equity} benchmarks={[]} />,
    );
    const el = getByTestId("benchmark-compare-chart");
    expect(el.textContent).toContain("벤치마크 데이터");
    expect(addSeriesMock).not.toHaveBeenCalled();
    cleanup();
  });

  it("벤치마크가 있으면 normalized 100 기준 line 2개 (전략 + KOSPI)", () => {
    const equity: EquityPoint[] = [
      { time: "2024-01-02", value: 10_000_000, drawdown: 0 },
      { time: "2024-01-03", value: 10_500_000, drawdown: 0 },
    ];
    const benchmarks = [
      {
        name: "KOSPI",
        points: [
          { time: "2024-01-02", value: 2500 },
          { time: "2024-01-03", value: 2550 },
        ],
      },
    ];
    render(<BenchmarkCompareChart equity={equity} benchmarks={benchmarks} />);
    // 전략 + KOSPI = 2 series
    expect(addSeriesMock).toHaveBeenCalledTimes(2);
    const allCalls = setDataMock.mock.calls.map((c) => c[0]);
    // 마지막 두 호출: 전략(2025년 100→105), KOSPI(100→102)
    const stratData = allCalls.find(
      (data: Array<{ value: number }>) => data.length === 2 && data[0].value === 100 && data[1].value === 105,
    );
    expect(stratData).toBeDefined();
    const kospiData = allCalls.find(
      (data: Array<{ value: number }>) => data.length === 2 && data[0].value === 100 && Math.abs(data[1].value - 102) < 0.1,
    );
    expect(kospiData).toBeDefined();
    cleanup();
  });

  it("벤치마크 series는 name ASC 정렬 (결정론)", () => {
    const equity: EquityPoint[] = [
      { time: "2024-01-02", value: 10_000_000, drawdown: 0 },
    ];
    const benchmarks = [
      { name: "KOSPI", points: [{ time: "2024-01-02", value: 2500 }] },
      { name: "KOSDAQ", points: [{ time: "2024-01-02", value: 800 }] },
    ];
    render(<BenchmarkCompareChart equity={equity} benchmarks={benchmarks} />);
    // addLineSeries 호출 순서: 전략 → KOSDAQ (ASC) → KOSPI (ASC)
    const titles = addSeriesMock.mock.calls.map((c) => {
      const opts = (c as unknown as Array<{ title?: string }>)[0];
      return opts?.title;
    });
    // 전략은 "전략", 그 다음은 ASC: KOSDAQ, KOSPI
    expect(titles).toEqual(["전략", "KOSDAQ", "KOSPI"]);
    cleanup();
  });
});
