import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Tabs from "../Tabs";
import type { TabItem } from "../Tabs";

/**
 * Tabs 컴포넌트 단위 테스트 (11-m)
 *
 * - 모든 탭 라벨 렌더
 * - active 탭 aria-selected=true
 * - onChange 호출
 * - 비활성 탭 클릭 시 onChange 콜백 전달 값 확인
 *
 * cleanup은 vitest globals + afterEach 자동 수행
 */

const ITEMS: TabItem[] = [
  { label: "요약", value: "summary" },
  { label: "거래", value: "trades" },
  { label: "자산", value: "equity" },
];

describe("Tabs", () => {
  it("모든 탭 라벨이 렌더된다", () => {
    render(<Tabs items={ITEMS} active="summary" onChange={vi.fn()} />);
    expect(screen.getByText("요약")).toBeInTheDocument();
    expect(screen.getByText("거래")).toBeInTheDocument();
    expect(screen.getByText("자산")).toBeInTheDocument();
  });

  it("active 탭 버튼이 aria-selected='true'", () => {
    render(<Tabs items={ITEMS} active="trades" onChange={vi.fn()} />);
    const tradeBtn = screen.getByRole("tab", { name: "거래" });
    expect(tradeBtn).toHaveAttribute("aria-selected", "true");
  });

  it("비활성 탭 버튼은 aria-selected='false'", () => {
    render(<Tabs items={ITEMS} active="summary" onChange={vi.fn()} />);
    const tradeBtn = screen.getByRole("tab", { name: "거래" });
    expect(tradeBtn).toHaveAttribute("aria-selected", "false");
  });

  it("active 탭 버튼 color #2563eb (파랑)", () => {
    render(<Tabs items={ITEMS} active="equity" onChange={vi.fn()} />);
    const equityBtn = screen.getByRole("tab", { name: "자산" });
    expect(equityBtn.style.color).toBe("rgb(37, 99, 235)");
  });

  it("비활성 탭 클릭 시 onChange(value) 호출", () => {
    const handleChange = vi.fn();
    render(<Tabs items={ITEMS} active="summary" onChange={handleChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "거래" }));
    expect(handleChange).toHaveBeenCalledWith("trades");
  });

  it("이미 active인 탭 클릭 시에도 onChange 호출 (상태 관리는 부모 책임)", () => {
    const handleChange = vi.fn();
    render(<Tabs items={ITEMS} active="summary" onChange={handleChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "요약" }));
    expect(handleChange).toHaveBeenCalledWith("summary");
  });

  it("role='tablist' 컨테이너 렌더", () => {
    render(<Tabs items={ITEMS} active="summary" onChange={vi.fn()} data-testid="tabs" />);
    const tablist = screen.getByRole("tablist");
    expect(tablist).toBeInTheDocument();
  });

  it("빈 items 배열 → 탭 없음, 오류 없음", () => {
    render(<Tabs items={[]} active="" onChange={vi.fn()} />);
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });
});
