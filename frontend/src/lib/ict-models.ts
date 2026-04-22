// ICT_BOT Trading Models

export interface MT5Credentials {
  server: string;
  login: string;
  password: string;
}

export interface BotConfig {
  symbol: string;
  lotSize: number;
  gridLevels: number;
  strategy: string;
  risk: number;
  [key: string]: any;
}

export interface BotStatus {
  running: boolean;
  pnl: number;
  openTrades: number;
  lastAction: string;
}

export interface AIInsight {
  sentiment: string;
  score: number;
  summary: string;
}

export interface BacktestResult {
  trades: number;
  profit: number;
  drawdown: number;
  details: any;
}
