"use client";
import { useState, useMemo } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from "recharts";
import { tradingApi } from "../utils/api";

// ─── Types ────────────────────────────────────────────────────────────────────
interface BacktestSummary {
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  net_pnl: number;
  max_dd: number;
  profit_factor: number;
  sharpe: number;
  calmar: number;
  max_consec_wins: number;
  max_consec_losses: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
}

interface EquityPoint { time: string; equity: number; }
interface MonthlyRow {
  month: string;
  end_equity: number;
  min_equity: number;
  max_equity: number;
  month_pnl: number;
}
interface TradeRow {
  time: string;
  direction: string;
  entry: number;
  exit: number;
  lot: number;
  pnl: number;
  result: string;
}
interface BacktestResults {
  summary: BacktestSummary;
  equity_curve: EquityPoint[];
  monthly: MonthlyRow[];
  trades: TradeRow[];
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const S = {
  card: {
    background: "rgba(22,24,29,0.95)",
    border: "1px solid rgba(212,175,55,0.12)",
    borderRadius: 12,
    padding: 24,
    backdropFilter: "blur(8px)",
  } as React.CSSProperties,
  cardHeader: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 2,
    textTransform: "uppercase" as const,
    color: "#D4AF37",
    marginBottom: 20,
    display: "flex",
    alignItems: "center",
    gap: 8,
  } as React.CSSProperties,
  label: { fontSize: 11, color: "#666", fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: 1 },
  input: {
    background: "#0D0E12",
    border: "1px solid rgba(255,255,255,0.08)",
    padding: "10px 14px",
    color: "#E0E0E0",
    borderRadius: 8,
    fontSize: 13,
    width: "100%",
    outline: "none",
    transition: "border-color 0.2s",
    boxSizing: "border-box" as const,
  } as React.CSSProperties,
};

// ─── Stat Card ────────────────────────────────────────────────────────────────
const StatCard = ({
  label,
  value,
  sub,
  color = "#E0E0E0",
  icon,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  icon?: string;
}) => (
  <div
    style={{
      ...S.card,
      padding: "20px 22px",
      position: "relative",
      overflow: "hidden",
    }}
  >
    <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: color, opacity: 0.6 }} />
    <div style={S.label}>{icon && <span style={{ marginRight: 4 }}>{icon}</span>}{label}</div>
    <div style={{ fontSize: 26, fontWeight: 800, color, marginTop: 8, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: "#555", marginTop: 4 }}>{sub}</div>}
  </div>
);

// ─── Custom Tooltip ───────────────────────────────────────────────────────────
const EquityTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const val = payload[0]?.value ?? 0;
  return (
    <div style={{ background: "#16181D", border: "1px solid rgba(212,175,55,0.3)", borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ fontSize: 11, color: "#888", marginBottom: 4 }}>{new Date(label).toLocaleString()}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: val >= 0 ? "#00FF85" : "#FF4D4D" }}>
        ${val.toFixed(2)}
      </div>
    </div>
  );
};

const MonthlyTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const val = payload[0]?.value ?? 0;
  return (
    <div style={{ background: "#16181D", border: "1px solid rgba(212,175,55,0.3)", borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ fontSize: 11, color: "#888", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: val >= 0 ? "#00FF85" : "#FF4D4D" }}>
        {val >= 0 ? "+" : ""}${val.toFixed(2)}
      </div>
    </div>
  );
};

