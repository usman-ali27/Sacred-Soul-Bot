import React from "react";

export const NewsFeed = ({ items }: { items: any[] }) => {
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
      {items.length === 0 && (
        <div style={{ textAlign: "center", padding: 40, color: "#888" }}>
          <div style={{ fontSize: 24, opacity: 0.2 }}>🛡️</div>
          <div
            style={{
              fontSize: 11,
              fontWeight: "bold",
              textTransform: "uppercase",
              letterSpacing: 2,
            }}
          >
            News Guard: Buffer Clear
          </div>
        </div>
      )}
      {items.map((item) => (
        <div
          key={item.id}
          style={{
            padding: 16,
            background: "#16181D",
            border: "1px solid rgba(255,255,255,0.05)",
            borderRadius: 6,
            marginBottom: 8,
          }}
        >
          <div style={{ display: "flex", gap: 16 }}>
            <div
              style={{
                marginTop: 4,
                width: 32,
                height: 32,
                borderRadius: 16,
                background:
                  item.sentiment > 0
                    ? "rgba(0,255,133,0.05)"
                    : "rgba(255,77,77,0.05)",
                color: item.sentiment > 0 ? "#00FF85" : "#FF4D4D",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {item.sentiment > 0 ? "↑" : "↓"}
            </div>
            <div style={{ flex: 1 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  marginBottom: 8,
                }}
              >
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: "bold",
                    textTransform: "uppercase",
                    color:
                      item.impact === "HIGH"
                        ? "#D4AF37"
                        : item.impact === "MEDIUM"
                          ? "#00D1FF"
                          : "#888",
                    background:
                      item.impact === "HIGH"
                        ? "rgba(212,175,55,0.08)"
                        : item.impact === "MEDIUM"
                          ? "rgba(0,209,255,0.08)"
                          : "rgba(136,136,136,0.08)",
                    borderRadius: 4,
                    padding: "2px 6px",
                    marginRight: 8,
                  }}
                >
                  {item.impact} IMPACT
                </span>
                <span
                  style={{
                    fontSize: 10,
                    color: "#888",
                    fontWeight: "bold",
                    textTransform: "uppercase",
                    letterSpacing: 1,
                  }}
                >
                  Global Economics
                </span>
              </div>
              <div style={{ fontSize: 13, color: "#E0E0E0", fontWeight: 500 }}>
                {item.title}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
