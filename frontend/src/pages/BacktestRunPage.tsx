import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useStrategies } from "../api/strategies";
import { useCreateBacktest } from "../api/backtests";
import UniverseSelector, {
  DEFAULT_UNIVERSE_CONFIG,
  type UniverseConfig,
} from "../features/universe-selector/UniverseSelector";

/**
 * 백테스트 실행 화면 — 전략 선택 + 설정 입력 + 실행 → 결과 페이지로 redirect.
 * dev 모드는 합성 데이터 (synthetic_seed/synthetic_n).
 */
export default function BacktestRunPage() {
  const [params] = useSearchParams();
  const initialStrategyId = params.get("strategy_id");
  const navigate = useNavigate();

  const { data: strategies, isLoading: strategiesLoading } = useStrategies();
  const createMutation = useCreateBacktest();

  const [strategyId, setStrategyId] = useState<number | "">(
    initialStrategyId ? Number(initialStrategyId) : "",
  );
  const [runName, setRunName] = useState("백테스트");
  const [startDate, setStartDate] = useState("2024-01-02");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [initialCash, setInitialCash] = useState(10_000_000);
  const [feeRate, setFeeRate] = useState(0.00015);
  const [taxRate, setTaxRate] = useState(0.0018);
  const [slippage, setSlippage] = useState(0.001);
  const [syntheticSeed, setSyntheticSeed] = useState(42);
  const [syntheticN, setSyntheticN] = useState(90);
  const [positionSize, setPositionSize] = useState(5_000_000);
  // 033 / 11-h: UniverseSelector config — 019 백엔드 활용.
  // dev 모드는 합성 데이터 사용 (universe_config.symbol="GOLDEN") → 토글로 전환.
  const [useSynthetic, setUseSynthetic] = useState(true);
  const [universeConfig, setUniverseConfig] = useState<UniverseConfig>(
    DEFAULT_UNIVERSE_CONFIG,
  );

  const canRun = strategyId !== "" && !createMutation.isPending;

  const onRun = () => {
    if (!canRun) return;
    // dev 모드 (합성)와 UniverseSelector(019) 분기.
    const universePayload: Record<string, unknown> = useSynthetic
      ? {
          symbol: "GOLDEN",
          position_size_amount: positionSize,
          synthetic_seed: syntheticSeed,
          synthetic_n: syntheticN,
        }
      : {
          position_size_amount: positionSize,
          ...universeConfigToPayload(universeConfig),
        };

    createMutation.mutate(
      {
        strategy_id: Number(strategyId),
        run_name: runName,
        universe_config: universePayload,
        start_date: startDate,
        end_date: endDate,
        initial_cash: initialCash,
        fee_rate: feeRate,
        tax_rate: taxRate,
        slippage: slippage,
        tick_rounding: "buy_up_sell_down",
      },
      {
        onSuccess: (run) => {
          navigate(`/backtests/${run.id}`);
        },
      },
    );
  };

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 720 }}>
      <p>
        <Link to="/strategies" style={{ color: "#6b7280" }}>
          ← 전략 목록
        </Link>
      </p>
      <h1 style={{ fontSize: 18, fontWeight: 600 }}>백테스트 실행</h1>
      <p style={{ fontSize: 12, color: "#9ca3af" }}>
        Phase 14 데이터 파이프라인 미구현 — dev 모드는 합성 시계열로 실행합니다.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onRun();
        }}
        style={{ display: "grid", gap: 12, marginTop: 16 }}
      >
        <Field label="전략">
          <select
            aria-label="전략 선택"
            value={String(strategyId)}
            onChange={(e) => setStrategyId(e.target.value ? Number(e.target.value) : "")}
            disabled={strategiesLoading}
            required
          >
            <option value="">전략을 선택하세요</option>
            {strategies?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="실행 이름">
          <input value={runName} onChange={(e) => setRunName(e.target.value)} />
        </Field>

        <Field label="기간 시작">
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </Field>
        <Field label="기간 끝">
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </Field>

        <Field label="초기 자금 (원)">
          <input
            type="number"
            value={initialCash}
            onChange={(e) => setInitialCash(Number(e.target.value))}
          />
        </Field>
        <Field label="종목당 매수 금액 (원)">
          <input
            type="number"
            value={positionSize}
            onChange={(e) => setPositionSize(Number(e.target.value))}
          />
        </Field>

        <Field label="수수료율 (소수)">
          <input
            type="number"
            step="0.00001"
            value={feeRate}
            onChange={(e) => setFeeRate(Number(e.target.value))}
          />
        </Field>
        <Field label="거래세율 (소수)">
          <input
            type="number"
            step="0.0001"
            value={taxRate}
            onChange={(e) => setTaxRate(Number(e.target.value))}
          />
        </Field>
        <Field label="슬리피지 (소수)">
          <input
            type="number"
            step="0.0001"
            value={slippage}
            onChange={(e) => setSlippage(Number(e.target.value))}
          />
        </Field>

        <Field label="유니버스 모드">
          <select
            aria-label="유니버스 모드"
            data-testid="universe-mode"
            value={useSynthetic ? "synthetic" : "real"}
            onChange={(e) => setUseSynthetic(e.target.value === "synthetic")}
          >
            <option value="synthetic">합성 데이터 (dev)</option>
            <option value="real">실제 시장 (UniverseSelector)</option>
          </select>
        </Field>

        {useSynthetic ? (
          <fieldset
            style={{ border: "1px solid #e5e7eb", padding: 12, borderRadius: 6 }}
          >
            <legend style={{ fontSize: 12, color: "#6b7280" }}>합성 데이터 (dev)</legend>
            <Field label="seed">
              <input
                type="number"
                value={syntheticSeed}
                onChange={(e) => setSyntheticSeed(Number(e.target.value))}
              />
            </Field>
            <Field label="일수 N">
              <input
                type="number"
                value={syntheticN}
                onChange={(e) => setSyntheticN(Number(e.target.value))}
              />
            </Field>
          </fieldset>
        ) : (
          <UniverseSelector value={universeConfig} onChange={setUniverseConfig} />
        )}

        <button
          type="submit"
          disabled={!canRun}
          style={{
            padding: "8px 16px",
            background: canRun ? "#2563eb" : "#d1d5db",
            color: "white",
            border: "none",
            borderRadius: 4,
            cursor: canRun ? "pointer" : "not-allowed",
            fontSize: 14,
          }}
        >
          {createMutation.isPending ? "실행 중..." : "백테스트 실행"}
        </button>
        {createMutation.isError && (
          <p style={{ color: "crimson", fontSize: 12 }}>실행 요청 실패</p>
        )}
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
      <span style={{ color: "#374151" }}>{label}</span>
      {children}
    </label>
  );
}

