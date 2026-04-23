"use client";
import { useState } from "react";
import { tradingApi } from "../utils/api";

export const ConnectModal = ({ isOpen, onClose, onSuccess }: any) => {
  const [creds, setCreds] = useState({
    login: "",
    password: "",
    server: ""
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!isOpen) return null;

  const handleConnect = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await tradingApi.connectMt5({
        login: parseInt(creds.login),
        password: creds.password,
        server: creds.server
      });
      if (res.data.status === "connected") {
        onSuccess();
        onClose();
      } else {
        setError(res.data.message || "Failed to connect");
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Connection failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <h2 style={{ color: "#D4AF37", marginBottom: 20 }}>Connect to MT5</h2>
        
        <div style={fieldStyle}>
          <label style={labelStyle}>MT5 Login</label>
          <input 
            style={inputStyle} 
            type="number" 
            placeholder="e.g. 1513116939"
            value={creds.login}
            onChange={e => setCreds({...creds, login: e.target.value})}
          />
        </div>

        <div style={fieldStyle}>
          <label style={labelStyle}>Password</label>
          <input 
            style={inputStyle} 
            type="password" 
            placeholder="MT5 Password"
            value={creds.password}
            onChange={e => setCreds({...creds, password: e.target.value})}
          />
        </div>

        <div style={fieldStyle}>
          <label style={labelStyle}>Server</label>
          <input 
            style={inputStyle} 
            type="text" 
            placeholder="e.g. FTMO-Demo"
            value={creds.server}
            onChange={e => setCreds({...creds, server: e.target.value})}
          />
        </div>

        {error && <div style={{ color: "#FF4D4D", fontSize: 12, marginBottom: 16 }}>{error}</div>}

        <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
          <button onClick={onClose} style={secondaryBtnStyle}>Cancel</button>
          <button 
            onClick={handleConnect} 
            disabled={loading}
            style={primaryBtnStyle}
          >
            {loading ? "Connecting..." : "Save & Connect"}
          </button>
        </div>
      </div>
    </div>
  );
};

const overlayStyle: any = {
  position: "fixed",
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: "rgba(0,0,0,0.85)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalStyle = {
  background: "#16181D",
  padding: 32,
  borderRadius: 12,
  width: "100%",
  maxWidth: 400,
  border: "1px solid rgba(255,255,255,0.1)",
  boxShadow: "0 20px 40px rgba(0,0,0,0.4)"
};

const fieldStyle = { marginBottom: 20 };
const labelStyle = { display: "block", color: "#888", fontSize: 12, marginBottom: 8, textTransform: "uppercase" as const, fontWeight: 700 };
const inputStyle = { width: "100%", background: "#0D0E12", border: "1px solid #333", padding: "12px", borderRadius: 4, color: "#fff" };

const primaryBtnStyle = { flex: 1, padding: "12px", background: "#D4AF37", border: "none", borderRadius: 4, fontWeight: 800, cursor: "pointer", color: "#000" };
const secondaryBtnStyle = { flex: 1, padding: "12px", background: "transparent", border: "1px solid #333", borderRadius: 4, fontWeight: 800, cursor: "pointer", color: "#888" };
