/**
 * E2E 테스트 — 주요 사용자 플로우 5개 시나리오.
 *
 * 모든 테스트는 page.route()로 API를 모킹합니다.
 * 백엔드 서버 없이 CI 환경에서도 실행 가능합니다.
 *
 * 시나리오:
 *   1. 전략 목록 페이지 조회 + 텍스트 필터 검색
 *   2. 전략 빌더 페이지 접근 + 블록 팔레트 렌더링 확인
 *   3. 백테스트 실행 페이지 — UniverseSelector 렌더링 확인
 *   4. 백테스트 결과 탭 전환 — 요약/거래/자산 탭 순차 확인
 *   5. 전략 비교 페이지 — 전략 슬롯 + 비교 테이블 렌더링 확인
 */

import { test, expect } from "@playwright/test";
import {
  mockBaseRoutes,
  mockStrategyDetail,
  mockBacktestResultRoutes,
  mockCompareRoutes,
} from "./mocks";

// ─────────────────────────────────────────────────────────────────────────────
// 시나리오 1: 전략 목록 페이지 조회 + 검색 필터
// ─────────────────────────────────────────────────────────────────────────────

test("시나리오 1: 전략 목록 조회 + 이름 검색 필터", async ({ page }) => {
  // API 모킹 설정
  await mockBaseRoutes(page);

  // 전략 목록 페이지로 이동
  await page.goto("/strategies");

  // 페이지 컨테이너가 렌더링됨 확인
  await expect(page.getByTestId("strategy-list-page")).toBeVisible();

  // 헤더 타이틀 확인
  await expect(page.getByText("주식 전략 연구소")).toBeVisible();

  // 전략 테이블이 렌더링됨 확인 (3개 전략이 있으므로 테이블 보임)
  await expect(page.getByTestId("strategy-table")).toBeVisible();

  // 3개 전략이 모두 표시됨 확인
  await expect(page.getByText("RSI 반등 전략")).toBeVisible();
  await expect(page.getByText("골든크로스 전략")).toBeVisible();
  await expect(page.getByText("볼린저밴드 돌파")).toBeVisible();

  // 검색 필터 입력창이 있음 확인
  const filterInput = page.getByTestId("strategy-name-filter");
  await expect(filterInput).toBeVisible();

  // "RSI"로 검색하면 해당 전략만 표시됨 확인
  await filterInput.fill("RSI");

  // RSI 전략은 표시됨
  await expect(page.getByText("RSI 반등 전략")).toBeVisible();

  // 총 개수 표시 텍스트에 검색어 포함 확인
  await expect(page.getByText(/검색: "RSI"/)).toBeVisible();

  // 검색어 지우면 전체 복귀
  await filterInput.fill("");
  await expect(page.getByText("골든크로스 전략")).toBeVisible();
  await expect(page.getByText("볼린저밴드 돌파")).toBeVisible();

  // + 새 전략 만들기 링크가 있음 확인
  await expect(page.getByText("+ 새 전략 만들기")).toBeVisible();

  // 전략 비교 링크가 있음 확인
  await expect(page.getByText("전략 비교")).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// 시나리오 2: 전략 빌더 페이지 접근 + 블록 팔레트 렌더링
// ─────────────────────────────────────────────────────────────────────────────

test("시나리오 2: 전략 빌더 페이지 — 블록 팔레트 렌더링 확인", async ({ page }) => {
  // API 모킹 설정
  await mockBaseRoutes(page);
  await mockStrategyDetail(page, 1);

  // 새 전략 빌더 페이지로 이동
  await page.goto("/strategies/new");

  // 블록 팔레트(aside[aria-label="블록 팔레트"])가 렌더링됨 확인
  const palette = page.getByRole("complementary", { name: "블록 팔레트" });
  await expect(palette).toBeVisible();

  // "블록 팔레트" 헤딩이 표시됨
  await expect(page.getByText("블록 팔레트")).toBeVisible();

  // 메타데이터 기반 조건 카탈로그에서 entry 카테고리 조건이 표시됨
  await expect(page.getByText("RSI 과매도")).toBeVisible();
  await expect(page.getByText("골든크로스")).toBeVisible();

  // exit_position 카테고리 조건도 표시됨
  await expect(page.getByText("익절")).toBeVisible();

  // 오류 메시지가 없음 확인
  await expect(page.getByText("조건 카탈로그 불러오기 실패")).not.toBeVisible();

  // 전략 이름 입력 필드가 있음 확인 (StrategyHeader)
  await expect(page.getByPlaceholder(/전략 이름|전략명/)).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// 시나리오 3: 백테스트 실행 페이지 — UniverseSelector 렌더링
// ─────────────────────────────────────────────────────────────────────────────

test("시나리오 3: 백테스트 실행 페이지 — UniverseSelector 렌더링 확인", async ({ page }) => {
  // API 모킹 설정
  await mockBaseRoutes(page);

  // 백테스트 실행 페이지로 이동 (strategy_id=1 파라미터 포함)
  await page.goto("/backtests/new?strategy_id=1");

  // 페이지 제목 확인 (h1 헤딩으로 특정)
  await expect(page.getByRole("heading", { name: "백테스트 실행" })).toBeVisible();

  // 전략 선택 드롭다운이 렌더링됨 확인
  const strategySelect = page.getByRole("combobox", { name: "전략 선택" });
  await expect(strategySelect).toBeVisible();

  // UniverseSelector 필드셋이 렌더링됨 확인 (data-testid="universe-selector")
  await expect(page.getByTestId("universe-selector")).toBeVisible();

  // 유니버스 설정 헤더가 표시됨
  await expect(page.getByText("유니버스 (대상 종목) 설정")).toBeVisible();

  // 시장 선택 드롭다운이 있음 확인 (select, not radio)
  const marketSelect = page.getByTestId("universe-market");
  await expect(marketSelect).toBeVisible();
  await expect(marketSelect).toContainText("코스피 (KOSPI)");
  await expect(marketSelect).toContainText("코스닥 (KOSDAQ)");

  // "합성 데이터" 텍스트가 없음 확인 (제거됨)
  await expect(page.getByText("합성 데이터")).not.toBeVisible();

  // 백테스트 실행 버튼이 있음 확인
  await expect(page.getByRole("button", { name: "백테스트 실행" })).toBeVisible();

  // 전략 목록이 드롭다운에 표시됨 확인
  await expect(strategySelect).toContainText("RSI 반등 전략");
  await expect(strategySelect).toContainText("골든크로스 전략");

  // ETF 제외 체크박스가 있음 확인
  await expect(page.getByTestId("universe-exclude_etf")).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// 시나리오 4: 백테스트 결과 탭 전환
// ─────────────────────────────────────────────────────────────────────────────

test("시나리오 4: 백테스트 결과 — 탭 전환 (요약/거래/자산)", async ({ page }) => {
  const runId = 42;

  // API 모킹 설정
  await mockBacktestResultRoutes(page, runId);

  // 백테스트 결과 페이지로 이동
  await page.goto(`/backtests/${runId}`);

  // 페이지 제목 확인
  await expect(page.getByText(`백테스트 결과 #${runId}`)).toBeVisible();

  // 상태가 completed로 표시됨
  await expect(page.getByTestId("run-status")).toHaveText("completed");

  // 탭 목록이 렌더링됨 확인 (ResultTabs: role="tablist")
  await expect(page.getByRole("tablist")).toBeVisible();

  await expect(page.getByTestId("tab-summary")).toBeVisible();
  await expect(page.getByTestId("tab-trades")).toBeVisible();
  await expect(page.getByTestId("tab-equity")).toBeVisible();
  await expect(page.getByTestId("tab-monthly")).toBeVisible();
  await expect(page.getByTestId("tab-risk")).toBeVisible();
  await expect(page.getByTestId("tab-cash")).toBeVisible();

  // 초기 탭은 요약 탭이 선택됨
  await expect(page.getByTestId("tab-summary")).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // 요약 탭에 백테스트 요약 지표가 표시됨 (총수익률 12.5%)
  await expect(page.getByText(/12\.5/)).toBeVisible();

  // 거래 탭으로 전환
  await page.getByTestId("tab-trades").click();
  await expect(page.getByTestId("tab-trades")).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // 거래 탭에서 삼성전자 거래 데이터가 표시됨
  await expect(page.getByText("삼성전자")).toBeVisible();

  // 자산 탭으로 전환
  await page.getByTestId("tab-equity").click();
  await expect(page.getByTestId("tab-equity")).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // 월별 성과 탭으로 전환
  await page.getByTestId("tab-monthly").click();
  await expect(page.getByTestId("tab-monthly")).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // 리스크 탭으로 전환
  await page.getByTestId("tab-risk").click();
  await expect(page.getByTestId("tab-risk")).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // 자금 관리 탭으로 전환
  await page.getByTestId("tab-cash").click();
  await expect(page.getByTestId("tab-cash")).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// 시나리오 5: 전략 비교 페이지 — 전략 선택 + 비교 테이블
// ─────────────────────────────────────────────────────────────────────────────

test("시나리오 5: 전략 비교 페이지 — 전략 슬롯 + 비교 테이블 렌더링", async ({ page }) => {
  // API 모킹 설정
  await mockBaseRoutes(page);
  await mockCompareRoutes(page);

  // 전략 비교 페이지로 이동
  await page.goto("/strategies/compare");

  // 페이지 컨테이너 확인
  await expect(page.getByTestId("strategy-compare-page")).toBeVisible();

  // 페이지 제목 확인
  await expect(page.getByText("전략 비교")).toBeVisible();

  // "전략을 2~5개 선택하면" 안내 문구 확인
  await expect(page.getByText(/전략을 2~5개 선택/)).toBeVisible();

  // "+ 전략 추가" 버튼이 있음 확인
  await expect(page.getByText("+ 전략 추가")).toBeVisible();

  // 전략 A/B 슬롯 드롭다운이 렌더링됨 (data-testid="compare-left", "compare-right")
  const leftSlot = page.getByTestId("compare-left");
  const rightSlot = page.getByTestId("compare-right");
  await expect(leftSlot).toBeVisible();
  await expect(rightSlot).toBeVisible();

  // 드롭다운에 전략 목록이 표시됨 확인
  await expect(leftSlot).toContainText("RSI 반등 전략");
  await expect(leftSlot).toContainText("골든크로스 전략");

  // 미선택 상태: 안내 메시지가 표시됨 (compare-table 대신 compare-guide)
  await expect(page.getByTestId("compare-guide")).toBeVisible();
  await expect(page.getByText("전략을 2개 이상 선택하세요")).toBeVisible();

  // 왼쪽 슬롯에서 "RSI 반등 전략" 선택
  await leftSlot.selectOption({ label: "RSI 반등 전략" });

  // 오른쪽 슬롯에서 "골든크로스 전략" 선택
  await rightSlot.selectOption({ label: "골든크로스 전략" });

  // 두 전략이 선택되면 compare-guide가 사라지고 비교 테이블이 렌더링됨
  await expect(page.getByTestId("compare-guide")).not.toBeVisible();
  await expect(page.getByTestId("compare-table")).toBeVisible();

  // 비교 테이블에 지표 행이 있음 확인
  await expect(page.getByText("총수익률")).toBeVisible();
  await expect(page.getByText("MDD")).toBeVisible();
  await expect(page.getByText("승률")).toBeVisible();
  await expect(page.getByText("거래횟수")).toBeVisible();

  // 비교 테이블 헤더에 전략 이름이 표시됨
  await expect(page.getByTestId("compare-table")).toContainText("RSI 반등 전략");

  // "전략 목록으로" 뒤로가기 링크가 있음 확인
  await expect(page.getByText("← 전략 목록")).toBeVisible();
});
