"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LoaderCircle, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  type Config,
  type Run,
  type StrategyDraft,
  type StrategySpec,
  request,
} from "@/lib/api";

type Proposal = {
  status: "supported" | "unsupported";
  explanation: string;
  draft: StrategyDraft | null;
};
export function AIStrategyBuilder({
  config,
  aiConfigured,
  onReview,
  onResult,
  onManual,
}: {
  config: Config;
  aiConfigured: boolean | undefined;
  onReview: (spec: StrategySpec) => void;
  onResult: (run: Run) => void;
  onManual: () => void;
}) {
  const [prompt, setPrompt] = useState(
    "Buy AAPL when its daily 20-day SMA crosses above its 50-day SMA. Sell on the reverse crossover.",
  );
  const [draft, setDraft] = useState<StrategyDraft | null>(null);
  const [edit, setEdit] = useState<StrategySpec | null>(null);
  const [message, setMessage] = useState("");
  const queryClient = useQueryClient();
  const drafts = useQuery({
    queryKey: ["strategy-drafts"],
    queryFn: () => request<StrategyDraft[]>("strategy-drafts"),
  });
  const selectDraft = (value: StrategyDraft) => {
    setDraft(value);
    setEdit(value.specification);
    onReview(value.specification);
    setMessage("");
  };
  const generate = useMutation({
    mutationFn: () => request<Proposal>("strategy-drafts/generate", { prompt }),
    onMutate: () => {
      onManual();
      save.reset();
      approve.reset();
      run.reset();
      setDraft(null);
      setEdit(null);
      setMessage("");
    },
    onSuccess: (result) => {
      if (result.draft) {
        selectDraft(result.draft);
        queryClient.invalidateQueries({ queryKey: ["strategy-drafts"] });
      } else setMessage(result.explanation);
    },
  });
  const save = useMutation({
    mutationFn: () =>
      request<StrategyDraft>("strategy-drafts", {
        specification: edit,
        parent_id: draft?.id,
      }),
    onSuccess: (result) => {
      selectDraft(result);
      queryClient.invalidateQueries({ queryKey: ["strategy-drafts"] });
    },
  });
  const approve = useMutation({
    mutationFn: () =>
      request<StrategyDraft>(`strategy-drafts/${draft?.id}/approve`, {}),
    onSuccess: (result) => {
      selectDraft(result);
      queryClient.invalidateQueries({ queryKey: ["strategy-drafts"] });
    },
  });
  const run = useMutation({
    mutationFn: () => {
      const {
        provider,
        start,
        end,
        initial_cash,
        allocation,
        commission_bps,
        slippage_bps,
      } = config;
      return request<Run>(`strategy-drafts/${draft?.id}/backtests`, {
        provider,
        start,
        end,
        initial_cash,
        allocation,
        commission_bps,
        slippage_bps,
      });
    },
    onSuccess: (result) => {
      onResult(result);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
  const busy =
    generate.isPending || save.isPending || approve.isPending || run.isPending;
  const changed = Boolean(
    draft &&
    edit &&
    JSON.stringify(edit) !== JSON.stringify(draft.specification),
  );
  const error = generate.error || save.error || approve.error || run.error;
  const update = (key: keyof StrategySpec, value: string | number) => {
    if (edit) setEdit({ ...edit, [key]: value });
  };

  return (
    <section
      className="panel mb-6 border-emerald-400/25 p-5 md:p-6"
      aria-labelledby="ai-heading"
    >
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2
            id="ai-heading"
            className="flex items-center gap-2 text-lg font-semibold"
          >
            <Sparkles size={19} className="text-emerald-300" /> AI strategy
            builder
          </h2>
          <p className="mt-2 text-xs leading-5 text-slate-400">
            Describe your idea. Review the rules. Approve a version, then
            backtest it.
          </p>
        </div>
        <span className="rounded-full bg-emerald-400/10 px-3 py-1 text-xs text-emerald-300">
          Draft → Review → Approve → Backtest
        </span>
      </div>
      {aiConfigured === false && (
        <p
          role="status"
          className="mb-4 rounded-lg border border-amber-300/20 bg-amber-300/5 p-3 text-xs leading-5 text-amber-100"
        >
          AI setup required: add QUANTPILOT_AI_API_KEY securely on the server.
          Saved drafts remain available. Generation uses OpenAI; your idea is
          sent to that provider.
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          generate.mutate();
        }}
      >
        <label htmlFor="strategy-idea">Describe a strategy</label>
        <textarea
          id="strategy-idea"
          className="mt-2 min-h-28 w-full rounded-lg border border-slate-700 bg-[#0b1422] p-3 text-sm leading-6 text-slate-100 focus:outline-2 focus:outline-emerald-400 disabled:opacity-50"
          required
          minLength={10}
          maxLength={4000}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={busy}
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-xl text-xs leading-5 text-slate-500">
            Currently supports one stock or ETF, daily SMA crossover, long only.
            Include the symbol and both periods. Other rules require
            clarification.
          </p>
          <Button type="submit" disabled={busy}>
            {generate.isPending ? (
              <LoaderCircle size={16} className="animate-spin" />
            ) : (
              <Sparkles size={16} />
            )}{" "}
            {generate.isPending ? "Drafting…" : "Generate strategy draft"}
          </Button>
        </div>
      </form>
      <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-slate-800 pt-4">
        <label htmlFor="saved-strategy-version">Saved strategy versions</label>
        <select
          id="saved-strategy-version"
          className="!w-full sm:!w-80"
          disabled={busy}
          value={draft?.id || ""}
          onChange={(e) => {
            const selected = drafts.data?.find((d) => d.id === e.target.value);
            if (selected) {
              selectDraft(selected);
              generate.reset();
              save.reset();
              approve.reset();
              run.reset();
            }
          }}
        >
          <option value="">Select a draft or approved version</option>
          {drafts.data?.map((d) => (
            <option key={d.id} value={d.id}>
              {d.specification.name} · {d.id.slice(0, 6)} ·{" "}
              {d.approved_at ? "Approved" : "Draft"}
            </option>
          ))}
        </select>
      </div>
      {drafts.error && (
        <p role="status" className="mt-3 text-xs text-amber-200">
          Strategy history unavailable: {drafts.error.message}
        </p>
      )}
      {message && (
        <p
          role="status"
          className="mt-4 rounded-lg border border-amber-300/20 p-3 text-sm text-amber-100"
        >
          {message}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200"
        >
          {error.message}
        </p>
      )}
      {draft && edit && (
        <div className="mt-5 rounded-xl border border-slate-700 bg-[#0b1422] p-4 md:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-semibold">Review strategy rules</h3>
            <span className="text-xs text-emerald-300">
              Version {draft.id.slice(0, 8)} ·{" "}
              {changed
                ? "Unsaved changes"
                : draft.approved_at
                  ? "Approved for backtesting"
                  : "Awaiting your approval"}
            </span>
          </div>
          <p className="mb-4 text-sm leading-6 text-slate-400">
            {draft.explanation}
          </p>
          <fieldset
            disabled={busy}
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          >
            <label className="sm:col-span-2">
              Draft name
              <input
                required
                maxLength={100}
                value={edit.name}
                onChange={(e) => update("name", e.target.value)}
              />
            </label>
            <label>
              Draft symbol
              <input
                required
                pattern="[A-Z][A-Z0-9.\-]{0,9}"
                value={edit.symbol}
                onChange={(e) => update("symbol", e.target.value.toUpperCase())}
              />
            </label>
            <label>
              Timeframe
              <input readOnly value="Daily · Long only" />
            </label>
            <label>
              Draft fast SMA
              <input
                type="number"
                min={1}
                max={250}
                value={edit.fast}
                onChange={(e) => update("fast", Number(e.target.value))}
              />
            </label>
            <label>
              Draft slow SMA
              <input
                type="number"
                min={2}
                max={500}
                value={edit.slow}
                onChange={(e) => update("slow", Number(e.target.value))}
              />
            </label>
            <label className="sm:col-span-2">
              Draft description
              <input
                maxLength={1000}
                value={edit.description}
                onChange={(e) => update("description", e.target.value)}
              />
            </label>
          </fieldset>
          <div className="my-4 grid gap-3 text-sm sm:grid-cols-2">
            <div className="rounded-lg border border-slate-800 p-3">
              <span className="eyebrow text-emerald-300">Entry</span>
              <p className="mt-2">
                Buy {edit.symbol} when SMA {edit.fast} crosses above SMA{" "}
                {edit.slow}.
              </p>
            </div>
            <div className="rounded-lg border border-slate-800 p-3">
              <span className="eyebrow text-rose-300">Exit</span>
              <p className="mt-2">
                Sell the position when SMA {edit.fast} crosses below SMA{" "}
                {edit.slow}.
              </p>
            </div>
          </div>
          <p className="mb-4 text-xs leading-5 text-slate-400">
            Signals use completed daily bars and fill at the next open. Choose
            historical data, dates, capital and costs below. Backtests use this
            version’s approved symbol and SMA periods.
          </p>
          <div className="flex flex-wrap gap-3">
            {changed && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  save.reset();
                  generate.reset();
                  approve.reset();
                  run.reset();
                  save.mutate();
                }}
              >
                Save as new draft version
              </Button>
            )}
            <Button
              variant="outline"
              disabled={busy || changed || Boolean(draft.approved_at)}
              onClick={() => {
                generate.reset();
                save.reset();
                approve.reset();
                run.reset();
                approve.mutate();
              }}
            >
              <Check size={15} />
              {draft.approved_at && !changed
                ? "Version approved"
                : "Approve for backtesting"}
            </Button>
            <Button
              disabled={busy || changed || !draft.approved_at}
              onClick={() => {
                generate.reset();
                save.reset();
                approve.reset();
                run.reset();
                run.mutate();
              }}
            >
              {run.isPending && (
                <LoaderCircle size={15} className="animate-spin" />
              )}
              {run.isPending ? "Backtesting…" : "Backtest approved version"}
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setDraft(null);
                setEdit(null);
                setMessage("");
                generate.reset();
                save.reset();
                approve.reset();
                run.reset();
                onManual();
              }}
            >
              Return to manual backtesting
            </Button>
          </div>
          {changed && (
            <p className="mt-3 text-xs text-amber-200">
              Save and approve the new version before backtesting these changes.
              The previous version stays unchanged.
            </p>
          )}
          <details className="mt-4 text-xs text-slate-400">
            <summary className="cursor-pointer">
              Inspect structured rules
            </summary>
            <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950 p-3">
              {JSON.stringify(edit, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </section>
  );
}
