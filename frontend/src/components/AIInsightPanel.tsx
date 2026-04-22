import React from "react";

export const AIInsightPanel = ({ aiInsight }: { aiInsight: string }) => (
  <div
    style={{
      background: "#16181D",
      border: "1px solid rgba(255,255,255,0.05)",
      borderRadius: 8,
      padding: 24,
      marginBottom: 24,
      color: "#E0E0E0",
    }}
  >
    <div
      style={{
        fontSize: 13,
        fontWeight: 700,
        color: "#D4AF37",
        marginBottom: 8,
      }}
    >
      AI Sentiment Core
    </div>
    <div style={{ fontStyle: "italic", color: "#E0E0E0", fontSize: 15 }}>
      "{aiInsight}"
    </div>
  </div>
);
