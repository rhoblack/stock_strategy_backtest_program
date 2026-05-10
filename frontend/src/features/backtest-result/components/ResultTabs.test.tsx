import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ResultTabs, { RESULT_TABS } from "./ResultTabs";

describe("ResultTabs", () => {
  it("탭 6개 (요약/거래/자산/월별 성과/리스크/자금 관리) 순서대로 표시", () => {
    render(<ResultTabs active="summary" onChange={() => {}} />);
    expect(RESULT_TABS.map((t) => t.label)).toEqual([
      "요약",
      "거래",
      "자산",
      "월별 성과",
      "리스크",
      "자금 관리",
    ]);
    RESULT_TABS.forEach((t) => {
      expect(screen.getByTestId(`tab-${t.key}`)).toHaveTextContent(t.label);
    });
  });

  it("active 탭만 aria-selected=true, 클릭 시 onChange", () => {
    const handle = vi.fn();
    render(<ResultTabs active="trades" onChange={handle} />);
    expect(screen.getByTestId("tab-trades")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("tab-summary")).toHaveAttribute("aria-selected", "false");

    fireEvent.click(screen.getByTestId("tab-cash"));
    expect(handle).toHaveBeenCalledWith("cash");
  });
});
