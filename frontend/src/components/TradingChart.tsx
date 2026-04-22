import React from "react";

export const TradingChart = ({
  data,
}: {
  data: { time: string; price: number }[];
}) => {
  if (!data || data.length === 0)
    return (
      <div
        style={{
          minHeight: 300,
          background: "#23262D",
          borderRadius: 8,
          padding: 24,
        }}
      >
        No chart data
      </div>
    );
  const minPrice = Math.min(...data.map((d) => d.price)) - 2;
  const maxPrice = Math.max(...data.map((d) => d.price)) + 2;
  return (
    <div
      style={{
        width: "100%",
        minHeight: 300,
        background: "#23262D",
        borderRadius: 8,
        padding: 24,
      }}
    >
      <div style={{ fontSize: 12, color: "#888", marginBottom: 8 }}>
        Trading Chart (placeholder)
      </div>
      <svg
        width="100%"
        height="200"
        viewBox={`0 0 400 200`}
        style={{ background: "none" }}
      >
        {/* Simple line chart placeholder */}
        <polyline
          fill="none"
          stroke="#D4AF37"
          strokeWidth="2"
          points={data
            .map(
              (d, i) =>
                `${(i / (data.length - 1)) * 400},${200 - ((d.price - minPrice) / (maxPrice - minPrice)) * 180}`,
            )
            .join(" ")}
        />
      </svg>
    </div>
  );
};
