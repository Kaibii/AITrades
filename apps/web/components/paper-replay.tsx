"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, ShieldCheck, Square, StepForward } from "lucide-react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { type Run, request } from "@/lib/api";

type Replay = {
  id: string;
  status: "paused" | "running" | "suspended" | "completed" | "stopped";
  cursor: number;
  total_bars: number;
  equity: string;
  cash: string;
  quantity: string;
  market_date: string | null;
  specification: { name: string; symbol: string };
  configuration: {
    initial_cash: string;
    limits: Record<string, string | number>;
  };
  history: { date: string; equity: string }[];
  orders: {
    id: string;
    market_date: string;
    side: string;
    status: string;
    quantity: string;
    price: string | null;
    fee: string;
    reason: string | null;
  }[];
  risk_events: { market_date: string | null; reason: string }[];
};
const money = (v: string | number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    Number(v),
  );

export function PaperReplay({ run }: { run: Run | null }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState("");
  const [limits, setLimits] = useState({
    allocation_pct: 10,
    max_position_pct: 25,
    max_order_notional: 2500,
    max_daily_loss_pct: 2,
    max_drawdown_pct: 10,
  });
  const sessions = useQuery({
    queryKey: ["paper-sessions"],
    queryFn: () => request<Replay[]>("paper/sessions"),
    refetchInterval: 5000,
  });
  const accountId = selected || sessions.data?.[0]?.id || "";
  const account = useQuery({
    queryKey: ["paper-session", accountId],
    enabled: Boolean(accountId),
    queryFn: () => request<Replay>(`paper/sessions/${accountId}`),
    refetchInterval: 5000,
  });
  const worker = useQuery({
    queryKey: ["paper-worker"],
    queryFn: () =>
      request<{ worker_recent: boolean; worker_last_seen: string | null }>(
        "paper/status",
      ),
    refetchInterval: 5000,
  });
  const accept = (result: Replay) => {
    setSelected(result.id);
    queryClient.setQueryData(["paper-session", result.id], result);
    queryClient.invalidateQueries({ queryKey: ["paper-sessions"] });
  };
  const create = useMutation({
    mutationFn: () =>
      request<Replay>("paper/sessions", { backtest_id: run?.id, limits }),
    onSuccess: accept,
  });
  const command = useMutation({
    mutationFn: (action: "start" | "pause" | "advance" | "stop") =>
      request<Replay>(
        `paper/sessions/${accountId}/${action}`,
        action === "advance"
          ? { expected_cursor: account.data?.cursor, bars: 100 }
          : {},
      ),
    onSuccess: accept,
  });
  const data = account.data;
  const busy = create.isPending || command.isPending;
  const error =
    create.error ||
    command.error ||
    sessions.error ||
    account.error ||
    worker.error;
  const changeLimit = (field: keyof typeof limits, value: string) =>
    setLimits((l) => ({ ...l, [field]: Number(value) }));
  const fields: [keyof typeof limits, string, number][] = [
    ["allocation_pct", "Replay allocation (%)", 100],
    ["max_position_pct", "Maximum position (%)", 100],
    ["max_order_notional", "Maximum order ($)", 100000000],
    ["max_daily_loss_pct", "Daily loss stop (%)", 100],
    ["max_drawdown_pct", "Drawdown stop (%)", 100],
  ];

  return (
    <section className="panel mb-6 p-5 md:p-6" aria-labelledby="paper-heading">
      <div className="mb-4 flex flex-wrap justify-between gap-3">
        <div>
          <h2
            id="paper-heading"
            className="flex items-center gap-2 text-lg font-semibold"
          >
            <ShieldCheck size={19} className="text-emerald-300" /> Paper
            portfolio replay
          </h2>
          <p className="mt-2 text-xs leading-5 text-slate-400">
            Watch an approved strategy trade through saved historical bars with
            virtual cash and server-enforced limits.
          </p>
        </div>
        <span className="h-fit rounded-full border border-amber-300/25 px-3 py-1 text-xs text-amber-200">
          Historical replay · No brokerage orders
        </span>
      </div>
      <p className="mb-4 text-xs leading-5 text-slate-400">
        This uses recorded historical prices, not current market quotes or
        Alpaca paper fills. Start from an approved-version backtest above.
        Replay allocation can differ from that backtest.
      </p>
      <details
        className="mb-4 rounded-lg border border-slate-700 p-4"
        open={!data}
      >
        <summary className="cursor-pointer text-sm">
          Limits for a new virtual account
        </summary>
        <form
          className="mt-4"
          onSubmit={(e) => {
            e.preventDefault();
            command.reset();
            create.mutate();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {fields.map(([key, label, max]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  required
                  min={key === "max_order_notional" ? 1 : 0.01}
                  max={max}
                  step="0.01"
                  value={limits[key]}
                  onChange={(e) => changeLimit(key, e.target.value)}
                />
              </label>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-slate-500">
              Limits are fixed for each account. New accounts start paused with
              the source backtest’s initial cash, fees and slippage.
            </p>
            <Button type="submit" disabled={busy || !run?.strategy_draft}>
              Create virtual replay account
            </Button>
          </div>
          {!run?.strategy_draft && (
            <p className="mt-3 text-xs text-amber-200">
              Run or reopen a backtest of an approved strategy version to create
              an account.
            </p>
          )}
        </form>
      </details>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <label className="flex flex-wrap items-center gap-3">
          Saved replay accounts
          <select
            aria-label="Saved replay accounts"
            className="!mt-0 !w-full sm:!w-80"
            disabled={busy}
            value={accountId}
            onChange={(e) => {
              setSelected(e.target.value);
              command.reset();
              create.reset();
            }}
          >
            <option value="">Select an account</option>
            {sessions.data?.map((s) => (
              <option value={s.id} key={s.id}>
                {s.specification.symbol} · {s.id.slice(0, 6)} · {s.status}
              </option>
            ))}
          </select>
        </label>
        <span
          role="status"
          className={`text-xs ${worker.data?.worker_recent ? "text-emerald-300" : "text-amber-200"}`}
        >
          {worker.data?.worker_recent
            ? "Replay worker heartbeat received"
            : "No recent worker heartbeat · Manual advance available"}
        </span>
      </div>
      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-red-400/30 p-3 text-sm text-red-200"
        >
          {error.message}
        </p>
      )}
      {data && (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold">{data.specification.name}</h3>
            <span
              className="rounded bg-slate-800 px-3 py-1 text-xs capitalize"
              data-testid="replay-status"
            >
              {data.status}
            </span>
          </div>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-slate-950/40 p-4">
              <p className="text-xs text-slate-400">Virtual equity</p>
              <p className="mt-2 font-mono text-xl">{money(data.equity)}</p>
            </div>
            <div className="rounded-lg bg-slate-950/40 p-4">
              <p className="text-xs text-slate-400">Virtual cash</p>
              <p className="mt-2 font-mono text-xl">{money(data.cash)}</p>
            </div>
            <div className="rounded-lg bg-slate-950/40 p-4">
              <p className="text-xs text-slate-400">
                Adjusted shares · {data.specification.symbol}
              </p>
              <p className="mt-2 font-mono text-xl">
                {Number(data.quantity).toFixed(6)}
              </p>
            </div>
          </div>
          <div className="mb-4">
            <div className="mb-2 flex justify-between gap-3 text-xs text-slate-400">
              <span>Historical date: {data.market_date || "Not started"}</span>
              <span>
                {data.cursor} / {data.total_bars} bars
              </span>
            </div>
            <progress
              aria-label="Replay progress"
              className="h-2 w-full accent-emerald-400"
              value={data.cursor}
              max={data.total_bars}
            />
          </div>
          <div className="mb-4 flex flex-wrap gap-3">
            <Button
              variant="outline"
              disabled={busy || data.status !== "paused"}
              onClick={() => {
                create.reset();
                command.mutate("start");
              }}
            >
              <Play size={15} /> Start automatic replay
            </Button>
            <Button
              variant="outline"
              disabled={busy || data.status !== "running"}
              onClick={() => command.mutate("pause")}
            >
              <Pause size={15} /> Pause replay
            </Button>
            <Button
              variant="outline"
              disabled={busy || data.status !== "paused"}
              onClick={() => {
                create.reset();
                command.mutate("advance");
              }}
            >
              <StepForward size={15} /> Advance 100 bars
            </Button>
            <Button
              variant="outline"
              className="!border-red-400/40 !text-red-200"
              disabled={busy || ["stopped", "completed"].includes(data.status)}
              onClick={() => command.mutate("stop")}
            >
              <Square size={15} /> Emergency stop
            </Button>
          </div>
          <p className="mb-4 text-xs leading-5 text-slate-400">
            Automatic replay advances one historical bar per worker tick
            (normally 5 seconds). Emergency stop blocks new bars and orders
            permanently for this account. Filled orders and positions are
            retained; stopping, suspension, completion and lost connectivity
            never trigger liquidation.
          </p>
          {data.history.length > 1 && (
            <div
              className="mb-4 h-48 w-full"
              role="img"
              aria-label="Virtual replay equity curve"
            >
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={data.history.map((h) => ({
                    date: h.date,
                    equity: Number(h.equity),
                  }))}
                >
                  <XAxis
                    dataKey="date"
                    minTickGap={70}
                    tickFormatter={(v) => String(v).slice(0, 7)}
                  />
                  <YAxis
                    width={65}
                    domain={["auto", "auto"]}
                    tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#101a2a",
                      border: "1px solid #334155",
                    }}
                    formatter={(v) => money(Number(v))}
                  />
                  <Area
                    dataKey="equity"
                    stroke="#34d399"
                    fill="#34d399"
                    fillOpacity={0.1}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
          {!!data.risk_events.length && (
            <div
              role="status"
              className="mb-4 rounded-lg border border-red-400/30 p-4 text-sm text-red-200"
            >
              <p className="font-semibold">Risk events</p>
              {data.risk_events.slice(-5).map((event, i) => (
                <p key={i} className="mt-2 text-xs">
                  {event.market_date || "Worker"} · {event.reason}
                </p>
              ))}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <caption className="mb-2 text-left text-xs text-slate-400">
                Simulated orders · Latest {Math.min(data.orders.length, 50)} of{" "}
                {data.orders.length}
              </caption>
              <thead>
                <tr>
                  {[
                    "Historical date",
                    "Side",
                    "Status",
                    "Quantity",
                    "Fill price",
                    "Fee",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.orders.slice(-50).map((o) => (
                  <tr key={o.id}>
                    <td>{o.market_date}</td>
                    <td
                      className={
                        o.side === "buy" ? "text-emerald-300" : "text-rose-300"
                      }
                    >
                      {o.side}
                    </td>
                    <td title={o.reason || undefined}>{o.status}</td>
                    <td>{Number(o.quantity).toFixed(6)}</td>
                    <td>{o.price ? money(o.price) : "—"}</td>
                    <td>{money(o.fee)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.orders.length && (
              <p className="py-4 text-xs text-slate-500">
                No simulated orders yet. The strategy needs warm-up bars and a
                crossover signal.
              </p>
            )}
          </div>
          <details className="mt-4 text-xs text-slate-400">
            <summary className="cursor-pointer">Account risk limits</summary>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-950 p-3">
              {JSON.stringify(data.configuration.limits, null, 2)}
            </pre>
          </details>
        </>
      )}
    </section>
  );
}
