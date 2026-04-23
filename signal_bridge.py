import re
import logging
import json
import asyncio
import time
from typing import Optional, Dict, List
from pathlib import Path

# Try to import listeners, fail gracefully if not configured
try:
    from telethon import TelegramClient, events
except ImportError:
    TelegramClient = None

try:
    import discord
except ImportError:
    discord = None

# Setup logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("signal_bridge.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("signal_bridge")

SIGNAL_STATE_FILE = Path("signal_state.json")

class SignalParser:
    """
    Parses natural language signals from Telegram/Discord into structured trade data.
    """
    SYMBOL_MAP = {
        r"GOLD": "XAUUSD", 
        r"XAUUSD": "XAUUSD", 
        r"XAU": "XAUUSD",
        r"GC": "XAUUSD", # Futures ticker
        r"US30": "US30",
        r"NAS100": "NAS100",
        r"USTEC": "NAS100"
    }
    ACTION_MAP = {r"BUY": "BUY", r"SELL": "SELL", r"LONG": "BUY", r"SHORT": "SELL"}
    IGNORE_KEYWORDS = ["GOODNIGHT", "LETS SLEEP", "DAY END", "REMINDER", "CALCULATING", "SABR"]

    def __init__(self, target_symbol: str = "XAUUSD"):
        self.target_symbol = target_symbol

    def parse(self, text: str) -> Optional[Dict]:
        clean_text = text.upper()
        
        # 1. Check for ignores
        if any(kw in clean_text for kw in self.IGNORE_KEYWORDS):
            return {"type": "IGNORE"}

        # 2. Check for action
        action = next((act for p, act in self.ACTION_MAP.items() if re.search(p, clean_text)), None)
        
        # 3. Detect symbol (or default to target_symbol)
        symbol = self.target_symbol
        for pattern, actual_sym in self.SYMBOL_MAP.items():
            if re.search(pattern, clean_text):
                symbol = actual_sym
                break
        
        # Match numbers (prices)
        prices = re.findall(r"\d{2,5}(?:\.\d+)?", clean_text)
        
        # Special: BE (Break Even)
        if "BE" in clean_text or "BREAK EVEN" in clean_text:
            price = float(prices[0]) if prices else None
            return {"type": "BE", "price": price, "symbol": symbol}

        # Special: TP Open
        if "TP OPEN" in clean_text:
            return {"type": "TP_OPEN"}

        # Special: SL Update
        if "SL" in clean_text and prices:
            return {"type": "SL", "price": float(prices[0])}

        # If action found, it's likely a NEW signal
        if action:
            # Try to find entry price near the action
            entry = float(prices[0]) if prices else None
            # Some signals have SL and TP in the same message
            sl = None
            tp = None
            if "SL" in clean_text and len(prices) > 1:
                sl_match = re.search(r"SL\s*(\d+(?:\.\d+)?)", clean_text)
                if sl_match: sl = float(sl_match.group(1))
            
            if "TP" in clean_text:
                tp_match = re.search(r"TP\s*(\d+(?:\.\d+)?)", clean_text)
                if tp_match: tp = float(tp_match.group(1))

            return {
                "type": "NEW",
                "symbol": symbol,
                "action": action,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "raw": text
            }

        return None

