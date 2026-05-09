/**
 * 공통 axios 인스턴스. Vite dev proxy로 /api → http://localhost:8000.
 */

import axios from "axios";

export const api = axios.create({
  baseURL: "",
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    // 향후 글로벌 에러 처리 자리 (toast 등). 현재는 그대로 전파.
    return Promise.reject(error);
  },
);
