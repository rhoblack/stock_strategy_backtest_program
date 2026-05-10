import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import StrategyListPage from "../pages/StrategyListPage";
import StrategyBuilderPage from "../pages/StrategyBuilderPage";
import BacktestRunPage from "../pages/BacktestRunPage";
import BacktestResultPage from "../pages/BacktestResultPage";
import StrategyComparePage from "../pages/StrategyComparePage";

const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/strategies" replace /> },
  { path: "/strategies", element: <StrategyListPage /> },
  { path: "/strategies/new", element: <StrategyBuilderPage /> },
  { path: "/strategies/compare", element: <StrategyComparePage /> },
  { path: "/strategies/:id", element: <StrategyBuilderPage /> },
  { path: "/backtests/new", element: <BacktestRunPage /> },
  { path: "/backtests/:runId", element: <BacktestResultPage /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
