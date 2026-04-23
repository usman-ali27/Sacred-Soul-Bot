"use client";

interface AIAnalysisTabProps {
  signals: any;
}

export const AIAnalysisTab = ({ signals }: AIAnalysisTabProps) => {
  if (!signals) return <div style={{ color: "#888", textAlign: "center", padding: 40 }}>Analyzing market structure...</div>;

  const biasColor = signals.bias === "BULLISH" ? "#00FF85" : signals.bias === "BEARISH" ? "#FF4D4D" : "#888";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      {/* Bias Indicator */}
      <section style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h3 style={labelStyle}>Current Market Bias</h3>
            <h1 style={{ fontSize: 48, fontWeight: 900, color: biasColor, margin: "8px 0" }}>
              {signals.bias}
            </h1>
            <p style={{ color: "#888", fontSize: 14 }}>
              Based on {signals.symbol} ({signals.timeframe}) ICT confluence
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <h3 style={labelStyle}>Confidence</h3>
            <div style={{ fontSize: 32, fontWeight: 800, color: "#fff" }}>
              {signals.confidence?.toFixed(0)}%
            </div>
            <div style={{ width: 160, height: 8, background: "rgba(255,255,255,0.1)", borderRadius: 4, marginTop: 8, overflow: "hidden" }}>
              <div style={{ width: `${signals.confidence}%`, height: "100%", background: biasColor, transition: "width 1s ease-out" }} />
            </div>
          </div>
        </div>
      </section>

      {/* Signal Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32 }}>
        {/* Bullish Signals */}
        <section style={cardStyle}>
          <div style={{ borderBottom: "1px solid rgba(0, 255, 133, 0.2)", paddingBottom: 12, marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
             <h3 style={{ color: "#00FF85", fontSize: 14, fontWeight: 700, textTransform: "uppercase" }}>Bullish Confluence</h3>
             <span style={{ color: "#00FF85", fontWeight: 800 }}>{signals.signals?.bull || 0}</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {signals.signals?.bull_details?.map((s: string) => (
              <SignalBadge key={s} name={s} type="bull" />
            ))}
            {(!signals.signals?.bull_details || signals.signals.bull_details.length === 0) && (
              <span style={{ color: "#444", fontSize: 13 }}>No active bullish signals</span>
            )}
          </div>
        </section>

        {/* Bearish Signals */}
        <section style={cardStyle}>
          <div style={{ borderBottom: "1px solid rgba(255, 77, 77, 0.2)", paddingBottom: 12, marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
             <h3 style={{ color: "#FF4D4D", fontSize: 14, fontWeight: 700, textTransform: "uppercase" }}>Bearish Confluence</h3>
             <span style={{ color: "#FF4D4D", fontWeight: 800 }}>{signals.signals?.bear || 0}</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {signals.signals?.bear_details?.map((s: string) => (
              <SignalBadge key={s} name={s} type="bear" />
            ))}
            {(!signals.signals?.bear_details || signals.signals.bear_details.length === 0) && (
              <span style={{ color: "#444", fontSize: 13 }}>No active bearish signals</span>
            )}
          </div>
        </section>
      </div>

      {/* Confluence Matrix */}
      <section style={cardStyle}>
        <h3 style={labelStyle}>Confluence Matrix</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 12, marginTop: 16 }}>
           {["FVG", "MSS", "OB", "OTE", "Liquidity Sweep", "Breaker Block", "Mitigation", "PO3"].map(name => {
             const isBull = signals.signals?.bull_details?.includes(name);
             const isBear = signals.signals?.bear_details?.includes(name);
             return (
               <div key={name} style={{ 
                 padding: "12px", 
                 background: "#0D0E12", 
                 borderRadius: 6, 
                 border: `1px solid ${isBull ? "rgba(0,255,133,0.3)" : isBear ? "rgba(255,77,77,0.3)" : "rgba(255,255,255,0.05)"}`,
                 textAlign: "center"
               }}>
                 <div style={{ fontSize: 10, color: "#888", marginBottom: 4, textTransform: "uppercase" }}>{name}</div>
                 <div style={{ fontSize: 14, fontWeight: 700, color: isBull ? "#00FF85" : isBear ? "#FF4D4D" : "#333" }}>
                   {isBull ? "BULLISH" : isBear ? "BEARISH" : "NEUTRAL"}
                 </div>
               </div>
             )
           })}
        </div>
      </section>
    </div>
  );
};

const SignalBadge = ({ name, type }: { name: string, type: "bull" | "bear" }) => (
  <div style={{
    background: type === "bull" ? "rgba(0, 255, 133, 0.1)" : "rgba(255, 77, 77, 0.1)",
    border: `1px solid ${type === "bull" ? "rgba(0, 255, 133, 0.3)" : "rgba(255, 77, 77, 0.3)"}`,
    color: type === "bull" ? "#00FF85" : "#FF4D4D",
    padding: "6px 12px",
    borderRadius: 4,
    fontSize: 12,
    fontWeight: 700,
  }}>
    {name}
  </div>
);

const cardStyle = {
  background: "#16181D",
  padding: 24,
  borderRadius: 8,
  border: "1px solid rgba(255,255,255,0.05)",
};

const labelStyle = {
  fontSize: 12,
  color: "#888",
  fontWeight: 600,
  textTransform: "uppercase" as const,
  letterSpacing: 1,
};
