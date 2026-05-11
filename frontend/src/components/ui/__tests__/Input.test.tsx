import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import Input from "../Input";

/**
 * Input 컴포넌트 단위 테스트 (11-m)
 *
 * - label 렌더
 * - error 메시지 표시 + 테두리 빨강
 * - onChange 콜백 호출
 * - placeholder
 * - disabled 상태
 */

describe("Input", () => {
  it("label이 있으면 렌더된다", () => {
    render(<Input label="종목명" value="" onChange={vi.fn()} />);
    expect(screen.getByText("종목명")).toBeInTheDocument();
    cleanup();
  });

  it("label이 없으면 label 요소 렌더 안 됨", () => {
    render(<Input value="" onChange={vi.fn()} />);
    expect(screen.queryByRole("label")).toBeNull();
    cleanup();
  });

  it("error prop → role=alert 메시지 표시", () => {
    render(<Input value="" onChange={vi.fn()} error="필수 입력 항목입니다" />);
    expect(screen.getByRole("alert")).toHaveTextContent("필수 입력 항목입니다");
    cleanup();
  });

  it("error가 없으면 alert 렌더 안 됨", () => {
    render(<Input value="" onChange={vi.fn()} />);
    expect(screen.queryByRole("alert")).toBeNull();
    cleanup();
  });

  it("error 있을 때 input border-color 빨강 (#dc2626)", () => {
    render(<Input value="" onChange={vi.fn()} error="오류" data-testid="inp" />);
    const inp = screen.getByTestId("inp");
    expect(inp.style.borderColor).toBe("rgb(220, 38, 38)");
    cleanup();
  });

  it("onChange 호출 시 콜백에 문자열 전달", () => {
    const handleChange = vi.fn();
    render(<Input value="" onChange={handleChange} data-testid="inp" />);
    fireEvent.change(screen.getByTestId("inp"), { target: { value: "삼성전자" } });
    expect(handleChange).toHaveBeenCalledWith("삼성전자");
    cleanup();
  });

  it("placeholder 속성 전달", () => {
    render(<Input value="" onChange={vi.fn()} placeholder="종목 코드 입력" data-testid="inp" />);
    expect(screen.getByTestId("inp")).toHaveAttribute("placeholder", "종목 코드 입력");
    cleanup();
  });

  it("disabled=true → input 비활성화", () => {
    render(<Input value="비활성" onChange={vi.fn()} disabled data-testid="inp" />);
    const inp = screen.getByTestId("inp") as HTMLInputElement;
    expect(inp.disabled).toBe(true);
    cleanup();
  });

  it("type='number' → input type 속성 전달", () => {
    render(<Input type="number" value={5} onChange={vi.fn()} data-testid="inp" />);
    const inp = screen.getByTestId("inp") as HTMLInputElement;
    expect(inp.type).toBe("number");
    cleanup();
  });

  it("id prop → label htmlFor 연결", () => {
    render(<Input id="my-input" label="라벨" value="" onChange={vi.fn()} />);
    const label = screen.getByText("라벨") as HTMLLabelElement;
    expect(label.htmlFor).toBe("my-input");
    cleanup();
  });
});
