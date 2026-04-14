"""
Data fetching utilities for the ICT Bot dashboard.

Uses yfinance to download OHLCV data and provides resampling
for timeframes not natively supported (e.g. 4h).
"""

import pandas as pd
import yfinance as yf

from config import INSTRUMENTS, MAX_PERIOD


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
