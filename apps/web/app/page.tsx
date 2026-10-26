"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ChartNoAxesCombined,
  FlaskConical,
  Layers,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { AIStrategyBuilder } from "@/components/ai-strategy-builder";
import { type Config, type Run, request } from "@/lib/api";

const initial: Config = {
  symbol: "AAPL",
  provider: "sample",
  start: "2015-02-17",
  end: "2017-02-16",
  fast: 20,
  slow: 50,
  initial_cash: 10000,
  allocation: 0.95,
  commission_bps: 5,
  slippage_bps: 5,
};
const money = (n: number | null | undefined) =>
  n == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
      }).format(n);
const number = (n: number | null | undefined, suffix = "") =>
  n == null ? "—" : `${n.toFixed(2)}${suffix}`;

export default function Dashboard() {
  const [config, setConfig] = useState(initial);
  const [run, setRun] = useState<Run | null>(null);
  const [draftSelected, setDraftSelected] = useState(false);
  const [tab, setTab] = useState<"equity" | "drawdown">("equity");
  const [loadError, setLoadError] = useState("");
  const queryClient = useQueryClient();
  const capabilities = useQuery({
    queryKey: ["capabilities"],
    queryFn: () =>
      request<{ alpaca_configured: boolean; ai_configured: boolean }>(
        "capabilities",
      ),
  });
  const history = useQuery({
    queryKey: ["runs"],
    queryFn: () =>
      request<Pick<Run, "id" | "configuration" | "created_at">[]>("backtests"),
  });
  const backtest = useMutation({
    mutationFn: (c: Config) => request<Run>("backtests", c),
    onSuccess: (result) => {
      setRun(result);
      setLoadError("");
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
  const loadRun = useMutation({
    mutationFn: (id: string) => request<Run>(`backtests/${id}`),
    onSuccess: (result) => {
      setRun(result);
      setConfig(result.configuration);
      setLoadError("");
    },
    onError: (error) => setLoadError(error.message),
  });
  const update = (key: keyof Config, value: string | number) =>
    setConfig((c) => ({ ...c, [key]: value }));
  const exportRun = () => {
    if (!run) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(run, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `quantpilot-${run.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const metrics = run?.metrics;
  const cards = [
    {
      label: "Total return",
      value: number(metrics?.total_return_pct, "%"),
      note: "After modeled costs",
    },
    {
      label: "Annualized return",
      value: number(metrics?.annualized_return_pct, "%"),
      note: "Calendar-based CAGR",
    },
    {
      label: "Maximum drawdown",
      value: number(metrics?.max_drawdown_pct, "%"),
      note: "Daily close peak to trough",
    },
    {
      label: "Sharpe ratio",
      value: number(metrics?.sharpe_ratio),
      note: "0% risk-free · 252 sessions",
    },
  ];

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[220px_1fr]">
      <aside className="border-b border-slate-800 bg-[#0b1320] p-6 lg:border-r lg:border-b-0">
        <div className="flex items-center gap-2 text-xl font-bold tracking-tight">
          <div className="rounded-lg bg-emerald-400 p-1.5 text-slate-950">
            <ChartNoAxesCombined size={21} />
          </div>
          QuantPilot<span className="text-emerald-400">.</span>
        </div>
        <div className="mt-12 hidden lg:block">
          <div className="eyebrow mb-4">Workspace</div>
          <div className="flex items-center gap-3 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-3 text-sm text-emerald-300">
            <FlaskConical size={18} /> Strategy research
          </div>
        </div>
        <div className="mt-8 hidden text-sm text-slate-500 lg:block">
          <div className="flex items-center gap-3 py-3">
            <Layers size={17} /> SMA crossover v1
          </div>
          <div className="flex items-center gap-3 py-3">
            <ShieldCheck size={17} /> Research only
          </div>
        </div>
        <div className="mt-12 hidden rounded-xl border border-slate-800 p-4 lg:block">
          <div className="mb-2 flex gap-2 text-xs text-emerald-300">
            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-400" /> No
            brokerage connected
          </div>
          <p className="text-xs leading-5 text-slate-500">
            Research workspace. Order execution is unavailable.
          </p>
        </div>
      </aside>
      <main className="min-w-0">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-5 md:px-9">
          <div className="text-xs text-slate-400">
            Workspace <span className="mx-3 text-slate-600">/</span>
            <span className="text-slate-200">Backtesting lab</span>
          </div>
          <span className="rounded-full border border-amber-400/25 bg-amber-400/5 px-3 py-1 text-xs text-amber-200">
            Hypothetical performance
          </span>
        </header>
        <div className="mx-auto max-w-[1500px] p-5 md:p-9">
          <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="eyebrow mb-3 text-emerald-400">
                Research / Backtesting
              </div>
              <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
                Test an idea. Understand the trade-offs.
              </h1>
              <p className="mt-3 text-sm text-slate-400">
                Explore a moving-average crossover against historical prices.
              </p>
            </div>
            <Button variant="outline" disabled={!run} onClick={exportRun}>
              <ArrowDownToLine size={15} /> Export run
            </Button>
          </div>
          <div className="mb-6 flex gap-3 rounded-lg border border-amber-300/20 bg-amber-300/5 px-4 py-3 text-xs leading-5 text-amber-100/85">
            <ShieldCheck size={17} className="mt-0.5 shrink-0" />
            Simulated research results only. No real trades are executed.
            Historical performance does not predict future returns.
          </div>

          <AIStrategyBuilder
            config={config}
            aiConfigured={capabilities.data?.ai_configured}
            onManual={() => setDraftSelected(false)}
            onReview={(spec) => {
              setDraftSelected(true);
              setConfig((c) => ({
                ...c,
                symbol: spec.symbol,
                fast: spec.fast,
                slow: spec.slow,
                provider: spec.symbol === "AAPL" ? c.provider : "alpaca",
              }));
            }}
            onResult={(result) => {
              setRun(result);
              setLoadError("");
            }}
          />

          <section
            className="panel mb-6 p-5 md:p-6"
            aria-labelledby="strategy-heading"
          >
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <h2
                id="strategy-heading"
                className="flex items-center gap-2 font-semibold"
              >
                <Activity size={17} className="text-emerald-400" /> Strategy
                configuration
              </h2>
              <span className="text-xs text-slate-400">
                Long only · Daily bars · Next-open fills
              </span>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!draftSelected) backtest.mutate(config);
              }}
            >
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
                <label className="xl:col-span-2">
                  Historical data
                  <select
                    value={config.provider}
                    onChange={(e) => {
                      const provider = e.target.value as Config["provider"];
                      if (draftSelected) {
                        setConfig((c) => ({ ...c, provider }));
                        return;
                      }
                      setConfig(
                        provider === "sample"
                          ? initial
                          : {
                              ...config,
                              provider,
                              symbol: "SPY",
                              start: "2023-01-01",
                              end: "2024-12-31",
                            },
                      );
                    }}
                  >
                    <option value="sample">Bundled AAPL · 2015–2017</option>
                    <option value="alpaca">Alpaca · IEX daily history</option>
                  </select>
                </label>
                <label>
                  Symbol
                  <input
                    value={config.symbol}
                    readOnly={draftSelected || config.provider === "sample"}
                    pattern="[A-Z][A-Z0-9.\-]{0,9}"
                    required
                    onChange={(e) =>
                      update("symbol", e.target.value.toUpperCase())
                    }
                  />
                </label>
                <label>
                  Initial cash ($)
                  <input
                    type="number"
                    min="100"
                    max="100000000"
                    required
                    value={config.initial_cash}
                    onChange={(e) =>
                      update("initial_cash", Number(e.target.value))
                    }
                  />
                </label>
                <label>
                  Start date
                  <input
                    type="date"
                    required
                    value={config.start}
                    onChange={(e) => update("start", e.target.value)}
                  />
                </label>
                <label>
                  End date
                  <input
                    type="date"
                    required
                    value={config.end}
                    onChange={(e) => update("end", e.target.value)}
                  />
                </label>
                <label>
                  Fast SMA (bars)
                  <input
                    type="number"
                    min="1"
                    max="250"
                    required
                    disabled={draftSelected}
                    value={config.fast}
                    onChange={(e) => update("fast", Number(e.target.value))}
                  />
                </label>
                <label>
                  Slow SMA (bars)
                  <input
                    type="number"
                    min="2"
                    max="500"
                    required
                    disabled={draftSelected}
                    value={config.slow}
                    onChange={(e) => update("slow", Number(e.target.value))}
                  />
                </label>
                <label>
                  Allocation (%)
                  <input
                    type="number"
                    min="1"
                    max="100"
                    required
                    value={Math.round(config.allocation * 100)}
                    onChange={(e) =>
                      update("allocation", Number(e.target.value) / 100)
                    }
                  />
                </label>
                <label>
                  Commission (bps)
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    required
                    value={config.commission_bps}
                    onChange={(e) =>
                      update("commission_bps", Number(e.target.value))
                    }
                  />
                </label>
                <label>
                  Slippage (bps)
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    required
                    value={config.slippage_bps}
                    onChange={(e) =>
                      update("slippage_bps", Number(e.target.value))
                    }
                  />
                </label>
                <div className="flex items-end">
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={
                      draftSelected || backtest.isPending || loadRun.isPending
                    }
                  >
                    {backtest.isPending ? (
                      <LoaderCircle size={16} className="animate-spin" />
                    ) : (
                      <ArrowRight size={16} />
                    )}
                    {backtest.isPending ? "Running…" : "Run backtest"}
                  </Button>
                </div>
              </div>
              {draftSelected && (
                <p className="mt-4 text-xs text-emerald-200">
                  A strategy version is selected. Use the review panel above to
                  approve and backtest it, or choose Return to manual
                  backtesting.
                </p>
              )}
              <p className="mt-4 text-xs leading-5 text-slate-500">
                {config.provider === "sample"
                  ? "Bundled historical sample: AAPL, February 17, 2015 – February 16, 2017. Adjusted prices; no API keys required."
                  : capabilities.data?.alpaca_configured
                    ? "Alpaca keys configured. Daily IEX coverage depends on your data entitlement."
                    : "Alpaca keys are not configured. Add APCA_API_KEY_ID and APCA_API_SECRET_KEY on the server. No sample data will be substituted."}
              </p>
            </form>
            {(backtest.error || loadError) && (
              <p
                role="alert"
                className="mt-4 rounded-lg border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200"
              >
                {backtest.error?.message || loadError}
              </p>
            )}
          </section>

          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold">
                {run
                  ? `${run.configuration.symbol} · Research results`
                  : "Research results"}
              </h2>
              {run && (
                <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-400">
                  SMA {run.configuration.fast} / {run.configuration.slow}
                </span>
              )}
            </div>
            <label className="flex items-center gap-2 text-xs">
              Saved runs
              <select
                aria-label="Saved runs"
                className="!mt-0 !w-48"
                value={run?.id || ""}
                disabled={loadRun.isPending}
                onChange={(e) =>
                  e.target.value && loadRun.mutate(e.target.value)
                }
              >
                <option value="">Select a saved run</option>
                {history.data?.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.configuration.symbol} · {r.configuration.fast}/
                    {r.configuration.slow} · {r.id.slice(0, 6)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {history.error && (
            <p role="status" className="mb-4 text-sm text-amber-200">
              Saved runs unavailable: {history.error.message}
            </p>
          )}
          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map((card) => (
              <article key={card.label} className="panel p-5">
                <h3 className="text-xs text-slate-400">{card.label}</h3>
                <p
                  className={`mt-3 font-mono text-3xl tracking-tight ${card.label === "Total return" && (metrics?.total_return_pct ?? 0) >= 0 && run ? "text-emerald-300" : "text-slate-100"}`}
                >
                  {card.value}
                </p>
                <p className="mt-3 text-[11px] text-slate-500">{card.note}</p>
              </article>
            ))}
          </div>

          <section
            className="panel mb-6 p-5 md:p-6"
            aria-labelledby="chart-heading"
          >
            <div className="mb-5 flex flex-wrap justify-between gap-4">
              <div>
                <h2 id="chart-heading" className="font-semibold">
                  {tab === "equity" ? "Equity growth" : "Portfolio drawdown"}
                </h2>
                <p className="mt-1 text-xs text-slate-400">
                  {run
                    ? `${run.data.first_date} → ${run.data.last_date} · ${run.data.bars} daily bars`
                    : "Run a backtest to explore the equity curve"}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  aria-pressed={tab === "equity"}
                  className={
                    tab === "equity"
                      ? "!border-emerald-400/50 !text-emerald-300"
                      : ""
                  }
                  onClick={() => setTab("equity")}
                >
                  Equity
                </Button>
                <Button
                  variant="outline"
                  aria-pressed={tab === "drawdown"}
                  className={
                    tab === "drawdown"
                      ? "!border-emerald-400/50 !text-emerald-300"
                      : ""
                  }
                  onClick={() => setTab("drawdown")}
                >
                  Drawdown
                </Button>
              </div>
            </div>
            {run ? (
              <>
                <div className="mb-4 flex gap-5 text-xs text-slate-400">
                  <span className="text-emerald-300">● Strategy</span>
                  {tab === "equity" && (
                    <span className="text-slate-400">
                      ● Buy & hold benchmark · before costs
                    </span>
                  )}
                </div>
                <div
                  className="h-[320px] w-full"
                  role="img"
                  aria-label={
                    tab === "equity"
                      ? "Strategy and buy-and-hold equity over time"
                      : "Strategy percentage drawdown over time"
                  }
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={run.equity_curve}
                      margin={{ top: 8, right: 8, bottom: 4, left: 4 }}
                    >
                      <defs>
                        <linearGradient
                          id="equity-fill"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor="#34d399"
                            stopOpacity={0.22}
                          />
                          <stop
                            offset="100%"
                            stopColor="#34d399"
                            stopOpacity={0}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid
                        stroke="#233147"
                        vertical={false}
                        strokeDasharray="3 5"
                      />
                      <XAxis
                        dataKey="date"
                        minTickGap={60}
                        tickFormatter={(v) => String(v).slice(0, 7)}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        width={70}
                        domain={
                          tab === "equity" ? ["auto", "auto"] : ["auto", 0]
                        }
                        tickFormatter={(v) =>
                          tab === "equity"
                            ? `$${(Number(v) / 1000).toFixed(1)}k`
                            : `${v}%`
                        }
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#101a2a",
                          border: "1px solid #334155",
                          borderRadius: 8,
                        }}
                        formatter={(value) =>
                          tab === "equity"
                            ? money(Number(value))
                            : number(Number(value), "%")
                        }
                      />
                      <Area
                        type="linear"
                        dataKey={tab === "equity" ? "equity" : "drawdown_pct"}
                        name="Strategy"
                        stroke="#34d399"
                        fill="url(#equity-fill)"
                        strokeWidth={2}
                        isAnimationActive={false}
                      />
                      {tab === "equity" && (
                        <Line
                          type="linear"
                          dataKey="benchmark"
                          name="Buy & hold"
                          stroke="#8193ad"
                          strokeWidth={1.5}
                          strokeDasharray="4 4"
                          dot={false}
                          isAnimationActive={false}
                        />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </>
            ) : (
              <div className="flex h-[300px] flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 text-center">
                <ChartNoAxesCombined
                  className="mb-4 text-slate-600"
                  size={40}
                />
                <h3 className="text-sm text-slate-300">
                  Your research starts here
                </h3>
                <p className="mt-2 max-w-sm px-4 text-xs leading-5 text-slate-500">
                  Choose your parameters and run a backtest. Performance appears
                  only after a successful simulation.
                </p>
              </div>
            )}
          </section>

          {run && (
            <>
              <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ["Final equity", money(metrics?.final_equity)],
                  ["Realized P/L", money(metrics?.realized_pnl)],
                  ["Unrealized P/L", money(metrics?.unrealized_pnl)],
                  [
                    "Win rate · completed trades",
                    number(metrics?.win_rate_pct, "%"),
                  ],
                  ["Completed trades", metrics?.completed_trades],
                  ["Open adjusted shares", number(metrics?.open_quantity)],
                  ["Fees paid", money(metrics?.fees_paid)],
                  ["Cash remaining", money(metrics?.cash)],
                ].map(([label, value]) => (
                  <div className="panel p-4" key={label}>
                    <div className="text-xs text-slate-400">{label}</div>
                    <div className="mt-2 font-mono text-lg">{value ?? "—"}</div>
                  </div>
                ))}
              </div>
              <section className="panel mb-6 overflow-hidden">
                <div className="flex justify-between border-b border-slate-800 p-5">
                  <h2 className="font-semibold">Completed trades</h2>
                  <span className="text-xs text-slate-400">
                    {run.trades.length} round trips · hypothetical fills
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr>
                        {[
                          "Entry date",
                          "Exit date",
                          "Quantity",
                          "Entry price",
                          "Exit price",
                          "Net P/L",
                          "Return",
                        ].map((h) => (
                          <th key={h}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {run.trades.map((t, i) => (
                        <tr key={i}>
                          <td>{t.entry_date}</td>
                          <td>{t.exit_date}</td>
                          <td>{t.quantity.toFixed(4)}</td>
                          <td>{money(t.entry_price)}</td>
                          <td>{money(t.exit_price)}</td>
                          <td
                            className={
                              t.net_pnl >= 0
                                ? "text-emerald-300"
                                : "text-rose-300"
                            }
                          >
                            {money(t.net_pnl)}
                          </td>
                          <td>{number(t.return_pct, "%")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!run.trades.length && (
                    <p className="p-8 text-center text-sm text-slate-400">
                      No completed round trips. Any open position remains marked
                      at the final close.
                    </p>
                  )}
                </div>
              </section>
              <details className="panel p-5">
                <summary className="cursor-pointer text-sm font-semibold">
                  Data provenance & simulation assumptions
                </summary>
                <div className="mt-4 space-y-3 text-xs leading-6 text-slate-400">
                  <p>
                    {run.data.source}. {run.data.adjustment}
                  </p>
                  <p>{run.data.license_note}</p>
                  <ul className="list-disc space-y-1 pl-5">
                    {run.assumptions.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                  <p className="break-all font-mono text-[10px]">
                    Engine: {run.engine_version} · Dataset SHA-256:{" "}
                    {run.data.version}
                  </p>
                </div>
              </details>
            </>
          )}
          <footer className="mt-8 flex flex-wrap justify-between gap-3 border-t border-slate-800 pt-5 text-[11px] text-slate-500">
            <span>QuantPilot · Local research workspace</span>
            <span>
              Research, backtesting, understanding. Live trading unavailable.
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}
