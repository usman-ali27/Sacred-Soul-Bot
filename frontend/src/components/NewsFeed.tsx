import React from "react";

export const NewsFeed = ({ items, guard }: { items: any[], guard?: { blocked: boolean, reason: string } }) => {
  const isBlocked = guard?.blocked || false;
  const reason = guard?.reason || "Buffer Clear";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 16,
        maxHeight: 500,
        overflowY: "auto",
        paddingRight: 8,
      }}
    >
      {/* News Guard Header */}
      <div style={{ 
        textAlign: "center", 
        padding: 20, 
        background: isBlocked ? "rgba(255,77,77,0.05)" : "rgba(0,255,133,0.05)",
        border: `1px solid ${isBlocked ? "rgba(255,77,77,0.15)" : "rgba(0,255,133,0.15)"}`,
        borderRadius: 8,
        marginBottom: 8 
      }}>
        <div style={{ fontSize: 24, marginBottom: 4 }}>{isBlocked ? "🚨" : "🛡️"}</div>
        <div
          style={{
            fontSize: 10,
            fontWeight: "bold",
            textTransform: "uppercase",
            letterSpacing: 2,
            color: isBlocked ? "#FF4D4D" : "#00FF85"
          }}
        >
          {reason}
        </div>
      </div>

      {items.length === 0 && !isBlocked && (
        <div style={{ textAlign: "center", padding: 20, color: "#888", fontSize: 12 }}>
          No high impact news scheduled for today.
        </div>
      )}

      {items.map((item, idx) => (
        <div
          key={idx}
          style={{
            padding: 16,
            background: "#16181D",
            border: "1px solid rgba(255,255,255,0.05)",
            borderRadius: 6,
          }}
        >
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 8,
                }}
              >
                <span
                  style={{
                    fontSize: 9,
                    fontWeight: "bold",
                    textTransform: "uppercase",
                    color: "#D4AF37",
                    background: "rgba(212,175,55,0.1)",
                    borderRadius: 4,
                    padding: "2px 6px",
                  }}
                >
                  HIGH IMPACT
                </span>
                <span style={{ fontSize: 10, color: "#888", fontWeight: "bold" }}>
                  {item.time_str}
                </span>
              </div>
              <div style={{ fontSize: 13, color: "#E0E0E0", fontWeight: 500 }}>
                {item.title}
              </div>
              <div style={{ fontSize: 10, color: "#666", marginTop: 4, textTransform: "uppercase" }}>
                USD • {item.country}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
