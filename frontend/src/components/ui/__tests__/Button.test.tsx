import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import Button from "../Button";

/**
 * Button 컴포넌트 단위 테스트 (11-m)
 *
 * - variant별 스타일
 * - loading state → 클릭 불가 + 스피너
 * - disabled state
 * - onClick 호출
 */

describe("Button", () => {
  it("children 텍스트가 렌더된다", () => {
    render(<Button>저장</Button>);
    expect(screen.getByText("저장")).toBeInTheDocument();
    cleanup();
  });

  it("primary variant: 파랑 배경색 적용", () => {
    render(<Button variant="primary" data-testid="btn">확인</Button>);
    const btn = screen.getByTestId("btn");
    // 인라인 스타일로 배경색 확인
    expect(btn.style.background).toBe("rgb(37, 99, 235)");
    cleanup();
  });

  it("secondary variant: 흰색 배경 + 테두리", () => {
    render(<Button variant="secondary" data-testid="btn">취소</Button>);
    const btn = screen.getByTestId("btn");
    expect(btn.style.background).toBe("rgb(255, 255, 255)");
    cleanup();
  });

  it("danger variant: 빨간 배경색", () => {
    render(<Button variant="danger" data-testid="btn">삭제</Button>);
    const btn = screen.getByTestId("btn");
    expect(btn.style.background).toBe("rgb(220, 38, 38)");
    cleanup();
  });

  it("ghost variant: 투명 배경", () => {
    render(<Button variant="ghost" data-testid="btn">닫기</Button>);
    const btn = screen.getByTestId("btn");
    expect(btn.style.background).toBe("transparent");
    cleanup();
  });

  it("size sm: font-size 12px", () => {
    render(<Button size="sm" data-testid="btn">작은 버튼</Button>);
    const btn = screen.getByTestId("btn");
    expect(btn.style.fontSize).toBe("12px");
    cleanup();
  });

  it("size lg: font-size 15px", () => {
    render(<Button size="lg" data-testid="btn">큰 버튼</Button>);
    const btn = screen.getByTestId("btn");
    expect(btn.style.fontSize).toBe("15px");
    cleanup();
  });

  it("loading=true → button disabled, opacity 0.5", () => {
    render(<Button loading data-testid="btn">로딩 중</Button>);
    const btn = screen.getByTestId("btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.style.opacity).toBe("0.5");
    cleanup();
  });

  it("loading=true → 스피너 span 렌더 (aria-hidden)", () => {
    render(<Button loading data-testid="btn">로딩</Button>);
    const spinner = document.querySelector("[aria-hidden='true']");
    expect(spinner).not.toBeNull();
    cleanup();
  });

  it("disabled=true → button disabled, 클릭 콜백 호출 안 됨", () => {
    const handleClick = vi.fn();
    render(<Button disabled onClick={handleClick} data-testid="btn">비활성</Button>);
    const btn = screen.getByTestId("btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(handleClick).not.toHaveBeenCalled();
    cleanup();
  });

  it("onClick 클릭 시 콜백 호출", () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick} data-testid="btn">클릭</Button>);
    fireEvent.click(screen.getByTestId("btn"));
    expect(handleClick).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("type='submit' 속성 전달", () => {
    render(<Button type="submit" data-testid="btn">제출</Button>);
    const btn = screen.getByTestId("btn") as HTMLButtonElement;
    expect(btn.type).toBe("submit");
    cleanup();
  });
});
