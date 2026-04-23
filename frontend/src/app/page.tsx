"use client";
import { useEffect, useState } from "react";
import { AccountStats } from "../components/AccountStats";
import { NewsFeed } from "../components/NewsFeed";
import { TradingChart } from "../components/TradingChart";
import { TradeTable } from "../components/TradeTable";
import { AIInsightPanel } from "../components/AIInsightPanel";
import { ConfigForm } from "../components/ConfigForm";
import { AIAnalysisTab } from "../components/AIAnalysisTab";
import { BacktestPanel } from "../components/BacktestPanel";
import { PropFirmPanel } from "../components/PropFirmPanel";
import { LogViewer } from "../components/LogViewer";
import { ConnectModal } from "../components/ConnectModal";
import { tradingApi } from "../utils/api";

export default function Home() {
  // Real dynamic state
  const [mt5Connected, setMt5Connected] = useState(false);
  const [account, setAccount] = useState<any>(null);
  const [ticker, setTicker] = useState<any>(null);
  const [botState, setBotState] = useState<any>(null);
  const [signals, setSignals] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [config, setConfig] = useState<any>(null);
  const [options, setOptions] = useState<any>(null);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [gridLevels, setGridLevels] = useState<any[]>([]);
  const [anchorPrice, setAnchorPrice] = useState<number>(0);
  const [analysis, setAnalysis] = useState<any>(null);
  const [signalBridge, setSignalBridge] = useState<any>(null);
  
  // Legacy/UI state
  const [autoTrading, setAutoTrading] = useState(false);
  const [activeTab, setActiveTab] = useState("monitor");
  const [news, setNews] = useState<any[]>([]); 
  const [newsGuard, setNewsGuard] = useState({ blocked: false, reason: "Buffer Clear" });
  const [chartData, setChartData] = useState([{ time: "Now", price: 0 }]);
  const [trades, setTrades] = useState<any[]>([]);

  // ── Derived account metrics ──────────────────────────────────────
  // Prop firm targets driven by real account balance + grid config
  const startingBalance = account?.balance || 0;
  const profitTargetPct = 10; // FTMO Phase 1 = 10%
  const targetAmount    = startingBalance * (profitTargetPct / 100);
  const currentProfit   = account?.profit || 0;
  const progressToTarget = targetAmount > 0 ? Math.min(100, Math.max(0, (currentProfit / targetAmount) * 100)) : 0;
  const phase = progressToTarget >= 100 ? 2 : 1; // Phase 2 once target hit

  // DD thresholds from GridConfig (fallback: FTMO defaults)
  const maxDailyLossPct  = config?.max_daily_loss_usd && startingBalance > 0
    ? (config.max_daily_loss_usd / startingBalance) * 100
    : 5;   // FTMO 5%
  const maxTotalDDPct    = config?.max_drawdown_pct ?? 10; // FTMO 10%

  // Data Fetching Loop
  useEffect(() => {
    // ── Auto-Connect Logic ──
    const performAutoConnect = async () => {
      try {
        const statusRes = await tradingApi.getStatus();
        if (statusRes.data.mt5_connected) {
          setMt5Connected(true);
        } else {
          // Attempt silent connect with saved credentials
          await tradingApi.connectMt5({});
          const retry = await tradingApi.getStatus();
          if (retry.data.mt5_connected) setMt5Connected(true);
        }
      } catch (e) {
        console.error("Auto-connect failed:", e);
      }
    };

    performAutoConnect();

    const fetchData = async () => {
      try {
        const [statusRes, accRes, tickerRes, botRes, logRes, posRes, levelsRes, bridgeRes] = await Promise.all([
          tradingApi.getStatus(),
          tradingApi.getAccount().catch(() => ({ data: null })),
          tradingApi.getTicker().catch(() => ({ data: null })),
          tradingApi.getBotState().catch(() => ({ data: null })),
          tradingApi.getLogs(50).catch(() => ({ data: [] })),
          tradingApi.getPositions().catch(() => ({ data: [] })),
          tradingApi.getLevels().catch(() => ({ data: null })),
          tradingApi.getSignalBridge().catch(() => ({ data: null })),
        ]);

        setMt5Connected(statusRes.data.mt5_connected);
        if (accRes.data) setAccount(accRes.data);
        if (tickerRes.data) {
          setTicker(tickerRes.data);
          // Update simple chart data for visualization
          setChartData(prev => [...prev.slice(-20), { time: new Date().toLocaleTimeString(), price: tickerRes.data.bid }]);
        }
        if (botRes.data) {
          setBotState(botRes.data);
          setAutoTrading(botRes.data.active);
        }
        if (logRes.data) setLogs(logRes.data);
        if (Array.isArray(posRes.data)) setTrades(posRes.data);
        if (levelsRes.data?.levels) {
          setGridLevels(levelsRes.data.levels);
          setAnchorPrice(levelsRes.data.anchor_price || 0);
        }
        if (bridgeRes?.data) {
          setSignalBridge(bridgeRes.data);
        }
      } catch (err) {
        console.error("Fetch error:", err);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 2000); // Poll every 2 seconds

    // Separate fetchers for less frequent data
    const fetchNewsData = async () => {
      try {
        const newsRes = await tradingApi.getNews().catch(() => ({ data: [] }));
        if (newsRes.data) setNews(newsRes.data);
        
        // Also update news guard state from status (optional, but keep it consistent)
        const statusRes = await tradingApi.getStatus();
        if (statusRes.data.news_blocked !== undefined) {
          setNewsGuard({ 
            blocked: statusRes.data.news_blocked, 
            reason: statusRes.data.news_reason || "Buffer Clear" 
          });
        }
      } catch (e) { console.error("News fetch error", e); }
    };

    const fetchAnalysisData = async () => {
      try {
        const analysisRes = await tradingApi.getAnalysis().catch(() => ({ data: null }));
        const signalsRes = await tradingApi.getSignals().catch(() => ({ data: null }));
        if (analysisRes.data) setAnalysis(analysisRes.data);
        if (signalsRes.data) setSignals(signalsRes.data);
      } catch (e) { console.error("Analysis/Signals fetch error", e); }
    };

    fetchNewsData();
    fetchAnalysisData();
    const newsInterval = setInterval(fetchNewsData, 60000); // Poll news every 60s
    const analysisInterval = setInterval(fetchAnalysisData, 15000); // Poll analysis/signals every 15s

    // Fetch static options once
    tradingApi.getOptions().then(res => setOptions(res.data));
    tradingApi.getConfig().then(res => setConfig(res.data));

    return () => {
      clearInterval(interval);
      clearInterval(newsInterval);
      clearInterval(analysisInterval);
    };
  }, []);

  const refreshConfig = () => {
    tradingApi.getConfig().then(res => setConfig(res.data));
  };

  const calculateVolatility = () => {
    if (chartData.length < 2) return "0.00";
    const prices = chartData.map((d) => d.price).filter(p => p > 0);
    if (prices.length < 2) return "0.00";
    const mean = prices.reduce((a, b) => a + b, 0) / prices.length;
    const variance = prices.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / prices.length;
    return Math.sqrt(variance).toFixed(2);
  };

  const toggleAutoTrading = async () => {
    const prev = autoTrading;
    // Optimistic update
    setAutoTrading(!prev);
    try {
      if (prev) {
        await tradingApi.deactivateBot();
      } else {
        await tradingApi.activateBot();
      }
    } catch (err) {
      // Revert on failure — UI stays in sync with backend reality
      setAutoTrading(prev);
      console.error("Failed to toggle bot", err);
      alert("Failed to toggle bot. Check MT5 connection.");
    }
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
          Sacred Soul{" "}
          <span style={{ color: "#888", fontWeight: 400, fontSize: 16 }}>
            v2.0-Alpha
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
          <span style={{ color: "#888" }}>MT5 Status:</span>
          <b style={{ color: mt5Connected ? "#00FF85" : "#FF4D4D" }}>
            {mt5Connected ? "CONNECTED" : "DISCONNECTED"}
          </b>
          {!mt5Connected && (
            <button 
              onClick={() => setIsConnectModalOpen(true)}
              style={{ background: "none", border: "none", color: "#D4AF37", cursor: "pointer", fontSize: 12, textDecoration: "underline", padding: 0 }}
            >
              Connect
            </button>
          )}
          <span style={{ color: "#888" }}>Price:</span>
          <b style={{ color: "#00D1FF" }}>{ticker?.bid ? `$${ticker.bid.toFixed(2)}` : "---"}</b>
          <span style={{ color: "#888" }}>Spread:</span>
          <b style={{ color: "#888" }}>{ticker?.spread ? ticker.spread.toFixed(2) : "0.0"}</b>
        </div>
        <button
          onClick={toggleAutoTrading}
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
          {autoTrading ? "Stop Grid Bot" : "Activate Smart Grid"}
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
        {["monitor", "ict", "backtest", "config", "prop"].map((tab) => (
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
              ? "Live Monitor"
              : tab === "ict"
                ? "AI Analysis"
                : tab === "backtest"
                  ? "Simulation"
                  : tab === "config"
                    ? "Settings"
                    : "Prop Firm"}
          </button>
        ))}
      </nav>

      {/* Main Content */}
      <main style={{ padding: 32 }}>
        {activeTab === "monitor" && (
          <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
            <div style={{ flex: 2, minWidth: 340 }}>
              <TradingChart 
                data={chartData} 
                levels={gridLevels} 
                anchorPrice={anchorPrice} 
                analysis={analysis} 
              />
              <div style={{ marginTop: 32 }}>
                 <TradeTable trades={trades} />
              </div>
              <div style={{ marginTop: 32 }}>
                <NewsFeed items={news} guard={newsGuard} />
              </div>
              <div style={{ marginTop: 32 }}>
                <LogViewer logs={logs} />
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 320 }}>
              <AccountStats
                status={{
                  phase,
                  dailyLoss: (account?.daily_loss_pct || 0) / 100,
                  totalLoss: (account?.total_loss_pct || 0) / 100,
                  equity: account?.equity || 0,
                }}
                progressToTarget={progressToTarget}
                targetAmount={targetAmount}
                currentProfit={currentProfit}
                totalPnL={account?.profit ?? 0}
                activeTradesCount={botState?.open_levels || 0}
                calculateVolatility={calculateVolatility}
                mt5Status={mt5Connected ? "CONNECTED" : "DISCONNECTED"}
                autoTrading={autoTrading}
                maxDailyLossPct={maxDailyLossPct}
                maxTotalDDPct={maxTotalDDPct}
              />
              <AIInsightPanel aiInsight={signals?.bias ? `${signals.bias} Bias (${signals.confidence.toFixed(0)}% Conf)` : "Analyzing market..."} />
              
              {/* Signal Bridge Monitor */}
              <div style={{
                marginTop: 24,
                background: "#16181D",
                padding: 20,
                borderRadius: 8,
                border: "1px solid rgba(255,255,255,0.05)"
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                  <h3 style={{ margin: 0, fontSize: 14, color: "#D4AF37", letterSpacing: 1 }}>SIGNAL BRIDGE</h3>
                  <div style={{ 
                    fontSize: 10, 
                    padding: "2px 8px", 
                    borderRadius: 4, 
                    background: signalBridge?.is_active ? "rgba(0, 255, 133, 0.1)" : "rgba(255, 77, 77, 0.1)",
                    color: signalBridge?.is_active ? "#00FF85" : "#FF4D4D",
                    border: `1px solid ${signalBridge?.is_active ? "#00FF8544" : "#FF4D4D44"}`
                  }}>
                    {signalBridge?.is_active ? "WATCHING LIVE" : "DISCONNECTED"}
                  </div>
                </div>

                <div style={{ maxHeight: 200, overflowY: "auto", fontSize: 11, fontFamily: "monospace" }}>
                  {signalBridge?.history && signalBridge.history.length > 0 ? (
                    signalBridge.history.slice().reverse().map((h: any, i: number) => (
                      <div key={i} style={{ 
                        padding: "8px 0", 
                        borderBottom: "1px solid rgba(255,255,255,0.03)",
                        display: "flex",
                        flexDirection: "column",
                        gap: 4
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span style={{ color: "#888" }}>[{h.time}] {h.source}</span>
                          <span style={{ 
                            color: h.status.includes("NEW") ? "#00D1FF" : h.status.includes("SET") ? "#D4AF37" : "#555" 
                          }}>
                            {h.status}
                          </span>
                        </div>
                        <div style={{ color: "#AAA", fontStyle: "italic", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          "{h.text}"
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ color: "#555", textAlign: "center", padding: 20 }}>
                      Waiting for signals...
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
        {activeTab === "config" && (
          <div style={{ maxWidth: 1000, margin: "0 auto" }}>
            <ConfigForm config={config} options={options} onUpdate={refreshConfig} />
          </div>
        )}
        {activeTab === "ict" && (
          <div style={{ maxWidth: 1200, margin: "0 auto" }}>
            <AIAnalysisTab signals={signals} />
          </div>
        )}
        {activeTab === "backtest" && (
          <div style={{ maxWidth: 1200, margin: "0 auto" }}>
            <BacktestPanel options={options} />
          </div>
        )}
        {activeTab === "prop" && (
          <div style={{ maxWidth: 1200, margin: "0 auto" }}>
            <PropFirmPanel account={account} />
          </div>
        )}
        {/* Placeholder for other tabs */}
      </main>

      <ConnectModal 
        isOpen={isConnectModalOpen} 
        onClose={() => setIsConnectModalOpen(false)}
        onSuccess={() => {
          // Success handled by the polling loop
        }}
      />
    </div>
  );
}
