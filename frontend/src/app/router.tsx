import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import StrategyListPage from "../pages/StrategyListPage";
import StrategyBuilderPage from "../pages/StrategyBuilderPage";

const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/strategies" replace /> },
  { path: "/strategies", element: <StrategyListPage /> },
  { path: "/strategies/new", element: <StrategyBuilderPage /> },
  { path: "/strategies/:id", element: <StrategyBuilderPage /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
