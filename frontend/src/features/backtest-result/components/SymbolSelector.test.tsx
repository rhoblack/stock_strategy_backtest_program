import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SymbolSelector from "./SymbolSelector";

describe("SymbolSelector", () => {
  it("종목이 1개 이하이면 렌더 안 함", () => {
    const { container } = render(
      <SymbolSelector symbols={[]} value={null} onChange={() => {}} />,
    );
    expect(container.firstChild).toBeNull();

    const { container: c2 } = render(
      <SymbolSelector
        symbols={[{ symbol: "GOLDEN" }]}
        value={null}
        onChange={() => {}}
      />,
    );
    expect(c2.firstChild).toBeNull();
  });

  it("symbol ASC 정렬 + 변경 시 onChange 호출", () => {
    const handleChange = vi.fn();
    render(
      <SymbolSelector
        symbols={[
          { symbol: "GOLDEN", name: "골든종목" },
          { symbol: "ALPHA", name: "알파" },
          { symbol: "MEGA" },
        ]}
        value={null}
        onChange={handleChange}
      />,
    );
    const select = screen.getByTestId("symbol-select") as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
    expect(options).toEqual(["", "ALPHA", "GOLDEN", "MEGA"]);

    // 라벨 검증: name 있으면 "심볼 (이름)"
    expect(screen.getByText("ALPHA (알파)")).toBeInTheDocument();
    expect(screen.getByText("GOLDEN (골든종목)")).toBeInTheDocument();
    expect(screen.getByText("MEGA")).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "GOLDEN" } });
    expect(handleChange).toHaveBeenCalledWith("GOLDEN");

    fireEvent.change(select, { target: { value: "" } });
    expect(handleChange).toHaveBeenCalledWith(null);
  });
});
