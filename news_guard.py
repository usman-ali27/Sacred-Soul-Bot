import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging

logger = logging.getLogger("news_guard")
NEWS_FILE = Path(__file__).parent / "news_events.json"

def is_trading_blocked_by_news(buffer_minutes=30):
    """
    Returns (is_blocked, reason)
    Checks if a high-impact news event is within the buffer window.
    """
    if not NEWS_FILE.exists():
        return False, "No news data"

    try:
        with open(NEWS_FILE, "r") as f:
            events = json.load(f)
        
        now = datetime.now() # We assume local time matches FF XML for now
        
        for event in events:
            # Parse the time string: e.g. "04-22-2026 8:30am"
            try:
                # Note: ForexFactory XML times are often in EST or the timezone of the server.
                # In a production bot, we would normalize everything to UTC.
                # For this implementation, we compare against local system time.
                event_time = datetime.strptime(event["time_str"], "%m-%d-%Y %I:%M%p")
                
                time_until = (event_time - now).total_seconds() / 60.0
                
                # If news is within 30 mins OR happened in the last 15 mins (volatility tail)
                if -15 <= time_until <= buffer_minutes:
                    return True, f"High Impact News: {event['title']} at {event['time_str']}"
                    
            except Exception:
                continue
                
        return False, "Buffer Clear"
    except Exception as e:
        logger.error(f"Error checking news guard: {e}")
        return False, "Error checking news"

if __name__ == "__main__":
    blocked, reason = is_trading_blocked_by_news()
    print(f"Blocked: {blocked} | Reason: {reason}")
