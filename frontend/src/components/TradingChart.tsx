"use client";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend, ReferenceArea
} from "recharts";

interface Level {
  level_id: string;
  price: number;
  direction: string;
  status: string;
  sl_price: number;
  tp_price: number;
  lot: number;
}

interface Analysis {
  fvgs: { time: string; type: string; top: number; bottom: number }[];
  sweeps: { time: string; type: string; price: number }[];
}

interface Props {
  data: { time: string; price: number }[];
  levels?: Level[];
  anchorPrice?: number;
  analysis?: Analysis | null;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#16181D", border: "1px solid rgba(212,175,55,0.3)", borderRadius: 6, padding: "8px 12px" }}>
      <div style={{ fontSize: 10, color: "#666", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#D4AF37" }}>
        ${payload[0]?.value?.toFixed(2)}
      </div>
    </div>
  );
};

export const TradingChart = ({ data, levels = [], anchorPrice, analysis }: Props) => {
  const validData = data.filter(d => d.price > 0);

  if (!validData.length) {
    return (
      <div style={{ minHeight: 320, background: "#16181D", borderRadius: 8, padding: 24, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "#444", fontSize: 13 }}>Waiting for price data…</div>
      </div>
    );
  }

  const prices = validData.map(d => d.price);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const pad = (maxP - minP) * 0.15 || 5;
  const yMin = Math.floor(minP - pad);
  const yMax = Math.ceil(maxP + pad);

  // Separate pending and open levels
  const pendingBuy  = levels.filter(l => l.direction === "BUY"  && l.status === "PENDING");
  const pendingSell = levels.filter(l => l.direction === "SELL" && l.status === "PENDING");
  const openLevels  = levels.filter(l => l.status === "OPEN");

  return (
    <div style={{ background: "#16181D", borderRadius: 8, padding: "20px 16px 12px", border: "1px solid rgba(255,255,255,0.05)" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 12, color: "#D4AF37", fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>
          XAUUSD — Live Price
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: 10 }}>
          <span style={{ color: "#00FF85" }}>▬ BUY levels ({pendingBuy.length})</span>
          <span style={{ color: "#FF4D4D" }}>▬ SELL levels ({pendingSell.length})</span>
          {openLevels.length > 0 && <span style={{ color: "#00D1FF" }}>● OPEN ({openLevels.length})</span>}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={validData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#D4AF37" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#D4AF37" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey="time"
            tick={{ fill: "#555", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[yMin, yMax]}
            tick={{ fill: "#555", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={v => `$${v}`}
            width={64}
          />
          <Tooltip content={<CustomTooltip />} />

          {/* Anchor price line */}
          {anchorPrice && anchorPrice > 0 && (
            <ReferenceLine
              y={anchorPrice}
              stroke="rgba(212,175,55,0.5)"
              strokeDasharray="6 3"
              label={{ value: `Anchor $${anchorPrice.toFixed(2)}`, fill: "#D4AF37", fontSize: 9, position: "insideTopRight" }}
            />
          )}

          {/* BUY pending levels — green dashed */}
          {pendingBuy.map((l, i) => (
            <ReferenceLine
              key={`pending-buy-${l.level_id}-${i}`}
              y={l.price}
              stroke="rgba(0,255,133,0.55)"
              strokeDasharray="4 3"
              strokeWidth={1.5}
              label={{ value: `${l.level_id} $${l.price.toFixed(0)}`, fill: "#00FF85", fontSize: 8, position: "insideTopRight" }}
            />
          ))}

          {/* SELL pending levels — red dashed */}
          {pendingSell.map((l, i) => (
            <ReferenceLine
              key={`pending-sell-${l.level_id}-${i}`}
              y={l.price}
              stroke="rgba(255,77,77,0.55)"
              strokeDasharray="4 3"
              strokeWidth={1.5}
              label={{ value: `${l.level_id} $${l.price.toFixed(0)}`, fill: "#FF4D4D", fontSize: 8, position: "insideTopRight" }}
            />
          ))}

          {/* OPEN levels — bright solid */}
          {openLevels.map((l, i) => (
            <ReferenceLine
              key={`open-${l.level_id}-${i}`}
              y={l.price}
              stroke="#00D1FF"
              strokeWidth={2}
              label={{ value: `OPEN $${l.price.toFixed(0)}`, fill: "#00D1FF", fontSize: 8, position: "insideTopRight" }}
            />
          ))}

          {/* ICT FVGs */}
          {analysis?.fvgs?.map((fvg, i) => (
            <ReferenceArea
              key={`fvg-${i}`}
              y1={fvg.bottom}
              y2={fvg.top}
              fill={fvg.type === "bullish" ? "rgba(0, 255, 133, 0.1)" : "rgba(255, 77, 77, 0.1)"}
              stroke={fvg.type === "bullish" ? "rgba(0, 255, 133, 0.2)" : "rgba(255, 77, 77, 0.2)"}
              strokeDasharray="2 2"
            />
          ))}

          {/* ICT Sweeps */}
          {analysis?.sweeps?.map((sweep, i) => (
            <ReferenceLine
              key={`sweep-${i}`}
              y={sweep.price}
              stroke={sweep.type === "bullish" ? "#00FF85" : "#FF4D4D"}
              strokeWidth={1}
              strokeDasharray="1 4"
              label={{ value: `SWEEP`, fill: sweep.type === "bullish" ? "#00FF85" : "#FF4D4D", fontSize: 7, position: "insideLeft" }}
            />
          ))}

          {/* Price area */}
          <Area
            type="monotone"
            dataKey="price"
            stroke="#D4AF37"
            strokeWidth={2}
            fill="url(#priceGrad)"
            dot={false}
            activeDot={{ r: 4, fill: "#D4AF37" }}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Grid Level Legend Table */}
      {levels.length > 0 && (
        <div style={{ marginTop: 12, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10, fontFamily: "monospace" }}>
            <thead>
              <tr style={{ color: "#555", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                {["Level", "Dir", "Price", "SL", "TP", "Lot", "Status"].map(h => (
                  <th key={h} style={{ padding: "4px 8px", textAlign: "left", fontWeight: 700, letterSpacing: 1 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {levels.map((l, i) => (
                <tr key={`${l.level_id}-${l.status}-${i}`} style={{ borderBottom: "1px solid rgba(255,255,255,0.02)" }}>
                  <td style={{ padding: "4px 8px", color: "#888" }}>{l.level_id}</td>
                  <td style={{ padding: "4px 8px", color: l.direction === "BUY" ? "#00FF85" : "#FF4D4D", fontWeight: 700 }}>{l.direction}</td>
                  <td style={{ padding: "4px 8px", color: "#E0E0E0" }}>${l.price.toFixed(2)}</td>
                  <td style={{ padding: "4px 8px", color: "#FF6B6B" }}>${l.sl_price.toFixed(2)}</td>
                  <td style={{ padding: "4px 8px", color: "#00FF85" }}>${l.tp_price.toFixed(2)}</td>
                  <td style={{ padding: "4px 8px", color: "#888" }}>{l.lot}</td>
                  <td style={{ padding: "4px 8px" }}>
                    <span style={{
                      padding: "1px 6px",
                      borderRadius: 4,
                      fontSize: 9,
                      fontWeight: 700,
                      background: l.status === "OPEN" ? "rgba(0,209,255,0.12)"
                                : l.status === "PENDING" ? "rgba(212,175,55,0.1)"
                                : "rgba(255,255,255,0.05)",
                      color: l.status === "OPEN" ? "#00D1FF"
                           : l.status === "PENDING" ? "#D4AF37"
                           : "#555",
                    }}>
                      {l.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