class SignalBridge:
    def __init__(self, config_path: str = "signal_config.json"):
        self.config_path = Path(config_path)
        self.load_config()
        self.parser = SignalParser()
        self.memory = {}
        self.history = []
        self.is_active = False
        
        # Load MT5 creds for execution
        from mt5_trader import load_credentials, build_mt5_config_from_credentials
        creds = load_credentials()
        self.mt5_cfg = build_mt5_config_from_credentials(creds) if creds else None
        
        self.save_state()

    def load_config(self):
        self.config = json.loads(self.config_path.read_text())

    def save_state(self):
        state = {
            "is_active": self.is_active,
            "last_update": time.time(),
            "history": self.history[-10:], # Last 10 messages
            "memory": {k: {mk: mv for mk, mv in v.items() if mk != 'time'} for k, v in self.memory.items()}
        }
        SIGNAL_STATE_FILE.write_text(json.dumps(state, indent=2))

    async def start_discord(self):
        if not discord: 
            logger.error("Discord.py not installed.")
            return
        d_cfg = self.config.get("discord", {})
        if not d_cfg.get("token"): 
            logger.warning("Discord Token not configured.")
            return

        intents = discord.Intents.default()
        intents.message_content = True 
        client = discord.Client(intents=intents)
        self.is_active = True
        self.save_state()
        
        @client.event
        async def on_ready():
            logger.info(f"📡 Discord Listener Active as {client.user}")
            # Fetch history on startup
            for channel_id in d_cfg.get("channels", []):
                try:
                    channel = client.get_channel(int(channel_id))
                    if channel:
                        async for msg in channel.history(limit=10):
                            await self.process_message(str(msg.author.id), msg.content, "Discord History", execute=False)
                except Exception as e:
                    logger.error(f"Error fetching history for {channel_id}: {e}")

        @client.event
        async def on_message(message):
            if str(message.channel.id) in d_cfg.get("channels", []) or not d_cfg.get("channels"):
                await self.process_message(str(message.author.id), message.content, "Discord")

        try:
            await client.start(d_cfg["token"])
        except Exception as e:
            logger.error(f"Discord connection error: {e}")
            self.is_active = False
            self.save_state()

    async def start_telegram(self):
        if not TelegramClient:
            logger.error("Telethon not installed.")
            return
        t_cfg = self.config.get("telegram", {})
        if not t_cfg.get("api_id") or not t_cfg.get("api_hash"):
            logger.warning("Telegram API ID/Hash not configured.")
            return

        client = TelegramClient('sacred_soul_bridge', int(t_cfg["api_id"]), t_cfg["api_hash"])
        await client.start(phone=t_cfg.get("phone"))
        logger.info("📡 Telegram Listener Active")
        self.is_active = True
        self.save_state()

        @client.on(events.NewMessage(chats=t_cfg.get("channels", [])))
        async def handler(event):
            await self.process_message(str(event.sender_id), event.text, "Telegram")

        await client.run_until_disconnected()

    async def process_message(self, sender_id: str, text: str, source: str, execute: bool = True):
        now = time.time()
        # Clean old memory
        self.memory = {k: v for k, v in self.memory.items() if now - v['time'] < 60} # 60s window
        
        profile = self.memory.get(sender_id, {
            "symbol": None, "action": None, "entry": None, "sl": None, "tp": None, "time": now
        })
        
        res = self.parser.parse(text)
        status = "IGNORED"
        
        if res:
            if res["type"] == "NEW":
                profile.update({"symbol": res["symbol"], "action": res["action"], "entry": res["entry"]})
                status = f"NEW {res['action']}"
            elif res["type"] == "SL":
                profile["sl"] = res["price"]
                status = f"SL SET: {res['price']}"
            elif res["type"] == "TP_OPEN":
                profile["tp"] = 0
                status = "TP OPENED"
            elif res["type"] == "BE":
                profile["sl"] = res["price"] or profile["entry"]
                status = f"BE UPDATE: {profile['sl']}"
            elif res["type"] == "IGNORE":
                status = "IGNORE KEYWORD"

        # Record in history
        self.history.append({
            "time": time.strftime("%H:%M:%S"),
            "source": source,
            "text": text[:100],
            "status": status
        })
        
        profile["time"] = now
        self.memory[sender_id] = profile
        
        # Check if complete
        if profile["symbol"] and profile["action"] and (profile["sl"] is not None or profile["tp"] is not None):
            logger.info(f"🎯 SIGNAL COMPLETE: {profile['action']} {profile['symbol']} @ {profile['entry']} | SL: {profile['sl']} TP: {profile['tp']}")
            self.execute_signal(profile)
            del self.memory[sender_id]
        
        self.save_state()

    def execute_signal(self, signal):
        if not self.config.get("auto_execute", False):
            logger.info("Signal parsed but 'auto_execute' is False. Skipping MT5 order.")
            return

        from mt5_trader import place_market_order, connect_mt5
        if not self.mt5_cfg:
            logger.error("MT5 Config missing. Cannot execute.")
            return

        connect_mt5(self.mt5_cfg)
        
        lot = self.config.get("risk_per_trade", 0.01)
        # We use execute_trade which has the Smart Execution logic
        from mt5_trader import execute_trade, MT5Config
        
        res = execute_trade(
            config=self.mt5_cfg,
            direction="LONG" if signal["action"] == "BUY" else "SHORT",
            entry_price=signal["entry"] or 0,
            sl_price=signal["sl"] or 0,
            tp_price=signal["tp"] or 0,
            lot_size=lot,
            comment="Sacred Soul Signal"
        )
        
        if res.get("success"):
            logger.info(f"✅ Trade Executed: Ticket {res.get('ticket')}")
        else:
            logger.error(f"❌ Execution Failed: {res.get('message')}")

    async def run_all(self):
        tasks = []
        if self.config.get("discord", {}).get("token"):
            tasks.append(self.start_discord())
        
        if self.config.get("telegram", {}).get("api_id"):
            tasks.append(self.start_telegram())
        
        if tasks:
            await asyncio.gather(*tasks)
        else:
            logger.error("No signal sources configured in signal_config.json")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    bridge = SignalBridge()
    try:
        asyncio.run(bridge.run_all())
    except KeyboardInterrupt:
        pass
