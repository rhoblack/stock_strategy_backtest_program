/**
 * step 068 - SurvivalBiasPanel 테스트 (06-l).
 *
 * 설계서 06번 §11.2: 결과 화면 영향 분석
 *   - 신규 상장: N개 종목
 *   - 상장폐지: M개 종목
 *   - 상장폐지 데이터 없는 경우 경고 문구
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import SurvivalBiasPanel from "./SurvivalBiasPanel";

describe("SurvivalBiasPanel", () => {
  it("섹션 aria-label이 렌더된다", () => {
    render(
      <SurvivalBiasPanel
        delistingCount={2}
        estimatedCount={1}
        newListingCount={3}
      />,
    );
    expect(screen.getByRole("region", { name: "생존편향 영향 분석" })).toBeInTheDocument();
  });

  it("상장폐지 건수를 표시한다", () => {
    render(
      <SurvivalBiasPanel
        delistingCount={5}
        estimatedCount={0}
        newListingCount={null}
      />,
    );
    expect(screen.getByTestId("delisting-count")).toHaveTextContent("5건");
  });

  it("신규 상장 건수를 표시한다 (null이 아닌 경우)", () => {
    render(
      <SurvivalBiasPanel
        delistingCount={0}
        estimatedCount={0}
        newListingCount={7}
      />,
    );
    expect(screen.getByTestId("new-listing-count")).toHaveTextContent("7개");
  });

  it("newListingCount=null이면 신규 상장 항목을 표시하지 않는다", () => {
    render(
      <SurvivalBiasPanel
        delistingCount={2}
        estimatedCount={0}
        newListingCount={null}
      />,
    );
    expect(screen.queryByTestId("new-listing-count")).not.toBeInTheDocument();
  });

  it("estimatedCount > 0이면 경고 문구를 표시한다", () => {
    render(
      <SurvivalBiasPanel
        delistingCount={3}
        estimatedCount={2}
        newListingCount={null}
      />,
    );
    expect(screen.getByTestId("survival-bias-warning")).toBeInTheDocument();
    expect(screen.getByTestId("survival-bias-warning")).toHaveTextContent(
      /보수적 추정 매도/,
    );
  });

  it("estimatedCount=0이면 경고 문구를 표시하지 않는다", () => {
    render(
      <SurvivalBiasPanel
        delistingCount={1}
        estimatedCount={0}
        newListingCount={null}
      />,
    );
    expect(screen.queryByTestId("survival-bias-warning")).not.toBeInTheDocument();
  });

  it("delistingCount=0 newListingCount=0이면 영향없음 메시지를 표시한다", () => {
    render(
      <SurvivalBiasPanel
        delistingCount={0}
        estimatedCount={0}
        newListingCount={0}
      />,
    );
    expect(screen.getByText(/영향 없음/)).toBeInTheDocument();
  });

  it("estimatedCount 건수가 괄호 안에 표시된다", () => {
    render(
      <SurvivalBiasPanel
        delistingCount={4}
        estimatedCount={3}
        newListingCount={null}
      />,
    );
    expect(screen.getByText(/추정 종가 ×0.5 적용: 3건/)).toBeInTheDocument();
  });
});
