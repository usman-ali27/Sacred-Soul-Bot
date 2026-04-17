# Grid Bot

A high-performance, minimal Python bot for grid trading on MetaTrader 5 (MT5).

## Features

- Simple UI: Connect MT5 account, configure grid, run.
- No unnecessary re-rendering; bot runs analysis and grid setup every 1 minute.
- Auto-reconnects and resumes execution if internet drops.
- Auto-enables execution after connect.
- All actions are automatic after start, until user stops.
- Fast, optimized, minimal UI.
- Includes a 'brain' module for future prediction and learning.

## Quick Start

1. Install requirements: `pip install -r requirements.txt`
2. Run: `python main.py`

## Requirements

- Python 3.9+
- MetaTrader5 Python package
- Streamlit (for UI)

## Roadmap

- [ ] Core MT5 connection and auto-reconnect
- [ ] Grid trading logic and settings
- [ ] Brain module for learning/prediction
- [ ] Minimal UI (connect, configure, run)
- [ ] Robust error handling and auto-resume

---

This project is focused on speed, reliability, and future extensibility. No legacy code from ICT bot is included.
