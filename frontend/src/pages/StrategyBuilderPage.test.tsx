import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StrategyBuilderPage from "./StrategyBuilderPage";

vi.mock("../api/conditions", () => ({
  useConditions: vi.fn(() => ({
    data: [],
    isLoading: false,
    error: null,
  })),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StrategyBuilderPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StrategyBuilderPage", () => {
  it("3열 레이아웃 영역(블록 팔레트 / 전략 조립 / 조건 편집)이 모두 존재한다", () => {
    renderPage();
    expect(screen.getByLabelText("블록 팔레트")).toBeInTheDocument();
    expect(screen.getByLabelText("전략 조립 영역")).toBeInTheDocument();
    expect(screen.getByLabelText("조건 편집 패널")).toBeInTheDocument();
  });

  it("5개 섹션 placeholder를 모두 보여준다", () => {
    renderPage();
    for (const label of [
      "매수 조건",
      "매도 시계열 조건",
      "매도 포지션 조건",
      "필터",
      "자금 관리",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("저장 버튼은 placeholder (disabled)", () => {
    renderPage();
    const btn = screen.getByRole("button", { name: "저장" });
    expect(btn).toBeDisabled();
  });
});
