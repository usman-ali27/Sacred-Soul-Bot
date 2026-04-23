"""
Data fetching utilities for the ICT Bot dashboard.

Uses yfinance to download OHLCV data and provides resampling
for timeframes not natively supported (e.g. 4h).
"""

import pandas as pd
import MetaTrader5 as mt5
import yfinance as yf
from config import INSTRUMENTS, MAX_PERIOD, MT5_TIMEFRAME_MAP


def fetch_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame:
    """Download OHLCV data from yfinance.

    Args:
        symbol: One of the keys in INSTRUMENTS (e.g. "XAUUSD").
        timeframe: One of "1m", "5m", "15m", "1h", "4h", "Daily".

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume] and a
        DatetimeIndex named 'Datetime'.
    """
    ticker = INSTRUMENTS[symbol]
    yf_interval = timeframe if timeframe != "Daily" else "1d"

    # 1. Try MT5 first
    try:
        if mt5.initialize():
            # Get bars from MT5
            mt5_tf = MT5_TIMEFRAME_MAP.get(timeframe)
            if mt5_tf is not None:
                # Map symbol (e.g. XAUUSD -> XAUUSD)
                mt5_symbol = symbol # Usually the same, or use a map if needed
                # Fetch 1000 bars
                rates = mt5.copy_rates_from_pos(mt5_symbol, mt5_tf, 0, 1000)
                if rates is not None and len(rates) > 0:
                    df = pd.DataFrame(rates)
                    df['time'] = pd.to_datetime(df['time'], unit='s')
                    df.set_index('time', inplace=True)
                    df.rename(columns={
                        'open': 'Open', 'high': 'High', 'low': 'Low', 
                        'close': 'Close', 'tick_volume': 'Volume'
                    }, inplace=True)
                    df.index.name = "Datetime"
                    return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except Exception as e:
        print(f"MT5 fetch failed, falling back to yfinance: {e}")

    # 2. Fallback to yfinance
    if timeframe == "4h":
        # yfinance has no 4h interval; fetch 1h and resample
        period = MAX_PERIOD["4h"]
        raw = yf.download(ticker, period=period, interval="1h", progress=False)
        df = _resample(raw, "4h")
    else:
        period = MAX_PERIOD.get(timeframe, "60d")
        df = yf.download(ticker, period=period, interval=yf_interval, progress=False)

    if df.empty:
        return df

    # Flatten MultiIndex columns if present (yfinance >= 0.2.36)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.index.name = "Datetime"
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV data to a coarser timeframe."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    agg = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
    return df.resample(rule).agg(agg).dropna()
