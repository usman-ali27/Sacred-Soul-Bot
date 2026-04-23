import api from "../lib/api";

export async function getStatus() {
  const res = await api.get("/status");
  return res.data;
}

export async function mt5Connect(credentials: any) {
  const res = await api.post("/mt5/connect", credentials);
  return res.data;
}

export async function mt5Status() {
  const res = await api.get("/mt5/status");
  return res.data;
}

export async function botStart(config: any) {
  const res = await api.post("/bot/start", config);
  return res.data;
}

export async function botStop() {
  const res = await api.post("/bot/stop");
  return res.data;
}

export async function botConfig() {
  const res = await api.get("/bot/config");
  return res.data;
}

export async function aiInsight() {
  const res = await api.get("/ai/insight");
  return res.data;
}

export async function backtestRun() {
  const res = await api.get("/backtest/run");
  return res.data;
}
export async function getNews() {
  const res = await api.get("/news");
  return res.data;
}