// ─── Trade Table ──────────────────────────────────────────────────────────────
const TradeLogTable = ({ trades }: { trades: TradeRow[] }) => {
  const [page, setPage] = useState(0);
  const PAGE = 20;
  const total = trades.length;
  const slice = trades.slice(page * PAGE, (page + 1) * PAGE);
  const pages = Math.ceil(total / PAGE);

  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              {["Time", "Direction", "Entry", "Exit", "Lot", "PnL", "Result"].map((h) => (
                <th
                  key={h}
                  style={{ padding: "10px 12px", textAlign: "left", color: "#555", fontWeight: 700, fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.map((t, i) => (
              <tr
                key={i}
                style={{
                  borderBottom: "1px solid rgba(255,255,255,0.03)",
                  background: i % 2 === 0 ? "rgba(255,255,255,0.01)" : "transparent",
                  transition: "background 0.15s",
                }}
              >
                <td style={{ padding: "10px 12px", color: "#666", fontFamily: "monospace" }}>
                  {new Date(t.time).toLocaleDateString()}
                </td>
                <td style={{ padding: "10px 12px" }}>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "2px 8px",
                      borderRadius: 4,
                      fontSize: 10,
                      fontWeight: 700,
                      letterSpacing: 0.5,
                      background: t.direction === "BUY" ? "rgba(0,255,133,0.12)" : "rgba(255,77,77,0.12)",
                      color: t.direction === "BUY" ? "#00FF85" : "#FF4D4D",
                    }}
                  >
                    {t.direction}
                  </span>
                </td>
                <td style={{ padding: "10px 12px", color: "#AAA", fontFamily: "monospace" }}>${t.entry.toFixed(2)}</td>
                <td style={{ padding: "10px 12px", color: "#AAA", fontFamily: "monospace" }}>${t.exit.toFixed(2)}</td>
                <td style={{ padding: "10px 12px", color: "#888" }}>{t.lot}</td>
                <td style={{ padding: "10px 12px", fontWeight: 600, fontFamily: "monospace", color: t.pnl >= 0 ? "#00FF85" : "#FF4D4D" }}>
                  {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
                </td>
                <td style={{ padding: "10px 12px" }}>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "2px 8px",
                      borderRadius: 4,
                      fontSize: 10,
                      fontWeight: 700,
                      background: t.result === "WIN" ? "rgba(0,255,133,0.1)" : "rgba(255,77,77,0.1)",
                      color: t.result === "WIN" ? "#00FF85" : "#FF4D4D",
                    }}
                  >
                    {t.result}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 16 }}>
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{ ...btnSmall, opacity: page === 0 ? 0.3 : 1 }}
          >
            ← Prev
          </button>
          <span style={{ color: "#666", fontSize: 12, padding: "6px 0" }}>
            Page {page + 1} of {pages} ({total} trades)
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
            disabled={page === pages - 1}
            style={{ ...btnSmall, opacity: page === pages - 1 ? 0.3 : 1 }}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
};

const btnSmall: React.CSSProperties = {
  padding: "5px 12px",
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#AAA",
  borderRadius: 6,
  fontSize: 11,
  cursor: "pointer",
};

// ─── Main Component ───────────────────────────────────────────────────────────
export const BacktestPanel = ({ options }: { options: any }) => {
  const [params, setParams] = useState({
    symbol: "XAUUSD",
    timeframe: "15m",
    days: 30,
    spread: 0.15,
    slippage: 0.10,
    base_lot: 0.01,
  });
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeView, setActiveView] = useState<"equity" | "monthly" | "trades">("equity");

  const handleRun = async () => {
    setLoading(true);
    setResults(null);
    try {
      const res = await tradingApi.runBacktest(params);
      setResults(res.data);
      setActiveView("equity");
    } catch (err: any) {
      console.error("Backtest failed", err);
      alert(`Backtest failed: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const s = results?.summary;

  // Derived — color equity curve green if profitable, red otherwise
  const equityColor = (s?.net_pnl ?? 0) >= 0 ? "#00FF85" : "#FF4D4D";
  const equityGrad = (s?.net_pnl ?? 0) >= 0 ? "rgba(0,255,133,0.15)" : "rgba(255,77,77,0.15)";

  // Trim time labels on X axis
  const formatEquityX = (t: string) => {
    try { return new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
    catch { return t; }
  };

  // Win rate arc calculation
  const wr = s?.win_rate ?? 0;
  const pf = s?.profit_factor ?? 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      {/* ── Parameters Panel ─────────────────────────────────── */}
      <section style={S.card}>
        <div style={S.cardHeader}>⚙️ Simulation Parameters</div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
            gap: 16,
          }}
        >
          {/* Symbol */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={S.label}>Symbol</label>
            <select
              style={S.input}
              value={params.symbol}
              onChange={(e) => setParams({ ...params, symbol: e.target.value })}
            >
              {Object.keys(options?.instruments || { XAUUSD: 1 }).map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          {/* Timeframe */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={S.label}>Timeframe</label>
            <select
              style={S.input}
              value={params.timeframe}
              onChange={(e) => setParams({ ...params, timeframe: e.target.value })}
            >
              {Object.keys(options?.timeframes || { "15m": 1, "1h": 1, "4h": 1 }).map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </div>
          {/* Days */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={S.label}>Duration (Days)</label>
            <input
              style={S.input}
              type="number"
              min={7}
              max={365}
              value={params.days}
              onChange={(e) => setParams({ ...params, days: parseInt(e.target.value) })}
            />
          </div>
          {/* Spread */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={S.label}>Spread (pts)</label>
            <input
              style={S.input}
              type="number"
              step="0.01"
              value={params.spread}
              onChange={(e) => setParams({ ...params, spread: parseFloat(e.target.value) })}
            />
          </div>
          {/* Slippage */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={S.label}>Slippage (pts)</label>
            <input
              style={S.input}
              type="number"
              step="0.01"
              value={params.slippage}
              onChange={(e) => setParams({ ...params, slippage: parseFloat(e.target.value) })}
            />
          </div>
          {/* Base Lot */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={S.label}>Base Lot</label>
            <input
              style={S.input}
              type="number"
              step="0.01"
              value={params.base_lot}
              onChange={(e) => setParams({ ...params, base_lot: parseFloat(e.target.value) })}
            />
          </div>
        </div>
        <button
          id="run-backtest-btn"
          onClick={handleRun}
          disabled={loading}
          style={{
            marginTop: 24,
            width: "100%",
            padding: "14px",
            borderRadius: 8,
            fontWeight: 800,
            fontSize: 13,
            letterSpacing: 1.5,
            textTransform: "uppercase",
            background: loading
              ? "rgba(212,175,55,0.3)"
              : "linear-gradient(135deg, #D4AF37 0%, #F5D063 100%)",
            color: "#0D0E12",
            border: "none",
            cursor: loading ? "not-allowed" : "pointer",
            transition: "all 0.2s",
            boxShadow: loading ? "none" : "0 4px 20px rgba(212,175,55,0.25)",
          }}
        >
          {loading ? "⏳  Running Simulation…" : "▶  Run Grid Backtest"}
        </button>
      </section>

      {/* ── Loading Skeleton ─────────────────────────────────── */}
      {loading && (
        <div style={{ ...S.card, textAlign: "center", padding: 48 }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⚡</div>
          <div style={{ color: "#D4AF37", fontWeight: 700, fontSize: 16 }}>Running Grid Simulation…</div>
          <div style={{ color: "#555", fontSize: 13, marginTop: 8 }}>
            Fetching {params.days} days of {params.symbol} {params.timeframe} data & simulating trades
          </div>
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────── */}
      {results && !loading && (
        <>
          {/* ── KPI Row ───────────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 16 }}>
            <StatCard
              label="Net Profit"
              value={`${s!.net_pnl >= 0 ? "+" : ""}$${s!.net_pnl.toFixed(2)}`}
              color={s!.net_pnl >= 0 ? "#00FF85" : "#FF4D4D"}
              icon="💰"
            />
            <StatCard label="Win Rate" value={`${s!.win_rate}%`} sub={`${s!.wins}W / ${s!.losses}L`} color="#D4AF37" icon="🎯" />
            <StatCard
              label="Profit Factor"
              value={s!.profit_factor.toFixed(2)}
              sub={pf >= 1.5 ? "Strong Edge" : pf >= 1 ? "Marginal Edge" : "No Edge"}
              color={pf >= 1.5 ? "#00FF85" : pf >= 1 ? "#D4AF37" : "#FF4D4D"}
              icon="📊"
            />
            <StatCard
              label="Max Drawdown"
              value={`$${s!.max_dd.toFixed(2)}`}
              color="#FF6B6B"
              icon="📉"
            />
            <StatCard label="Sharpe Ratio" value={s!.sharpe.toFixed(2)} sub={s!.sharpe >= 1.5 ? "Excellent" : s!.sharpe >= 0.5 ? "Good" : "Poor"} color="#00D1FF" icon="📐" />
            <StatCard label="Calmar Ratio" value={s!.calmar.toFixed(2)} color="#00D1FF" icon="🏆" />
            <StatCard label="Expectancy" value={`$${s!.expectancy.toFixed(2)}`} sub="per trade" color={s!.expectancy >= 0 ? "#00FF85" : "#FF4D4D"} icon="🔮" />
            <StatCard label="Total Trades" value={s!.trades} sub={`Avg W: $${s!.avg_win.toFixed(2)} / L: $${s!.avg_loss.toFixed(2)}`} icon="🔁" />
          </div>

          {/* ── Streak Row ────────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div style={{ ...S.card, padding: "16px 22px" }}>
              <div style={S.label}>Max Consecutive Wins</div>
              <div style={{ fontSize: 32, fontWeight: 800, color: "#00FF85", marginTop: 6 }}>
                {s!.max_consec_wins}
                <span style={{ fontSize: 14, color: "#555", fontWeight: 400, marginLeft: 8 }}>streak</span>
              </div>
            </div>
            <div style={{ ...S.card, padding: "16px 22px" }}>
              <div style={S.label}>Max Consecutive Losses</div>
              <div style={{ fontSize: 32, fontWeight: 800, color: "#FF4D4D", marginTop: 6 }}>
                {s!.max_consec_losses}
                <span style={{ fontSize: 14, color: "#555", fontWeight: 400, marginLeft: 8 }}>streak</span>
              </div>
            </div>
          </div>

          {/* ── Sub-Tab Navigation ────────────── */}
          <div style={{ display: "flex", gap: 8 }}>
            {(["equity", "monthly", "trades"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setActiveView(v)}
                style={{
                  padding: "8px 18px",
                  borderRadius: 6,
                  fontWeight: 700,
                  fontSize: 12,
                  letterSpacing: 1,
                  textTransform: "uppercase",
                  border: "none",
                  cursor: "pointer",
                  background: activeView === v ? "rgba(212,175,55,0.15)" : "transparent",
                  color: activeView === v ? "#D4AF37" : "#555",
                  borderBottom: activeView === v ? "2px solid #D4AF37" : "2px solid transparent",
                  transition: "all 0.2s",
                }}
              >
                {v === "equity" ? "📈 Equity Curve" : v === "monthly" ? "📅 Monthly P&L" : `📋 Trade Log (${results.trades.length})`}
              </button>
            ))}
          </div>

          {/* ── Equity Curve ──────────────────── */}
          {activeView === "equity" && results.equity_curve.length > 1 && (
            <section style={S.card}>
              <div style={S.cardHeader}>📈 Equity Curve — {params.symbol} {params.timeframe} ({params.days}d)</div>
              <ResponsiveContainer width="100%" height={340}>
                <AreaChart data={results.equity_curve} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={equityColor} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={equityColor} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis
                    dataKey="time"
                    tickFormatter={formatEquityX}
                    tick={{ fill: "#555", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fill: "#555", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `$${v}`}
                    width={60}
                  />
                  <Tooltip content={<EquityTooltip />} />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" strokeDasharray="4 4" />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke={equityColor}
                    strokeWidth={2}
                    fill="url(#eqGrad)"
                    dot={false}
                    activeDot={{ r: 4, fill: equityColor }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </section>
          )}

          {activeView === "equity" && results.equity_curve.length <= 1 && (
            <div style={{ ...S.card, textAlign: "center", padding: 40, color: "#555" }}>
              Not enough equity data points to render chart. Try a longer duration.
            </div>
          )}

          {/* ── Monthly Bar Chart ─────────────── */}
          {activeView === "monthly" && (
            <section style={S.card}>
              <div style={S.cardHeader}>📅 Monthly P&L Breakdown</div>
              {results.monthly.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={results.monthly} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                      <XAxis dataKey="month" tick={{ fill: "#555", fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#555", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} width={60} />
                      <Tooltip content={<MonthlyTooltip />} />
                      <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" />
                      <Bar dataKey="month_pnl" radius={[4, 4, 0, 0]}>
                        {results.monthly.map((m, i) => (
                          <Cell key={i} fill={m.month_pnl >= 0 ? "#00FF85" : "#FF4D4D"} fillOpacity={0.8} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  {/* Monthly Table */}
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginTop: 20 }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                        {["Month", "Monthly PnL", "Min Equity", "Max Equity", "End Equity"].map((h) => (
                          <th key={h} style={{ padding: "8px 12px", textAlign: "left", color: "#555", fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {results.monthly.map((m, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                          <td style={{ padding: "10px 12px", color: "#AAA", fontWeight: 600 }}>{m.month}</td>
                          <td style={{ padding: "10px 12px", fontWeight: 700, color: m.month_pnl >= 0 ? "#00FF85" : "#FF4D4D" }}>
                            {m.month_pnl >= 0 ? "+" : ""}${m.month_pnl.toFixed(2)}
                          </td>
                          <td style={{ padding: "10px 12px", color: "#FF6B6B" }}>${m.min_equity.toFixed(2)}</td>
                          <td style={{ padding: "10px 12px", color: "#00FF85" }}>${m.max_equity.toFixed(2)}</td>
                          <td style={{ padding: "10px 12px", color: "#AAA" }}>${m.end_equity.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              ) : (
                <div style={{ textAlign: "center", padding: 40, color: "#555" }}>No monthly data available.</div>
              )}
            </section>
          )}

          {/* ── Trade Log ─────────────────────── */}
          {activeView === "trades" && (
            <section style={S.card}>
              <div style={S.cardHeader}>📋 Trade Log — {results.trades.length} trades</div>
              {results.trades.length > 0 ? (
                <TradeLogTable trades={results.trades} />
              ) : (
                <div style={{ textAlign: "center", padding: 40, color: "#555" }}>No trades executed in this simulation.</div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
};