/**
 * UniverseConfig → 백엔드 universe_config payload.
 * - null/빈값은 키 자체를 생략 (백엔드 default 사용).
 * - MANUAL은 symbols 리스트만 전달.
 */
function universeConfigToPayload(cfg: UniverseConfig): Record<string, unknown> {
  const out: Record<string, unknown> = {
    market: cfg.market,
    selection_method: cfg.selection_method,
    exclude_etf: cfg.exclude_etf,
    exclude_etn: cfg.exclude_etn,
    exclude_spac: cfg.exclude_spac,
    exclude_preferred: cfg.exclude_preferred,
    exclude_managed: cfg.exclude_managed,
    exclude_halted: cfg.exclude_halted,
    avg_trading_value_window_days: cfg.avg_trading_value_window_days,
  };
  if (cfg.min_market_cap !== null) out.min_market_cap = cfg.min_market_cap;
  if (cfg.min_avg_trading_value !== null)
    out.min_avg_trading_value = cfg.min_avg_trading_value;
  if (
    (cfg.selection_method === "MARKET_CAP_TOP_N" ||
      cfg.selection_method === "LIQUIDITY_TOP_N") &&
    cfg.top_n !== null
  ) {
    out.top_n = cfg.top_n;
  }
  if (cfg.selection_method === "MANUAL" && cfg.symbols && cfg.symbols.length > 0) {
    out.symbols = cfg.symbols;
  }
  return out;
}
