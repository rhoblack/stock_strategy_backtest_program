import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import Card, { SummaryCard, ContainerCard } from "../Card";

/**
 * Card 컴포넌트 단위 테스트 (11-m)
 *
 * SummaryCard: label + value + valueColor
 * ContainerCard: title + children + padding
 *
 * cleanup은 vitest globals + afterEach 자동 수행
 */

describe("SummaryCard", () => {
  it("label이 렌더된다", () => {
    render(<SummaryCard label="총 수익률" value="12.34%" />);
    expect(screen.getByText("총 수익률")).toBeInTheDocument();
  });

  it("value가 렌더된다", () => {
    render(<SummaryCard label="승률" value="65.0%" />);
    expect(screen.getByText("65.0%")).toBeInTheDocument();
  });

  it("valueColor → 해당 색상으로 value 표시", () => {
    render(
      <SummaryCard label="MDD" value="-15.2%" valueColor="#dc2626" data-testid="sc" />,
    );
    const card = screen.getByTestId("sc");
    const valueEl = card.querySelector("div:last-child") as HTMLElement;
    expect(valueEl.style.color).toBe("rgb(220, 38, 38)");
  });

  it("valueColor 미지정 시 색상 없음 (default)", () => {
    render(<SummaryCard label="거래 횟수" value="42" data-testid="sc" />);
    const card = screen.getByTestId("sc");
    const valueEl = card.querySelector("div:last-child") as HTMLElement;
    expect(valueEl.style.color).toBe("");
  });

  it("default export도 SummaryCard와 동일", () => {
    render(<Card label="테스트" value="100" />);
    expect(screen.getByText("테스트")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("ReactNode value (JSX 자식) 렌더", () => {
    render(
      <SummaryCard label="자산" value={<strong>10,000,000원</strong>} />,
    );
    expect(screen.getByText("10,000,000원")).toBeInTheDocument();
  });
});

describe("ContainerCard", () => {
  it("children이 렌더된다", () => {
    render(
      <ContainerCard>
        <p>카드 내용</p>
      </ContainerCard>,
    );
    expect(screen.getByText("카드 내용")).toBeInTheDocument();
  });

  it("title이 있으면 렌더된다", () => {
    render(
      <ContainerCard title="섹션 제목">
        <span>내용</span>
      </ContainerCard>,
    );
    expect(screen.getByText("섹션 제목")).toBeInTheDocument();
  });

  it("title이 없으면 title 영역 렌더 안 됨", () => {
    render(
      <ContainerCard data-testid="cc">
        <span>내용</span>
      </ContainerCard>,
    );
    const card = screen.getByTestId("cc");
    // 자식 요소 수: children 하나뿐 (title div 없음)
    expect(card.children).toHaveLength(1);
  });

  it("padding='lg' → 패딩 20px", () => {
    render(
      <ContainerCard padding="lg" data-testid="cc">
        <span>내용</span>
      </ContainerCard>,
    );
    const card = screen.getByTestId("cc");
    expect(card.style.padding).toBe("20px");
  });

  it("padding='sm' → 패딩 8px", () => {
    render(
      <ContainerCard padding="sm" data-testid="cc">
        <span>내용</span>
      </ContainerCard>,
    );
    const card = screen.getByTestId("cc");
    expect(card.style.padding).toBe("8px");
  });
});
