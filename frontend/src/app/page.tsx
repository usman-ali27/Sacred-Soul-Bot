"use client";
import { useEffect, useState } from "react";
import { AccountStats } from "../components/AccountStats";
import { NewsFeed } from "../components/NewsFeed";
import { TradingChart } from "../components/TradingChart";
import { TradeTable } from "../components/TradeTable";
import { AIInsightPanel } from "../components/AIInsightPanel";

export default function Home() {
  // Demo/mock data for UI
  const [accountStatus, setAccountStatus] = useState({
    phase: 1,
    dailyLoss: 0.02,
    totalLoss: 0.04,
    equity: 10000,
  });
  const [progressToTarget, setProgressToTarget] = useState(45.2);
  const [targetAmount, setTargetAmount] = useState(20000);
  const [currentProfit, setCurrentProfit] = useState(9042.12);
  const [totalPnL, setTotalPnL] = useState(1200);
  const [activeTradesCount, setActiveTradesCount] = useState(3);
  const [autoTrading, setAutoTrading] = useState(true);
  const [mt5Status, setMt5Status] = useState("CONNECTED");
  const [news, setNews] = useState([
    {
      id: "1",
      title: "Fed Signals Potential Pivot in 2026 Policy Meeting",
      impact: "HIGH",
      sentiment: 0.5,
    },
    {
      id: "2",
      title: "Global Demand for Gold Surges as Reserve Asset",
      impact: "MEDIUM",
      sentiment: 0.8,
    },
    {
      id: "3",
      title: "Consumer Spending Data Exceeds Experts Estimates",
      impact: "LOW",
      sentiment: -0.2,
    },
  ]);
  const [chartData, setChartData] = useState([
    { time: "09:00", price: 1920 },
    { time: "10:00", price: 1925 },
    { time: "11:00", price: 1918 },
    { time: "12:00", price: 1932 },
    { time: "13:00", price: 1927 },
    { time: "14:00", price: 1940 },
    { time: "15:00", price: 1935 },
  ]);
  const [activeTab, setActiveTab] = useState("monitor");
  const [aiInsight, setAiInsight] = useState("Analyzing market structure...");
  const [trades, setTrades] = useState([
    {
      id: 1,
      symbol: "XAUUSD",
      type: "BUY",
      entryPrice: 1925,
      lotSize: 0.1,
      pnl: 120,
      status: "OPEN",
    },
    {
      id: 2,
      symbol: "XAUUSD",
      type: "SELL",
      entryPrice: 1932,
      lotSize: 0.2,
      pnl: -45,
      status: "OPEN",
    },
  ]);

  // Placeholder volatility calculation
  const calculateVolatility = () => {
    if (!chartData.length) return 0;
    const prices = chartData.map((d) => d.price);
    const mean = prices.reduce((a, b) => a + b, 0) / prices.length;
    const variance =
      prices.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / prices.length;
    return Math.sqrt(variance).toFixed(2);
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0D0E12",
        color: "#E0E0E0",
        fontFamily: "sans-serif",
      }}
    >
      {/* Header */}
      <header
        style={{
          padding: "20px 30px",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          background: "linear-gradient(90deg, #16181D 0%, #0D0E12 100%)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div
          style={{
            fontSize: 20,
            fontWeight: 800,
            letterSpacing: 2,
            color: "#D4AF37",
            textTransform: "uppercase",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          ICT_BOT{" "}
          <span style={{ color: "#888", fontWeight: 400, fontSize: 16 }}>
            v1.0
          </span>
        </div>
        <div
          style={{
            display: "flex",
            gap: 24,
            fontFamily: "monospace",
            fontSize: 14,
          }}
        >
          <span style={{ color: "#888" }}>Broker:</span>
          <b
            style={{ color: mt5Status === "CONNECTED" ? "#00FF85" : "#00D1FF" }}
          >
            {mt5Status === "CONNECTED" ? "DemoServer" : "Awaiting Connection"}
          </b>
          <span style={{ color: "#888" }}>MT5 Status:</span>
          <b
            style={{ color: mt5Status === "CONNECTED" ? "#00FF85" : "#FF4D4D" }}
          >
            {mt5Status}
          </b>
          <span style={{ color: "#888" }}>Ticker:</span>
          <b style={{ color: "#00D1FF" }}>XAUUSD</b>
        </div>
        <button
          onClick={() => setAutoTrading((v) => !v)}
          style={{
            padding: "10px 24px",
            borderRadius: 4,
            fontWeight: 700,
            fontSize: 13,
            textTransform: "uppercase",
            background: autoTrading ? "#FF4D4D" : "#00D1FF",
            color: autoTrading ? "#fff" : "#000",
            border: "none",
            cursor: "pointer",
            boxShadow: "0 2px 8px #0002",
          }}
        >
          {autoTrading ? "Live Trading Active" : "Engage Smart Bot"}
        </button>
      </header>

      {/* Tab Navigation */}
      <nav
        style={{
          display: "flex",
          gap: 8,
          padding: "16px 30px",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
        }}
      >
        {["monitor", "ict", "backtest", "broker", "config"].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "8px 18px",
              borderRadius: 4,
              fontWeight: 700,
              fontSize: 13,
              textTransform: "uppercase",
              background:
                activeTab === tab
                  ? tab === "ict"
                    ? "#D4AF37"
                    : "#23262D"
                  : "transparent",
              color:
                activeTab === tab
                  ? tab === "ict"
                    ? "#000"
                    : "#00D1FF"
                  : "#888",
              border: "none",
              cursor: "pointer",
              boxShadow: activeTab === tab ? "0 2px 8px #0002" : "none",
              transition: "all 0.2s",
            }}
          >
            {tab === "monitor"
              ? "Monitor"
              : tab === "ict"
                ? "ICT / MTF"
                : tab === "backtest"
                  ? "Simulation"
                  : tab === "broker"
                    ? "Broker"
                    : "Protocols"}
          </button>
        ))}
      </nav>

      {/* Main Content */}
      <main style={{ padding: 32 }}>
        {activeTab === "monitor" && (
          <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
            <div style={{ flex: 2, minWidth: 340 }}>
              <TradingChart data={chartData} />
              <TradeTable trades={trades} />
              <div style={{ marginTop: 32 }}>
                <NewsFeed items={news} />
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 320 }}>
              <AccountStats
                status={accountStatus}
                progressToTarget={progressToTarget}
                targetAmount={targetAmount}
                currentProfit={currentProfit}
                totalPnL={totalPnL}
                activeTradesCount={activeTradesCount}
                calculateVolatility={calculateVolatility}
                mt5Status={mt5Status}
                autoTrading={autoTrading}
              />
              <AIInsightPanel aiInsight={aiInsight} />
            </div>
          </div>
        )}
        {activeTab === "ict" && (
          <div
            style={{
              background: "#16181D",
              borderRadius: 8,
              padding: 32,
              color: "#E0E0E0",
              minHeight: 400,
            }}
          >
            <h2
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: "#D4AF37",
                marginBottom: 12,
              }}
            >
              ICT / Multi-Timeframe Core
            </h2>
            <p
              style={{
                fontSize: 13,
                color: "#888",
                textTransform: "uppercase",
                marginBottom: 24,
              }}
            >
              HTF Alignment: 1H / 15M → Scalp: M5
            </p>
            <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
              {["BULLISH", "BEARISH", "NEUTRAL"].map((bias) => (
                <button
                  key={bias}
                  style={{
                    padding: "8px 18px",
                    borderRadius: 4,
                    fontWeight: 700,
                    fontSize: 13,
                    textTransform: "uppercase",
                    background: "#23262D",
                    color: "#D4AF37",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  {bias}
                </button>
              ))}
            </div>
            <div
              style={{
                background: "#23262D",
                borderRadius: 8,
                padding: 24,
                marginBottom: 24,
              }}
            >
              <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>
                Institutional Logic
              </div>
              <p style={{ fontSize: 14, color: "#E0E0E0" }}>
                The bot currently monitors{" "}
                <span style={{ color: "#D4AF37" }}>FVGs (Fair Value Gaps)</span>{" "}
                on the M1/M5 chart only when HTF bias (1H) is aligned. Grid
                spacing is locked at{" "}
                <span style={{ color: "#fff", fontFamily: "monospace" }}>
                  $10
                </span>{" "}
                price delta to ensure scalp positions aren't clustered in
                equilibrium zones.
              </p>
            </div>
            <div
              style={{ background: "#23262D", borderRadius: 8, padding: 24 }}
            >
              <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>
                Live ICT Market Events
              </div>
              <div style={{ fontSize: 13, color: "#E0E0E0" }}>
                Scanning order flow...
              </div>
            </div>
          </div>
        )}
        {activeTab === "backtest" && (
          <div
            style={{
              background: "#16181D",
              borderRadius: 8,
              padding: 32,
              color: "#E0E0E0",
              minHeight: 400,
            }}
          >
            <h2
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: "#D4AF37",
                marginBottom: 12,
              }}
            >
              Simulation / Backtest
            </h2>
            <div style={{ marginBottom: 24 }}>
              <TradingChart data={chartData} />
            </div>
            <button
              style={{
                padding: "12px 32px",
                borderRadius: 4,
                fontWeight: 700,
                fontSize: 13,
                textTransform: "uppercase",
                background: "#D4AF37",
                color: "#000",
                border: "none",
                cursor: "pointer",
              }}
            >
              Run Institutional Backtest Simulation
            </button>
          </div>
        )}
        {activeTab === "broker" && (
          <div
            style={{
              background: "#16181D",
              borderRadius: 8,
              padding: 32,
              color: "#E0E0E0",
              minHeight: 400,
            }}
          >
            <h2
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: "#D4AF37",
                marginBottom: 12,
              }}
            >
              Broker / Account Connection
            </h2>
            <form
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 16,
                maxWidth: 400,
              }}
            >
              <input
                placeholder="Account ID"
                style={{
                  padding: 12,
                  borderRadius: 4,
                  border: "1px solid #23262D",
                  background: "#23262D",
                  color: "#E0E0E0",
                  fontSize: 15,
                }}
              />
              <input
                placeholder="Password"
                type="password"
                style={{
                  padding: 12,
                  borderRadius: 4,
                  border: "1px solid #23262D",
                  background: "#23262D",
                  color: "#E0E0E0",
                  fontSize: 15,
                }}
              />
              <input
                placeholder="Server"
                style={{
                  padding: 12,
                  borderRadius: 4,
                  border: "1px solid #23262D",
                  background: "#23262D",
                  color: "#E0E0E0",
                  fontSize: 15,
                }}
              />
              <button
                type="submit"
                style={{
                  padding: "12px 32px",
                  borderRadius: 4,
                  fontWeight: 700,
                  fontSize: 13,
                  textTransform: "uppercase",
                  background: "#00D1FF",
                  color: "#000",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                Connect
              </button>
            </form>
          </div>
        )}
        {activeTab === "config" && (
          <div
            style={{
              background: "#16181D",
              borderRadius: 8,
              padding: 32,
              color: "#E0E0E0",
              minHeight: 400,
            }}
          >
            <h2
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: "#D4AF37",
                marginBottom: 12,
              }}
            >
              Engine Protocols
            </h2>
            <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>
                  Grid Spacing ($)
                </div>
                <input
                  type="range"
                  min="5"
                  max="50"
                  step="1"
                  value={10}
                  style={{ width: "100%" }}
                  readOnly
                />
                <div style={{ fontSize: 13, color: "#E0E0E0", marginTop: 4 }}>
                  $10 Delta
                </div>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>
                  Max Grid Levels
                </div>
                <input
                  type="range"
                  min="2"
                  max="20"
                  step="1"
                  value={8}
                  style={{ width: "100%" }}
                  readOnly
                />
                <div style={{ fontSize: 13, color: "#E0E0E0", marginTop: 4 }}>
                  8 Nodes
                </div>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>
                  Min Lot Size
                </div>
                <input
                  type="range"
                  min="0.01"
                  max="0.04"
                  step="0.01"
                  value={0.01}
                  style={{ width: "100%" }}
                  readOnly
                />
                <div style={{ fontSize: 13, color: "#E0E0E0", marginTop: 4 }}>
                  0.01 Lots
                </div>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>
                  Max Lot Size
                </div>
                <input
                  type="range"
                  min="0.01"
                  max="0.10"
                  step="0.01"
                  value={0.05}
                  style={{ width: "100%" }}
                  readOnly
                />
                <div style={{ fontSize: 13, color: "#E0E0E0", marginTop: 4 }}>
                  0.05 Lots
                </div>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>
                  Take Profit
                </div>
                <input
                  type="range"
                  min="1.0"
                  max="20.0"
                  step="0.5"
                  value={10}
                  style={{ width: "100%" }}
                  readOnly
                />
                <div style={{ fontSize: 13, color: "#E0E0E0", marginTop: 4 }}>
                  10 Pips
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
