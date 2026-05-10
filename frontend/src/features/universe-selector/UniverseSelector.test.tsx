import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import UniverseSelector, {
  DEFAULT_UNIVERSE_CONFIG,
  type UniverseConfig,
} from "./UniverseSelector";

function setup(overrides: Partial<UniverseConfig> = {}) {
  const handle = vi.fn();
  const value = { ...DEFAULT_UNIVERSE_CONFIG, ...overrides };
  const utils = render(<UniverseSelector value={value} onChange={handle} />);
  return { handle, value, ...utils };
}

describe("UniverseSelector", () => {
  it("기본값: KOSPI / ALL / 6 공통 필터 모두 true", () => {
    setup();
    expect((screen.getByTestId("universe-market") as HTMLSelectElement).value).toBe(
      "KOSPI",
    );
    expect(
      (screen.getByTestId("universe-selection-method") as HTMLSelectElement).value,
    ).toBe("ALL");
    [
      "exclude_etf",
      "exclude_etn",
      "exclude_spac",
      "exclude_preferred",
      "exclude_managed",
      "exclude_halted",
    ].forEach((flag) => {
      const cb = screen.getByTestId(`universe-${flag}`) as HTMLInputElement;
      expect(cb.checked).toBe(true);
    });
  });

  it("시장 변경 시 onChange 호출", () => {
    const { handle } = setup();
    fireEvent.change(screen.getByTestId("universe-market"), {
      target: { value: "KOSDAQ" },
    });
    expect(handle).toHaveBeenCalledWith(
      expect.objectContaining({ market: "KOSDAQ" }),
    );
  });

  it("ETF 제외 토글", () => {
    const { handle } = setup();
    fireEvent.click(screen.getByTestId("universe-exclude_etf"));
    expect(handle).toHaveBeenCalledWith(
      expect.objectContaining({ exclude_etf: false }),
    );
  });

  it("min_market_cap 입력 → 숫자로 전달", () => {
    const { handle } = setup();
    fireEvent.change(screen.getByTestId("universe-min-market-cap"), {
      target: { value: "100000000000" },
    });
    expect(handle).toHaveBeenCalledWith(
      expect.objectContaining({ min_market_cap: 100_000_000_000 }),
    );
  });

  it("min_market_cap 비우면 null", () => {
    const { handle } = setup({ min_market_cap: 1000 });
    fireEvent.change(screen.getByTestId("universe-min-market-cap"), {
      target: { value: "" },
    });
    expect(handle).toHaveBeenCalledWith(
      expect.objectContaining({ min_market_cap: null }),
    );
  });

  it("MARKET_CAP_TOP_N 선택 시 top_n 입력 노출", () => {
    setup({ selection_method: "MARKET_CAP_TOP_N" });
    expect(screen.getByTestId("universe-top-n")).toBeInTheDocument();
  });

  it("ALL 선택 시 top_n 입력 미노출", () => {
    setup({ selection_method: "ALL" });
    expect(screen.queryByTestId("universe-top-n")).not.toBeInTheDocument();
  });

  it("MANUAL 선택 시 종목 코드 입력란 노출", () => {
    setup({ selection_method: "MANUAL" });
    expect(screen.getByTestId("universe-manual-symbols")).toBeInTheDocument();
  });

  it("MANUAL 종목 입력 → 쉼표 분리하여 symbols 배열로 전달", () => {
    const { handle } = setup({ selection_method: "MANUAL", symbols: null });
    fireEvent.change(screen.getByTestId("universe-manual-symbols"), {
      target: { value: "005930, 035720, 000660" },
    });
    // 마지막 onChange 호출에 symbols 배열이 포함되어야 함 (useEffect 동작)
    const calls = handle.mock.calls.map((c) => c[0].symbols);
    expect(calls.at(-1)).toEqual(["005930", "035720", "000660"]);
  });

  it("preview placeholder 메시지 표시 (universe preview API 미구현)", () => {
    setup();
    expect(screen.getByTestId("universe-preview-placeholder")).toBeInTheDocument();
  });
});
