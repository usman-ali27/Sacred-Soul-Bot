import React from "react";

export const AccountStats = ({
  status,
  progressToTarget,
  targetAmount,
  currentProfit,
  totalPnL,
  activeTradesCount,
  calculateVolatility,
  mt5Status,
  autoTrading,
  maxDailyLossPct = 5,
  maxTotalDDPct   = 10,
}: any) => {
  // Convert pct props to fractions for comparison
  const dailyLimitFraction = maxDailyLossPct / 100;
  const totalLimitFraction = maxTotalDDPct / 100;
  return (
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
          fontSize: 12,
          fontWeight: "bold",
          textTransform: "uppercase",
          color: "#888",
          marginBottom: 12,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        Account Phase {status?.phase || "-"}
        <span style={{ color: "#D4AF37" }}>Prop Eval</span>
      </div>
      <div style={{ marginBottom: 24 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "end",
            marginBottom: 8,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: "#888",
              textTransform: "uppercase",
              fontWeight: "bold",
            }}
          >
            Target Profit
          </span>
          <span
            style={{ fontSize: 13, fontFamily: "monospace", color: "#D4AF37" }}
          >
            {progressToTarget?.toFixed(1) || 0}%
          </span>
        </div>
        <div
          style={{
            height: 4,
            background: "#23262D",
            borderRadius: 4,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              background: "linear-gradient(to right, #D4AF37, #D4AF37AA)",
              width: `${progressToTarget || 0}%`,
            }}
          />
        </div>
        <div
          style={{
            marginTop: 8,
            fontFamily: "monospace",
            fontSize: 14,
            textAlign: "right",
          }}
        >
          ${currentProfit?.toFixed(2) || 0} / $
          {targetAmount?.toLocaleString() || 0}
        </div>
      </div>
      <div style={{ display: "flex", gap: 24 }}>
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 4,
            }}
          >
            <span
              style={{
                fontSize: 11,
                color: "#888",
                textTransform: "uppercase",
                fontWeight: "bold",
              }}
            >
              Daily Drawdown
            </span>
            <span
              style={{
                fontSize: 12,
                fontFamily: "monospace",
                color: status?.dailyLoss > dailyLimitFraction * 0.8 ? "#FF4D4D" : "#888",
              }}
            >
              {((status?.dailyLoss || 0) * 100).toFixed(2)}%
            </span>
          </div>
          <div
            style={{
              height: 2,
              background: "#23262D",
              borderRadius: 4,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                background: "#FF4D4D",
                width: `${Math.min(100, ((status?.dailyLoss || 0) / dailyLimitFraction) * 100)}%`,
              }}
            ></div>
          </div>
        </div>
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 4,
            }}
          >
            <span
              style={{
                fontSize: 11,
                color: "#888",
                textTransform: "uppercase",
                fontWeight: "bold",
              }}
            >
              Max Drawdown
            </span>
            <span
              style={{
                fontSize: 12,
                fontFamily: "monospace",
                color: status?.totalLoss > totalLimitFraction * 0.8 ? "#FF4D4D" : "#888",
              }}
            >
              {((status?.totalLoss || 0) * 100).toFixed(2)}%
            </span>
          </div>
          <div
            style={{
              height: 2,
              background: "#23262D",
              borderRadius: 4,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                background: "#FF4D4D",
                width: `${Math.min(100, ((status?.totalLoss || 0) / totalLimitFraction) * 100)}%`,
              }}
            ></div>
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 24, marginTop: 16 }}>
        <div
          style={{
            background: "#23262D",
            padding: 12,
            borderRadius: 6,
            textAlign: "center",
            flex: 1,
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: "#888",
              marginBottom: 4,
              textTransform: "uppercase",
              fontWeight: "bold",
              letterSpacing: 1,
            }}
          >
            Equity
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 14,
              fontWeight: "bold",
              color: "#E0E0E0",
            }}
          >
            ${status?.equity?.toLocaleString() || 0}
          </div>
        </div>
        <div
          style={{
            background: "#23262D",
            padding: 12,
            borderRadius: 6,
            textAlign: "center",
            flex: 1,
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: "#888",
              marginBottom: 4,
              textTransform: "uppercase",
              fontWeight: "bold",
              letterSpacing: 1,
            }}
          >
            PnL
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 14,
              fontWeight: "bold",
              color: totalPnL >= 0 ? "#00FF85" : "#FF4D4D",
            }}
          >
            {totalPnL}
          </div>
        </div>
        <div
          style={{
            background: "#23262D",
            padding: 12,
            borderRadius: 6,
            textAlign: "center",
            flex: 1,
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: "#888",
              marginBottom: 4,
              textTransform: "uppercase",
              fontWeight: "bold",
              letterSpacing: 1,
            }}
          >
            Orders
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 14,
              fontWeight: "bold",
              color: "#E0E0E0",
            }}
          >
            {activeTradesCount}
          </div>
        </div>
        <div
          style={{
            background: "#23262D",
            padding: 12,
            borderRadius: 6,
            textAlign: "center",
            flex: 1,
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: "#888",
              marginBottom: 4,
              textTransform: "uppercase",
              fontWeight: "bold",
              letterSpacing: 1,
            }}
          >
            Volatility
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 14,
              fontWeight: "bold",
              color: "#D4AF37",
            }}
          >
            {calculateVolatility?.()}
          </div>
        </div>
      </div>
      <div
        style={{
          fontSize: 12,
          fontWeight: "bold",
          textTransform: "uppercase",
          color: "#888",
          marginTop: 24,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>MT5 Status:</span>
        <span
          style={{ color: mt5Status === "CONNECTED" ? "#00FF85" : "#FF4D4D" }}
        >
          {mt5Status}
        </span>
      </div>
      <div
        style={{
          fontSize: 12,
          fontWeight: "bold",
          textTransform: "uppercase",
          color: "#888",
          marginTop: 8,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>Grid Mode:</span>
        <span style={{ color: autoTrading ? "#00FF85" : "#888" }}>
          {autoTrading ? "Active" : "Standby"}
        </span>
      </div>
    </div>
  );
};
