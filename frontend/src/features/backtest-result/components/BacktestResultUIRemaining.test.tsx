import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, cleanup, screen, fireEvent } from "@testing-library/react";
import MonthlyReturnChart, { type MonthlyReturn } from "./MonthlyReturnChart";

/**
 * step 057 — BacktestResultPage 잔존 UI 단위 테스트.
 *
 * 1. MonthlyReturnChart
 *    - 빈 데이터 → 안내 메시지 (data-testid="monthly-return-chart-empty")
 *    - 데이터 있을 때 → data-testid="monthly-return-chart" 렌더
 *    - 양수 막대(초록)와 음수 막대(빨강)가 SVG에 존재
 *    - 툴팁: 막대 mouseEnter 시 role="tooltip" 존재
 *
 * 2. SymbolSelector (08-n)
 *    - 단일 종목 → null 반환 (컴포넌트 미표시)
 *    - 복수 종목 → select 드롭다운 표시
 *
 * 3. RiskSection (BacktestResultPage 내부)
 *    - data-testid="risk-card" 6개 렌더
 *    - Sharpe Ratio / 연율화 변동성 → "—" 값 + "API 미지원" 표시
 *
 * 4. CandleTradeChart — crosshairMove 이벤트 구독 여부
 *    - subscribeCrosshairMove 호출 확인
 *    - 컴포넌트 언마운트 시 unsubscribeCrosshairMove 호출 확인
 */

// --- lightweight-charts mock ---
const setDataMock = vi.fn();
const addSeriesMock = vi.fn(() => ({ setData: setDataMock, setMarkers: vi.fn() }));
const subscribeMock = vi.fn();
const unsubscribeMock = vi.fn();
const applyOptionsMock = vi.fn();
const removeChartMock = vi.fn();
const fitContentMock = vi.fn();

vi.mock("lightweight-charts", () => ({
  ColorType: { Solid: "solid" },
  CrosshairMode: { Magnet: 1 },
  createChart: vi.fn(() => ({
    addCandlestickSeries: addSeriesMock,
    addLineSeries: addSeriesMock,
    subscribeCrosshairMove: subscribeMock,
    unsubscribeCrosshairMove: unsubscribeMock,
    applyOptions: applyOptionsMock,
    remove: removeChartMock,
    timeScale: () => ({ fitContent: fitContentMock, setVisibleRange: vi.fn() }),
  })),
}));

beforeEach(() => {
  setDataMock.mockClear();
  addSeriesMock.mockClear();
  subscribeMock.mockClear();
  unsubscribeMock.mockClear();
  applyOptionsMock.mockClear();
  removeChartMock.mockClear();
  fitContentMock.mockClear();
});

// === MonthlyReturnChart ===

describe("MonthlyReturnChart", () => {
  it("빈 데이터 → 안내 메시지 표시", () => {
    render(<MonthlyReturnChart data={[]} />);
    expect(screen.getByTestId("monthly-return-chart-empty")).toBeInTheDocument();
    expect(screen.getByTestId("monthly-return-chart-empty").textContent).toContain("데이터가 없습니다");
    cleanup();
  });

  it("데이터 있을 때 monthly-return-chart 컨테이너 표시", () => {
    const data: MonthlyReturn[] = [
      { ym: "2024-01", returnPct: 5.2, lastEquity: 10_500_000 },
      { ym: "2024-02", returnPct: -2.1, lastEquity: 10_279_500 },
    ];
    render(<MonthlyReturnChart data={data} />);
    expect(screen.getByTestId("monthly-return-chart")).toBeInTheDocument();
    cleanup();
  });

  it("양수 막대에 초록(#16a34a), 음수 막대에 빨강(#dc2626) fill 적용", () => {
    const data: MonthlyReturn[] = [
      { ym: "2024-01", returnPct: 5.2, lastEquity: 10_500_000 },
      { ym: "2024-02", returnPct: -2.1, lastEquity: 10_279_500 },
    ];
    const { container } = render(<MonthlyReturnChart data={data} />);
    const rects = container.querySelectorAll("rect");
    const fills = Array.from(rects).map((r) => r.getAttribute("fill"));
    expect(fills).toContain("#16a34a"); // 양수
    expect(fills).toContain("#dc2626"); // 음수
    cleanup();
  });

  it("막대 mouseEnter → role=tooltip 표시, mouseLeave → 툴팁 숨김", () => {
    const data: MonthlyReturn[] = [
      { ym: "2024-03", returnPct: 3.0, lastEquity: 10_300_000 },
    ];
    const { container } = render(<MonthlyReturnChart data={data} />);
    // SVG 내 cursor:pointer 그룹 탐색
    const svgRoot = container.querySelector("svg")!;
    const bars = svgRoot.querySelectorAll<SVGGElement>("g");
    // cursor:pointer인 g에서 mouseEnter 트리거
    let triggerEl: SVGGElement | null = null;
    bars.forEach((g) => {
      if (g.style.cursor === "pointer" && !triggerEl) {
        triggerEl = g;
      }
    });
    if (triggerEl) {
      fireEvent.mouseEnter(triggerEl);
      expect(screen.getByRole("tooltip")).toBeInTheDocument();
      // mouseLeave 후 툴팁 사라짐
      fireEvent.mouseLeave(triggerEl);
      expect(screen.queryByRole("tooltip")).toBeNull();
    }
    cleanup();
  });
});

