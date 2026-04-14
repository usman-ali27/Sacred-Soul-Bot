"""
Configuration constants for the ICT Bot dashboard.
"""

# Supported instruments with their yfinance ticker symbols
INSTRUMENTS = {
    "XAUUSD": "GC=F",
    "EURUSD": "EURUSD=X",
    "NASDAQ": "NQ=F",
    "GBPUSD": "GBPUSD=X",
}

# Default instrument (used for backtesting and auto-trade)
DEFAULT_INSTRUMENT = "XAUUSD"

# Supported timeframes mapped to yfinance interval strings
TIMEFRAMES = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "Daily": "1d",
}

# yfinance max period per interval
MAX_PERIOD = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "1h": "730d",
    "4h": "730d",
    "Daily": "max",
}

# ── Trading Modes ─────────────────────────────────────────────────
TRADING_MODES = {
    "Scalping": {
        "description": "Fast entries on 1m–5m charts. Tight SL, quick TP.",
        "timeframes": ["1m", "5m"],
        "default_tf": "5m",
        "default_rr": 1.5,
        "sweep_lookback": 10,
        "cooldown_bars": 2,
        "default_lot": 0.02,
        "default_balance": 10_000,
        "recommended_concepts": ["Liquidity Sweep", "FVG", "Order Flow"],
    },
    "Intraday": {
        "description": "Entries on 15m–1h charts within a single session.",
        "timeframes": ["15m", "1h"],
        "default_tf": "1h",
        "default_rr": 2.0,
        "sweep_lookback": 20,
        "cooldown_bars": 5,
        "default_lot": 0.04,
        "default_balance": 10_000,
        "recommended_concepts": ["Liquidity Sweep", "MSS", "OB", "FVG"],
    },
    "Swing": {
        "description": "Multi-day holds on 4h–Daily charts.",
        "timeframes": ["4h", "Daily"],
        "default_tf": "4h",
        "default_rr": 3.0,
        "sweep_lookback": 30,
        "cooldown_bars": 8,
        "default_lot": 0.02,
        "default_balance": 10_000,
        "recommended_concepts": ["Liquidity Sweep", "MSS", "OB", "FVG", "OTE"],
    },
}

# Session times (UTC)
SESSIONS = {
    "Asian":  {"start": "00:00", "end": "06:00"},
    "London": {"start": "07:00", "end": "12:00"},
    "NY":     {"start": "12:00", "end": "17:00"},
}

# ---------------------------------------------------------------------------
# ICT Concepts — the ten building blocks
# ---------------------------------------------------------------------------
ALL_CONCEPTS = [
    "MSS",
    "Liquidity Sweep",
    "OB",
    "FVG",
    "OTE",
    "PO3",
    "SSL/BSL",
    "Breaker Block",
    "Mitigation",
    "Order Flow",
]

# Scenario presets (name → list of required concepts)
PRESETS = {
    "Liquidity Sweep + OB": ["Liquidity Sweep", "OB"],
    "FVG + OTE + Order Flow": ["FVG", "OTE", "Order Flow"],
    "MSS + Breaker Block + Mitigation": ["MSS", "Breaker Block", "Mitigation"],
    "Full ICT (excl. Order Flow)": [
        "MSS", "Liquidity Sweep", "OB", "FVG", "OTE",
        "PO3", "SSL/BSL", "Breaker Block", "Mitigation",
    ],
    "Minimal (Sweep + MSS)": ["Liquidity Sweep", "MSS"],
}

# ── MT5 defaults ──────────────────────────────────────────────────
MT5_SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "EURUSD": "EURUSD",
    "NASDAQ": "NAS100",
    "GBPUSD": "GBPUSD",
}

MT5_TIMEFRAME_MAP = {
    "1m": 1,    # mt5.TIMEFRAME_M1
    "5m": 5,    # mt5.TIMEFRAME_M5
    "15m": 15,  # mt5.TIMEFRAME_M15
    "1h": 16385,  # mt5.TIMEFRAME_H1
    "4h": 16388,  # mt5.TIMEFRAME_H4
    "Daily": 16408,  # mt5.TIMEFRAME_D1
}
