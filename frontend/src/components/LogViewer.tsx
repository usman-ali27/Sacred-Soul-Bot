"use client";

export const LogViewer = ({ logs }: { logs: any[] }) => {
  if (!logs || logs.length === 0) return <div style={{ color: "#444", textAlign: "center", padding: 20 }}>No logs available</div>;

  return (
    <div style={{ background: "#16181D", borderRadius: 8, border: "1px solid rgba(255,255,255,0.05)", overflow: "hidden" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.05)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ fontSize: 12, color: "#D4AF37", textTransform: "uppercase", letterSpacing: 1, margin: 0 }}>Execution Logs</h3>
        <span style={{ fontSize: 10, color: "#444" }}>Latest {logs.length} events</span>
      </div>
      <div style={{ maxHeight: 300, overflowY: "auto", fontFamily: "monospace", fontSize: 11 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead style={{ position: "sticky", top: 0, background: "#16181D", color: "#888", textAlign: "left" }}>
            <tr>
              <th style={thStyle}>Time</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Dir</th>
              <th style={thStyle}>Detail</th>
              <th style={thStyle}>Price</th>
              <th style={thStyle}>PnL</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log, i) => {
              // Real mt5_audit_log.jsonl fields:
              // status, reason, direction, symbol, signal_entry, live_price,
              // entry, lot_size, profit_usd, order_id, timestamp
              const status = log.status || log.event || "—";
              const detail = log.reason || log.message || "";
              const direction = log.direction || "";
              const price = log.entry || log.live_price || log.signal_entry || log.price || null;
              const pnl = log.profit_usd;
              const timeStr = log.timestamp?.split("T")[1]?.split(".")[0] ?? "—";

              return (
                <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.02)", verticalAlign: "top" }}>
                  <td style={{ ...tdStyle, whiteSpace: "nowrap" }}>{timeStr}</td>
                  <td style={{ ...tdStyle, color: getStatusColor(status), fontWeight: 700 }}>{status}</td>
                  <td style={{
                    ...tdStyle,
                    color: (direction === "LONG" || direction === "BUY") ? "#00FF85"
                          : (direction === "SHORT" || direction === "SELL") ? "#FF4D4D"
                          : "#666"
                  }}>
                    {direction || "—"}
                  </td>
                  <td style={{ ...tdStyle, color: "#888", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {detail}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>
                    {price != null ? `$${Number(price).toFixed(2)}` : "—"}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right", color: pnl != null ? (pnl >= 0 ? "#00FF85" : "#FF4D4D") : "#555" }}>
                    {pnl != null ? `${pnl >= 0 ? "+" : ""}$${Number(pnl).toFixed(2)}` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const getStatusColor = (status: string) => {
  switch ((status || "").toUpperCase()) {
    case "FILLED":   return "#00FF85";
    case "CLOSED":   return "#00D1FF";
    case "TEST_OK":  return "#D4AF37";
    case "BLOCKED":  return "#FF9500";
    case "FAILED":   return "#FF4D4D";
    case "ERROR":    return "#FF4D4D";
    default:         return "#888";
  }
};

const thStyle: React.CSSProperties = {
  padding: "8px 12px",
  fontWeight: 600,
  borderBottom: "1px solid rgba(255,255,255,0.05)",
  fontSize: 10,
  letterSpacing: 1,
  textTransform: "uppercase",
};
const tdStyle: React.CSSProperties = { padding: "8px 12px", color: "#ccc" };
