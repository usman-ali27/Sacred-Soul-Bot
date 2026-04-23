"use client";
import { useState, useEffect } from "react";

export const PropFirmPanel = ({ account }: { account: any }) => {
  const [rules, setRules] = useState({
    maxDailyLoss: 5,
    maxTotalDD: 10,
    profitTarget: 10,
    startingBalance: account?.balance || 10000,
  });

  // Sync startingBalance when account connects or balance changes
  useEffect(() => {
    if (account?.balance && account.balance > 0) {
      setRules(prev => ({ ...prev, startingBalance: account.balance }));
    }
  }, [account?.balance]);

  const [calc, setCalc] = useState({ slPips: 20, riskPct: 1 });

  const currentBalance   = account?.balance   || rules.startingBalance;
  const currentEquity    = account?.equity    || currentBalance;
  const currentProfit    = account?.profit    || 0;
  const dailyLossLimit   = rules.startingBalance * (rules.maxDailyLoss / 100);
  const totalDDLimit     = rules.startingBalance * (rules.maxTotalDD / 100);
  const profitTarget     = rules.startingBalance * (rules.profitTarget / 100);
  const ddFloor          = rules.startingBalance - totalDDLimit;
  const healthPct        = Math.max(0, ((currentEquity - ddFloor) / (rules.startingBalance - ddFloor)) * 100);
  const progressPct      = Math.min(100, Math.max(0, (currentProfit / profitTarget) * 100));

  // Position sizing (Gold: ~$1/pip per 0.01 lot, so $10/pip per 1 lot)
  const riskDollar = currentBalance * (calc.riskPct / 100);
  const lotSize    = parseFloat((riskDollar / (calc.slPips * 10)).toFixed(2));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>

      {/* Live Account Summary */}
      <section style={cardStyle}>
        <h3 style={headerStyle}>Live Account Status</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
          {[
            { label: "Balance",    value: `$${currentBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, color: "#E0E0E0" },
            { label: "Equity",     value: `$${currentEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,  color: currentEquity >= currentBalance ? "#00FF85" : "#FF4D4D" },
            { label: "Profit",     value: `${currentProfit >= 0 ? "+" : ""}$${currentProfit.toFixed(2)}`, color: currentProfit >= 0 ? "#00FF85" : "#FF4D4D" },
            { label: "Progress",   value: `${progressPct.toFixed(1)}%`, color: "#D4AF37" },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: "#23262D", borderRadius: 6, padding: "12px 16px", textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#666", textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>{label}</div>
              <div style={{ fontFamily: "monospace", fontSize: 15, fontWeight: 800, color }}>{value}</div>
            </div>
          ))}
        </div>
        {/* Profit target progress bar */}
        <div style={{ marginTop: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#888", marginBottom: 6 }}>
            <span>Profit Target Progress</span>
            <span>${currentProfit.toFixed(2)} / ${profitTarget.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
          </div>
          <div style={{ height: 6, background: "#23262D", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${progressPct}%`, background: "linear-gradient(90deg, #D4AF37, #00FF85)", borderRadius: 4, transition: "width 1s ease" }} />
          </div>
        </div>
      </section>

      {/* Risk Calculator */}
      <section style={cardStyle}>
        <h3 style={headerStyle}>AI Risk Calculator (Prop Optimized)</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
          <div style={fieldStyle}>
            <label style={labelStyle}>Stop Loss (Pips)</label>
            <input style={inputStyle} type="number" value={calc.slPips} onChange={e => setCalc({...calc, slPips: parseFloat(e.target.value)})} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Risk per Trade (%)</label>
            <input style={inputStyle} type="number" step="0.1" value={calc.riskPct} onChange={e => setCalc({...calc, riskPct: parseFloat(e.target.value)})} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Suggested Lot Size</label>
            <div style={{ padding: "10px 12px", background: "rgba(0,200,150,0.1)", borderRadius: 4, color: "#00FF85", fontWeight: 800 }}>
              {lotSize} Lots
            </div>
          </div>
        </div>
        <p style={{ fontSize: 12, color: "#888", marginTop: 12 }}>
          Risking <b>${riskDollar.toFixed(2)}</b> per trade on ${currentBalance.toLocaleString(undefined, { maximumFractionDigits: 0 })} account.
        </p>
      </section>

      {/* Drawdown Protection */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24 }}>
        <section style={cardStyle}>
          <h3 style={headerStyle}>Daily Loss Limit</h3>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#FF4D4D" }}>${dailyLossLimit.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
          <p style={{ color: "#888", fontSize: 12, marginTop: 8 }}>Max loss per day before auto-stop.</p>
          <div style={{ marginTop: 16 }}>
            <label style={labelStyle}>Limit %</label>
            <input style={inputStyle} type="number" value={rules.maxDailyLoss} onChange={e => setRules({...rules, maxDailyLoss: parseFloat(e.target.value)})} />
          </div>
        </section>

        <section style={cardStyle}>
          <h3 style={headerStyle}>Max Drawdown Floor</h3>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#FF4D4D" }}>${ddFloor.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
          <p style={{ color: "#888", fontSize: 12, marginTop: 8 }}>Absolute equity floor. Bot stops here.</p>
          <div style={{ marginTop: 16 }}>
            <label style={labelStyle}>Max DD %</label>
            <input style={inputStyle} type="number" value={rules.maxTotalDD} onChange={e => setRules({...rules, maxTotalDD: parseFloat(e.target.value)})} />
          </div>
        </section>

        <section style={cardStyle}>
          <h3 style={headerStyle}>Profit Target</h3>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#D4AF37" }}>${profitTarget.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
          <p style={{ color: "#888", fontSize: 12, marginTop: 8 }}>Required profit to pass phase.</p>
          <div style={{ marginTop: 16 }}>
            <label style={labelStyle}>Target %</label>
            <input style={inputStyle} type="number" value={rules.profitTarget} onChange={e => setRules({...rules, profitTarget: parseFloat(e.target.value)})} />
          </div>
        </section>
      </div>

      {/* Account Health */}
      <section style={cardStyle}>
        <h3 style={headerStyle}>Account Health Meter</h3>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#888", marginBottom: 8 }}>
          <span>Breach Level (${ddFloor.toLocaleString(undefined, { maximumFractionDigits: 0 })})</span>
          <span style={{ color: healthPct > 70 ? "#00FF85" : healthPct > 40 ? "#D4AF37" : "#FF4D4D", fontWeight: 700 }}>
            {healthPct.toFixed(1)}% Safe
          </span>
          <span>Target (${(rules.startingBalance + profitTarget).toLocaleString(undefined, { maximumFractionDigits: 0 })})</span>
        </div>
        <div style={{ height: 20, background: "rgba(255,255,255,0.05)", borderRadius: 10, overflow: "hidden" }}>
          <div style={{
            width: `${healthPct}%`,
            height: "100%",
            background: healthPct > 70 ? "linear-gradient(90deg, #FF4D4D, #00FF85)"
                       : healthPct > 40 ? "linear-gradient(90deg, #FF4D4D, #D4AF37)"
                       : "#FF4D4D",
            transition: "width 1s ease"
          }} />
        </div>
      </section>
    </div>
  );
};

const cardStyle = {
  background: "#16181D",
  padding: 24,
  borderRadius: 8,
  border: "1px solid rgba(255,255,255,0.05)",
};

const headerStyle = {
  fontSize: 14,
  color: "#D4AF37",
  textTransform: "uppercase" as const,
  letterSpacing: 1,
  marginBottom: 20,
};

const labelStyle = {
  fontSize: 11,
  color: "#888",
  fontWeight: 600,
  textTransform: "uppercase" as const,
  marginBottom: 8,
  display: "block"
};

const fieldStyle = {
  display: "flex",
  flexDirection: "column" as const,
};

const inputStyle = {
  background: "#0D0E12",
  border: "1px solid rgba(255,255,255,0.1)",
  padding: "10px 12px",
  color: "#fff",
  borderRadius: 4,
  fontSize: 14,
  width: "100%"
};
