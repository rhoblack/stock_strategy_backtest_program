/**
 * Playwright E2E API 모킹 헬퍼.
 *
 * page.route()를 사용해 백엔드 없이 E2E 테스트를 실행할 수 있도록
 * 공통 mock 응답 데이터와 라우트 설정 함수를 제공합니다.
 */

import type { Page } from "@playwright/test";

// ─────────────────────────────────────────────────────────────────────────────
// Mock 데이터
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_STRATEGIES = [
  {
    id: 1,
    user_id: 1,
    name: "RSI 반등 전략",
    description: "RSI 과매도 구간 매수",
    strategy_json: {
      entry: [],
      exit_signal: [],
      exit_position: [],
      filters: [],
      universe: {},
    },
    tags: ["RSI", "모멘텀"],
    favorite: false,
    created_at: "2024-01-10T09:00:00",
    updated_at: "2024-01-10T09:00:00",
    deleted_at: null,
    last_backtest: {
      total_return: 12.5,
      mdd: -8.3,
      win_rate: 0.6,
      run_date: "2024-06-15",
    },
  },
  {
    id: 2,
    user_id: 1,
    name: "골든크로스 전략",
    description: "단기 이동평균 골든크로스",
    strategy_json: {
      entry: [],
      exit_signal: [],
      exit_position: [],
      filters: [],
      universe: {},
    },
    tags: ["이동평균"],
    favorite: false,
    created_at: "2024-02-20T09:00:00",
    updated_at: "2024-02-20T09:00:00",
    deleted_at: null,
    last_backtest: {
      total_return: -3.2,
      mdd: -15.1,
      win_rate: 0.45,
      run_date: "2024-05-01",
    },
  },
  {
    id: 3,
    user_id: 1,
    name: "볼린저밴드 돌파",
    description: "상단 밴드 돌파 추세추종",
    strategy_json: {
      entry: [],
      exit_signal: [],
      exit_position: [],
      filters: [],
      universe: {},
    },
    tags: ["볼린저밴드"],
    favorite: true,
    created_at: "2024-03-05T09:00:00",
    updated_at: "2024-03-05T09:00:00",
    deleted_at: null,
    last_backtest: null,
  },
];

export const MOCK_CONDITIONS = [
  {
    type: "rsi_below",
    name: "RSI 과매도",
    category: "entry",
    allowed_in: ["entry", "exit_signal"],
    sentence_template: "RSI가 {threshold} 이하일 때",
    parameters: [
      {
        name: "period",
        label: "기간",
        type: "int",
        default: 14,
        min: 2,
        max: 100,
      },
      {
        name: "threshold",
        label: "임계값",
        type: "float",
        default: 30,
        min: 1,
        max: 99,
      },
    ],
  },
  {
    type: "ma_cross_up",
    name: "골든크로스",
    category: "entry",
    allowed_in: ["entry"],
    sentence_template: "단기 이동평균({short_period})이 장기({long_period})를 상향 돌파",
    parameters: [
      {
        name: "short_period",
        label: "단기 기간",
        type: "int",
        default: 5,
        min: 2,
        max: 50,
      },
      {
        name: "long_period",
        label: "장기 기간",
        type: "int",
        default: 20,
        min: 5,
        max: 200,
      },
    ],
  },
  {
    type: "profit_take",
    name: "익절",
    category: "exit_position",
    allowed_in: ["exit_position"],
    sentence_template: "{profit_pct}% 수익 시 매도",
    parameters: [
      {
        name: "profit_pct",
        label: "익절 비율(%)",
        type: "float",
        default: 10,
        min: 0.1,
        max: 100,
      },
    ],
  },
];

export const MOCK_BACKTEST_STATUS_COMPLETED = {
  id: 42,
  user_id: 1,
  strategy_id: 1,
  run_name: "테스트 백테스트",
  status: "completed",
  progress_pct: 100,
  error_message: null,
  created_at: "2024-06-15T10:00:00",
  started_at: "2024-06-15T10:00:01",
  finished_at: "2024-06-15T10:00:30",
};

export const MOCK_BACKTEST_SUMMARY = {
  run_id: 42,
  status: "completed",
  progress_pct: 100,
  started_at: "2024-06-15T10:00:01",
  finished_at: "2024-06-15T10:00:30",
  error_message: null,
  summary: {
    initial_cash: 10_000_000,
    final_equity: 11_250_000,
    total_return_pct: 12.5,
    annual_return_pct: 14.3,
    mdd_pct: -8.3,
    trade_count: 25,
    open_position_count: 0,
    win_rate: 0.6,
    avg_holding_days: 7.2,
    avg_profit_pct: 5.1,
    avg_loss_pct: -3.2,
    profit_factor: 1.8,
  },
};

