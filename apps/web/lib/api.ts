export type Config = {
  symbol: string;
  provider: "sample" | "alpaca";
  start: string;
  end: string;
  fast: number;
  slow: number;
  initial_cash: number;
  allocation: number;
  commission_bps: number;
  slippage_bps: number;
};
export type Run = {
  id: string;
  created_at: string;
  engine_version: string;
  strategy_version: string;
  strategy_draft?: {
    id: string;
    approved_at: string;
    origin: string;
    specification: StrategySpec;
  };
  configuration: Config;
  assumptions: string[];
  data: {
    source: string;
    version: string;
    adjustment: string;
    license_note: string;
    bars: number;
    first_date: string;
    last_date: string;
  };
  metrics: Record<string, number | null>;
  equity_curve: {
    date: string;
    equity: number;
    benchmark: number;
    drawdown_pct: number;
  }[];
  trades: {
    entry_date: string;
    exit_date: string;
    quantity: number;
    entry_price: number;
    exit_price: number;
    net_pnl: number;
    return_pct: number;
    holding_bars: number;
  }[];
};

export type StrategySpec = {
  name: string;
  description: string;
  symbol: string;
  timeframe: "1Day";
  indicator: "SMA";
  fast: number;
  slow: number;
  entry: "fast_crosses_above_slow";
  exit: "fast_crosses_below_slow";
  direction: "long_only";
};
export type StrategyDraft = {
  id: string;
  parent_id: string | null;
  created_at: string;
  approved_at: string | null;
  origin: "ai" | "manual";
  prompt: string | null;
  explanation: string;
  specification: StrategySpec;
};
export async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    `/api/${path}`,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Invalid configuration. Check dates, symbol and indicator periods.",
    );
  return data;
}
