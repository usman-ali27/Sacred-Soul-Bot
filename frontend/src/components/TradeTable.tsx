import React from "react";

export const TradeTable = ({ trades }: { trades: any[] }) => (
  <div
    style={{
      background: "#16181D",
      borderRadius: 8,
      padding: 24,
      color: "#E0E0E0",
      marginBottom: 24,
    }}
  >
    <div
      style={{
        fontSize: 14,
        fontWeight: 700,
        marginBottom: 16,
        color: "#D4AF37",
      }}
    >
      Open Grid Trades
    </div>
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ color: "#888" }}>
          <th align="left">#</th>
          <th align="left">Symbol</th>
          <th align="left">Type</th>
          <th align="right">Entry</th>
          <th align="right">Lot</th>
          <th align="right">PnL</th>
          <th align="right">Status</th>
        </tr>
      </thead>
      <tbody>
        {trades.length === 0 && (
          <tr>
            <td
              colSpan={7}
              style={{ color: "#888", textAlign: "center", padding: 16 }}
            >
              No open trades
            </td>
          </tr>
        )}
        {trades.map((t, i) => (
          <tr key={t.id || i} style={{ borderTop: "1px solid #23262D" }}>
            <td>{i + 1}</td>
            <td>{t.symbol}</td>
            <td>{t.type}</td>
            <td align="right">{t.entryPrice}</td>
            <td align="right">{t.lotSize}</td>
            <td
              align="right"
              style={{ color: t.pnl >= 0 ? "#00FF85" : "#FF4D4D" }}
            >
              {t.pnl}
            </td>
            <td align="right">{t.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
