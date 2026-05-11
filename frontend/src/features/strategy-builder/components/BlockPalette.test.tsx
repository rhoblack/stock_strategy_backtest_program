import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import BlockPalette from "./BlockPalette";
import { useConditions } from "../../../api/conditions";
import { StrategyDraftProvider } from "../state/StrategyDraftContext";
import type { ConditionMeta } from "../../../types/condition";

vi.mock("../../../api/conditions", () => ({
  useConditions: vi.fn(),
}));

const mockUseConditions = vi.mocked(useConditions);

const sample: ConditionMeta[] = [
  {
    type: "price_vs_ma",
    category: "moving_average",
    requires_position: false,
    name: "가격과 이동평균 비교",
    description: "테스트 설명",
    sentence_template: "",
    parameters: [],
    allowed_in: ["entry", "exit_signal", "filters"],
  },
  {
    type: "ma_cross",
    category: "moving_average",
    requires_position: false,
    name: "이동평균 교차",
    description: "",
    sentence_template: "",
    parameters: [],
    allowed_in: ["entry", "exit_signal"],
  },
  {
    type: "take_profit",
    category: "exit_position",
    requires_position: true,
    name: "익절",
    description: "수익 목표 달성 시 매도",
    sentence_template: "",
    parameters: [],
    allowed_in: ["exit_position"],
  },
];

function renderPalette() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StrategyDraftProvider>
        <BlockPalette />
      </StrategyDraftProvider>
    </QueryClientProvider>,
  );
}

describe("BlockPalette", () => {
  beforeEach(() => {
    mockUseConditions.mockReset();
    localStorage.clear();
  });

  it("로딩 중 메시지를 보여준다", () => {
    mockUseConditions.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();
    expect(screen.getByText(/로딩 중/)).toBeInTheDocument();
  });

  it("카테고리별로 조건을 그룹화하여 렌더한다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    expect(screen.getByText("moving_average")).toBeInTheDocument();
    expect(screen.getByText("exit_position")).toBeInTheDocument();
    expect(screen.getByText("가격과 이동평균 비교")).toBeInTheDocument();
    expect(screen.getByText("이동평균 교차")).toBeInTheDocument();
    expect(screen.getByText("익절")).toBeInTheDocument();
  });

  it("API 실패 시 안내", () => {
    mockUseConditions.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as ReturnType<typeof useConditions>);
    renderPalette();
    expect(screen.getByText(/조건 카탈로그 불러오기 실패/)).toBeInTheDocument();
  });

  // ========================================================================
  // 검색 기능 테스트 (step 067 — 01-l)
  // ========================================================================

  it("검색 입력란이 렌더된다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();
    expect(screen.getByRole("searchbox", { name: /조건 검색/ })).toBeInTheDocument();
  });

  it("검색어 입력 시 조건 이름으로 필터링된다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    const input = screen.getByRole("searchbox", { name: /조건 검색/ });
    fireEvent.change(input, { target: { value: "이동평균" } });

    // "이동평균" 검색 시 price_vs_ma(이름에 포함)·ma_cross(이름에 포함)는 보임, 익절은 숨김
    expect(screen.getByText("가격과 이동평균 비교")).toBeInTheDocument();
    expect(screen.getByText("이동평균 교차")).toBeInTheDocument();
    expect(screen.queryByText("익절")).not.toBeInTheDocument();
  });

  it("검색어가 설명(description)에도 적용된다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    const input = screen.getByRole("searchbox", { name: /조건 검색/ });
    // "수익 목표"는 take_profit의 description에 있음
    fireEvent.change(input, { target: { value: "수익 목표" } });

    expect(screen.getByText("익절")).toBeInTheDocument();
    expect(screen.queryByText("가격과 이동평균 비교")).not.toBeInTheDocument();
  });

  it("검색 결과가 없을 때 안내 메시지를 보여준다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    const input = screen.getByRole("searchbox", { name: /조건 검색/ });
    fireEvent.change(input, { target: { value: "존재하지않는조건XYZ" } });

    expect(screen.getByText(/검색 결과가 없습니다/)).toBeInTheDocument();
  });

  // ========================================================================
  // 즐겨찾기 기능 테스트 (step 067 — 01-l)
  // ========================================================================

  it("각 조건에 즐겨찾기 토글 버튼이 렌더된다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    // 3개 조건 각각에 즐겨찾기 버튼이 있어야 함
    const favBtns = screen.getAllByRole("button", { name: /즐겨찾기/ });
    expect(favBtns.length).toBeGreaterThanOrEqual(3);
  });

  it("즐겨찾기 토글 클릭 시 아이콘이 변경된다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    // "가격과 이동평균 비교" 즐겨찾기 버튼 찾기
    const favBtn = screen.getByRole("button", { name: "가격과 이동평균 비교 즐겨찾기" });
    expect(favBtn).toBeInTheDocument();

    // 클릭 후 해제 버튼으로 변경
    fireEvent.click(favBtn);
    expect(screen.getByRole("button", { name: "가격과 이동평균 비교 즐겨찾기 해제" })).toBeInTheDocument();
  });

  it("즐겨찾기 탭 클릭 시 즐겨찾기한 조건만 표시된다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    // "익절"을 즐겨찾기에 추가
    const favBtn = screen.getByRole("button", { name: "익절 즐겨찾기" });
    fireEvent.click(favBtn);

    // 즐겨찾기 탭 클릭 (aria-label="즐겨찾기만 보기" 버튼)
    const favTab = screen.getByRole("tab", { name: "즐겨찾기만 보기" });
    fireEvent.click(favTab);

    // 익절만 보임
    expect(screen.getByText("익절")).toBeInTheDocument();
    expect(screen.queryByText("가격과 이동평균 비교")).not.toBeInTheDocument();
    expect(screen.queryByText("이동평균 교차")).not.toBeInTheDocument();
  });

  it("즐겨찾기 탭에서 즐겨찾기한 조건이 없으면 안내 메시지를 보여준다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    // 즐겨찾기 탭 클릭 (즐겨찾기 없음)
    const favTab = screen.getByRole("tab", { name: "즐겨찾기만 보기" });
    fireEvent.click(favTab);

    expect(screen.getByText(/즐겨찾기한 조건이 없습니다/)).toBeInTheDocument();
  });

  it("즐겨찾기가 localStorage에 영속화된다", () => {
    mockUseConditions.mockReturnValue({
      data: sample,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useConditions>);
    renderPalette();

    // 즐겨찾기 추가
    const favBtn = screen.getByRole("button", { name: "이동평균 교차 즐겨찾기" });
    fireEvent.click(favBtn);

    // localStorage에 저장 확인
    const stored = localStorage.getItem("blockpalette_favorites");
    expect(stored).not.toBeNull();
    const arr = JSON.parse(stored!) as string[];
    expect(arr).toContain("ma_cross");
  });
});