export const MOCK_BACKTEST_TRADES = {
  items: [
    {
      trade_group_id: 1,
      symbol: "005930",
      name: "삼성전자",
      entry_date: "2024-02-05",
      entry_price: 73000,
      entry_quantity: 10,
      remaining_quantity: 0,
      fully_closed_at: "2024-02-15",
      final_profit: 12000,
      final_profit_rate: 0.0164,
      executions: [
        {
          execution_date: "2024-02-05",
          execution_type: "BUY",
          price: 73000,
          quantity: 10,
          realized_profit: null,
          exit_reason: null,
        },
        {
          execution_date: "2024-02-15",
          execution_type: "SELL",
          price: 74200,
          quantity: 10,
          realized_profit: 12000,
          exit_reason: "profit_take",
        },
      ],
    },
  ],
  total_count: 1,
};

export const MOCK_DAILY_EQUITY = {
  items: [
    {
      date: "2024-01-02",
      cash: 10_000_000,
      stock_value: 0,
      total_equity: 10_000_000,
      drawdown: 0,
      positions_count: 0,
    },
    {
      date: "2024-01-03",
      cash: 9_270_000,
      stock_value: 730_000,
      total_equity: 10_000_000,
      drawdown: 0,
      positions_count: 1,
    },
  ],
  total_count: 2,
};

export const MOCK_CHART_DATA = {
  run_id: 42,
  symbol: "005930",
  source: "daily_prices",
  downsampled: false,
  candles: [
    {
      time: "2024-01-02",
      open: 72000,
      high: 73500,
      low: 71500,
      close: 73000,
      volume: 10000000,
    },
    {
      time: "2024-01-03",
      open: 73000,
      high: 74000,
      low: 72500,
      close: 73500,
      volume: 8500000,
    },
  ],
  markers: [
    {
      time: "2024-01-02",
      type: "BUY",
      price: 73000,
      quantity: 10,
      exit_reason: null,
    },
    {
      time: "2024-01-03",
      type: "SELL",
      price: 73500,
      quantity: 10,
      exit_reason: "profit_take",
    },
  ],
  equity_curve: [
    {
      time: "2024-01-02",
      value: 10000000,
      drawdown: 0,
    },
    {
      time: "2024-01-03",
      value: 10050000,
      drawdown: 0,
    },
  ],
};

export const MOCK_BACKTEST_LIST_EMPTY = {
  items: [],
  total_count: 0,
  total_pages: 0,
  page: 1,
  page_size: 1,
};

export const MOCK_BACKTEST_LIST_WITH_ITEM = {
  items: [
    {
      id: 42,
      strategy_id: 1,
      run_name: "테스트 백테스트",
      status: "completed",
      progress_pct: 100,
      start_date: "2024-01-02",
      end_date: "2024-12-31",
      initial_cash: 10_000_000,
      created_at: "2024-06-15T10:00:00",
      started_at: "2024-06-15T10:00:01",
      finished_at: "2024-06-15T10:00:30",
      error_message: null,
    },
  ],
  total_count: 1,
  total_pages: 1,
  page: 1,
  page_size: 1,
};

// ─────────────────────────────────────────────────────────────────────────────
// 라우트 설정 함수
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 전략 목록 + 조건 카탈로그 기본 모킹.
 * 대부분의 테스트에서 공통으로 사용합니다.
 */
export async function mockBaseRoutes(page: Page) {
  await page.route("**/api/strategies", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_STRATEGIES),
      });
    } else {
      route.continue();
    }
  });

  await page.route("**/api/conditions", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_CONDITIONS),
    });
  });
}

/**
 * 단일 전략 상세 모킹 (GET /api/strategies/:id).
 */
export async function mockStrategyDetail(page: Page, id: number) {
  const strategy = MOCK_STRATEGIES.find((s) => s.id === id) ?? MOCK_STRATEGIES[0];
  await page.route(`**/api/strategies/${id}`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(strategy),
    });
  });
}

/**
 * 완료된 백테스트 결과 관련 모킹.
 */
export async function mockBacktestResultRoutes(page: Page, runId: number) {
  await page.route(`**/api/backtests/${runId}/status`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_BACKTEST_STATUS_COMPLETED),
    });
  });

  await page.route(`**/api/backtests/${runId}/summary`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_BACKTEST_SUMMARY),
    });
  });

  await page.route(`**/api/backtests/${runId}/trades*`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_BACKTEST_TRADES),
    });
  });

  await page.route(`**/api/backtests/${runId}/daily-equity*`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_DAILY_EQUITY),
    });
  });

  await page.route(`**/api/backtests/${runId}/chart-data*`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_CHART_DATA),
    });
  });
}

/**
 * 전략 비교 페이지용 백테스트 목록 + summary 모킹.
 */
export async function mockCompareRoutes(page: Page) {
  // 전략별 최신 run_id 조회 (백테스트 목록)
  await page.route(`**/api/backtests*`, (route) => {
    const url = route.request().url();
    // status=completed 필터가 있을 때만 run_id 반환
    if (url.includes("status=completed") && url.includes("strategy_id=1")) {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_BACKTEST_LIST_WITH_ITEM),
      });
    } else {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_BACKTEST_LIST_EMPTY),
      });
    }
  });

  // run_id=42 summary
  await page.route(`**/api/backtests/42/summary`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_BACKTEST_SUMMARY),
    });
  });
}
