import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useStrategies } from "../api/strategies";
import { useCreateBacktest } from "../api/backtests";

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

  const canRun = strategyId !== "" && !createMutation.isPending;

  const onRun = () => {
    if (!canRun) return;
    createMutation.mutate(
      {
        strategy_id: Number(strategyId),
        run_name: runName,
        universe_config: {
          symbol: "GOLDEN",
          position_size_amount: positionSize,
          synthetic_seed: syntheticSeed,
          synthetic_n: syntheticN,
        },
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
