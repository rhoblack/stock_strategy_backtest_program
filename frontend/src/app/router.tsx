import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import StrategyListPage from "../pages/StrategyListPage";
import StrategyBuilderPage from "../pages/StrategyBuilderPage";
import BacktestRunPage from "../pages/BacktestRunPage";
import BacktestResultPage from "../pages/BacktestResultPage";

const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/strategies" replace /> },
  { path: "/strategies", element: <StrategyListPage /> },
  { path: "/strategies/new", element: <StrategyBuilderPage /> },
  { path: "/strategies/:id", element: <StrategyBuilderPage /> },
  { path: "/backtests/new", element: <BacktestRunPage /> },
  { path: "/backtests/:runId", element: <BacktestResultPage /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
