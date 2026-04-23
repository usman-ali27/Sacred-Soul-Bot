"use client";
import { useState, useEffect } from "react";
import { tradingApi } from "../utils/api";

interface ConfigFormProps {
  config: any;
  options: any;
  onUpdate: () => void;
}

export const ConfigForm = ({ config, options, onUpdate }: ConfigFormProps) => {
  const [formData, setFormData] = useState<any>(config);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setFormData(config);
  }, [config]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target as HTMLInputElement;
    const val = type === "checkbox" ? (e.target as HTMLInputElement).checked : value;
    
    setFormData({
      ...formData,
      [name]: type === "number" ? parseFloat(value) : val,
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await tradingApi.updateConfig(formData);
      onUpdate();
      alert("Configuration updated successfully!");
    } catch (err) {
      console.error("Failed to update config", err);
      alert("Failed to update configuration");
    } finally {
      setLoading(false);
    }
  };

  if (!formData) return <div>Loading config...</div>;

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Core Settings */}
        <section style={sectionStyle}>
          <h3 style={headerStyle}>Core Parameters</h3>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Symbol</label>
            <select name="symbol" value={formData.symbol} onChange={handleChange} style={inputStyle}>
              {Object.keys(options?.instruments || {}).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Timeframe</label>
            <select name="timeframe" value={formData.timeframe} onChange={handleChange} style={inputStyle}>
              {Object.keys(options?.timeframes || {}).map(tf => <option key={tf} value={tf}>{tf}</option>)}
            </select>
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Base Lot</label>
            <input type="number" name="base_lot" value={formData.base_lot} onChange={handleChange} step="0.01" style={inputStyle} />
          </div>
          <div style={{ display: "flex", gap: 12 }}>
             <div style={fieldGroupStyle}>
                <label style={labelStyle}>Buy Levels</label>
                <input type="number" name="levels_buy" value={formData.levels_buy} onChange={handleChange} style={inputStyle} />
             </div>
             <div style={fieldGroupStyle}>
                <label style={labelStyle}>Sell Levels</label>
                <input type="number" name="levels_sell" value={formData.levels_sell} onChange={handleChange} style={inputStyle} />
             </div>
          </div>
        </section>

        {/* Multipliers */}
        <section style={sectionStyle}>
          <h3 style={headerStyle}>Strategy Multipliers</h3>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Spacing Multiplier (ATR x ?)</label>
            <input type="number" name="spacing_multiplier" value={formData.spacing_multiplier} onChange={handleChange} step="0.1" style={inputStyle} />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>TP Multiplier (Spacing x ?)</label>
            <input type="number" name="tp_multiplier" value={formData.tp_multiplier} onChange={handleChange} step="0.1" style={inputStyle} />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>SL Multiplier (Spacing x ?)</label>
            <input type="number" name="sl_multiplier" value={formData.sl_multiplier} onChange={handleChange} step="0.1" style={inputStyle} />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Max Open Levels</label>
            <input type="number" name="max_open_levels" value={formData.max_open_levels} onChange={handleChange} style={inputStyle} />
          </div>
        </section>

        {/* Basket Settings */}
        <section style={sectionStyle}>
          <h3 style={headerStyle}>Basket Management</h3>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Take Profit (USD)</label>
            <input type="number" name="basket_take_profit_usd" value={formData.basket_take_profit_usd} onChange={handleChange} style={inputStyle} />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Stop Loss (USD)</label>
            <input type="number" name="basket_stop_loss_usd" value={formData.basket_stop_loss_usd} onChange={handleChange} style={inputStyle} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <input type="checkbox" name="basket_close_on_profit" checked={formData.basket_close_on_profit} onChange={handleChange} />
            <label style={labelStyle}>Close on Profit</label>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <input type="checkbox" name="basket_close_on_loss" checked={formData.basket_close_on_loss} onChange={handleChange} />
            <label style={labelStyle}>Close on Loss</label>
          </div>
        </section>

        {/* AI Guards */}
        <section style={sectionStyle}>
          <h3 style={headerStyle}>AI & Risk Guards</h3>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <input type="checkbox" name="ai_direction_enabled" checked={formData.ai_direction_enabled} onChange={handleChange} />
            <label style={labelStyle}>Enable AI Direction Bias</label>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <input type="checkbox" name="ai_spacing_enabled" checked={formData.ai_spacing_enabled} onChange={handleChange} />
            <label style={labelStyle}>Enable Dynamic AI Spacing</label>
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Max Daily Loss (USD)</label>
            <input type="number" name="max_daily_loss_usd" value={formData.max_daily_loss_usd} onChange={handleChange} style={inputStyle} />
          </div>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Max Drawdown (%)</label>
            <input type="number" name="max_drawdown_pct" value={formData.max_drawdown_pct} onChange={handleChange} style={inputStyle} />
          </div>
        </section>
      </div>

      <button
        type="submit"
        disabled={loading}
        style={{
          padding: "16px",
          background: "#00D1FF",
          color: "#000",
          border: "none",
          borderRadius: 4,
          fontWeight: 800,
          cursor: "pointer",
          fontSize: 16,
          textTransform: "uppercase",
          marginTop: 12,
        }}
      >
        {loading ? "Updating..." : "Save Configuration"}
      </button>
    </form>
  );
};

const sectionStyle = {
  background: "#16181D",
  padding: 24,
  borderRadius: 8,
  border: "1px solid rgba(255,255,255,0.05)",
};

const headerStyle = {
  fontSize: 14,
  color: "#D4AF37",
  textTransform: "uppercase" as const,
  letterSpacing: 1,
  marginBottom: 20,
  borderBottom: "1px solid rgba(212,175,55,0.2)",
  paddingBottom: 8,
};

const fieldGroupStyle = {
  display: "flex",
  flexDirection: "column" as const,
  gap: 8,
  marginBottom: 16,
};

const labelStyle = {
  fontSize: 12,
  color: "#888",
  fontWeight: 600,
};

const inputStyle = {
  background: "#0D0E12",
  border: "1px solid rgba(255,255,255,0.1)",
  padding: "10px 12px",
  color: "#fff",
  borderRadius: 4,
  fontSize: 14,
};