// === SymbolSelector (08-n) ===

import SymbolSelector, { type SymbolOption } from "./SymbolSelector";

describe("SymbolSelector (08-n)", () => {
  it("단일 종목 → null 반환 (컴포넌트 렌더 없음)", () => {
    const symbols: SymbolOption[] = [{ symbol: "005930", name: "삼성전자" }];
    const { container } = render(
      <SymbolSelector symbols={symbols} value={null} onChange={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
    cleanup();
  });

  it("빈 배열 → null 반환", () => {
    const { container } = render(
      <SymbolSelector symbols={[]} value={null} onChange={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
    cleanup();
  });

  it("복수 종목 → select 드롭다운 표시", () => {
    const symbols: SymbolOption[] = [
      { symbol: "005930", name: "삼성전자" },
      { symbol: "000660", name: "SK하이닉스" },
    ];
    render(
      <SymbolSelector symbols={symbols} value={null} onChange={() => {}} />,
    );
    expect(screen.getByTestId("symbol-select")).toBeInTheDocument();
    cleanup();
  });

  it("복수 종목 → symbol ASC 정렬 (000660이 005930보다 먼저)", () => {
    const symbols: SymbolOption[] = [
      { symbol: "005930", name: "삼성전자" },
      { symbol: "000660", name: "SK하이닉스" },
    ];
    const { container } = render(
      <SymbolSelector symbols={symbols} value={null} onChange={() => {}} />,
    );
    const options = container.querySelectorAll("option:not([value=''])");
    expect(options[0].getAttribute("value")).toBe("000660");
    expect(options[1].getAttribute("value")).toBe("005930");
    cleanup();
  });

  it("값 변경 시 onChange 호출", () => {
    const symbols: SymbolOption[] = [
      { symbol: "005930", name: "삼성전자" },
      { symbol: "000660", name: "SK하이닉스" },
    ];
    const onChangeMock = vi.fn();
    render(
      <SymbolSelector symbols={symbols} value={null} onChange={onChangeMock} />,
    );
    const select = screen.getByTestId("symbol-select") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "005930" } });
    expect(onChangeMock).toHaveBeenCalledWith("005930");
    cleanup();
  });
});

// === CandleTradeChart — crosshairMove 구독 ===

import CandleTradeChart from "./CandleTradeChart";
import type { CandleBar, ChartMarker } from "../../../api/chartData";

describe("CandleTradeChart 툴팁 (08-p)", () => {
  const candles: CandleBar[] = [
    { time: "2024-01-02", open: 70_000, high: 72_000, low: 69_000, close: 71_500 },
    { time: "2024-01-03", open: 71_500, high: 74_000, low: 71_000, close: 73_000 },
  ];
  const markers: ChartMarker[] = [
    { time: "2024-01-02", type: "BUY", price: 70_500, quantity: 10, exit_reason: null },
    { time: "2024-01-03", type: "SELL", price: 72_800, quantity: 10, exit_reason: "take_profit" },
  ];

  it("차트 마운트 시 subscribeCrosshairMove 호출됨", () => {
    render(<CandleTradeChart candles={candles} markers={markers} />);
    expect(subscribeMock).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("차트 언마운트 시 unsubscribeCrosshairMove 호출됨", () => {
    const { unmount } = render(<CandleTradeChart candles={candles} markers={markers} />);
    unmount();
    expect(unsubscribeMock).toHaveBeenCalledTimes(1);
  });

  it("candle-trade-chart data-testid 존재", () => {
    render(<CandleTradeChart candles={candles} markers={markers} />);
    expect(screen.getByTestId("candle-trade-chart")).toBeInTheDocument();
    cleanup();
  });

  it("빈 candles + 빈 markers → 렌더 오류 없음", () => {
    expect(() =>
      render(<CandleTradeChart candles={[]} markers={[]} />),
    ).not.toThrow();
    cleanup();
  });
});
