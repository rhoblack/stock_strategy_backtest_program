import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import BacktestRunPage from "./BacktestRunPage";
import { useStrategies } from "../api/strategies";
import { useCreateBacktest } from "../api/backtests";

vi.mock("../api/strategies", () => ({
  useStrategies: vi.fn(),
}));
vi.mock("../api/backtests", () => ({
  useCreateBacktest: vi.fn(),
}));

const navigateMock = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
});

const mutate = vi.fn();
const useStrategiesMock = vi.mocked(useStrategies);
const useCreateMock = vi.mocked(useCreateBacktest);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BacktestRunPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BacktestRunPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    mutate.mockReset();
    useStrategiesMock.mockReturnValue({
      data: [
        { id: 1, user_id: 1, name: "전략 A", description: "", strategy_json: {}, tags: [], favorite: false, created_at: "", updated_at: "", deleted_at: null },
      ],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useStrategies>);
    mutate.mockImplementation((_payload, opts) => {
      opts?.onSuccess?.({ id: 999 });
    });
    useCreateMock.mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof useCreateBacktest>);
  });

  it("전략 목록을 셀렉트에 표시", () => {
    renderPage();
    expect(screen.getByLabelText("전략 선택")).toBeInTheDocument();
    expect(screen.getByText("전략 A")).toBeInTheDocument();
  });

  it("전략 미선택 시 실행 버튼 disabled", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /백테스트 실행/ })).toBeDisabled();
  });

  it("전략 선택 → 실행 → mutate 호출 + redirect", async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText("전략 선택"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: /백테스트 실행/ }));

    await waitFor(() => expect(mutate).toHaveBeenCalled());
    const payload = mutate.mock.calls[0][0];
    expect(payload.strategy_id).toBe(1);
    expect(payload.universe_config.synthetic_seed).toBe(42);

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/backtests/999"));
  });
});
