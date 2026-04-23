import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const tradingApi = {
  getStatus: () => apiClient.get('/status'),
  getAccount: () => apiClient.get('/mt5/account'),
  getTicker: (symbol: string = 'XAUUSD') => apiClient.get(`/market/ticker?symbol=${symbol}`),
  getSignals: (symbol: string = 'XAUUSD', tf: string = '15m') => apiClient.get(`/market/signals?symbol=${symbol}&timeframe=${tf}`),
  getBotState: () => apiClient.get('/bot/state'),
  getConfig: () => apiClient.get('/bot/config'),
  updateConfig: (config: any) => apiClient.post('/bot/config', config),
  connectMt5: (creds: any) => apiClient.post('/mt5/connect', creds),
  getOptions: () => apiClient.get('/config/options'),
  getLogs: (limit: number = 100) => apiClient.get(`/bot/logs?limit=${limit}`),
  runBacktest: (params: any) => apiClient.post('/bot/backtest', params),
  activateBot: () => apiClient.post('/bot/activate'),
  deactivateBot: () => apiClient.post('/bot/deactivate'),
  getPositions: () => apiClient.get('/mt5/positions'),
  getLevels: () => apiClient.get('/bot/levels'),
  propSim: (params: any) => apiClient.post('/bot/prop-sim', params),
  getNews: () => apiClient.get('/news'),
  getAnalysis: (symbol: string = 'XAUUSD', tf: string = '15m') => apiClient.get(`/market/analysis?symbol=${symbol}&timeframe=${tf}`),
  getSignalBridge: () => apiClient.get('/bot/signals'),
};
