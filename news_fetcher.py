import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("news_fetcher")

NEWS_FILE = Path(__file__).parent / "news_events.json"

def fetch_economic_calendar():
    """
    Fetches the ForexFactory XML calendar for the current week.
    """
    # Use the NFS endpoint which is often more permissive
    url = "https://nfs.forexfactory.com/ff_calendar_thisweek.xml"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/xml,application/xml,application/xhtml+xml"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"Failed to fetch news calendar: {e}")
        return None

def parse_calendar(xml_data):
    """
    Parses the XML data and returns a list of High Impact USD events.
    """
    if not xml_data:
        return []
    
    events = []
    try:
        root = ET.fromstring(xml_data)
        for event in root.findall("event"):
            title = event.find("title").text
            country = event.find("country").text
            date = event.find("date").text # e.g. 04-22-2026
            time = event.find("time").text # e.g. 8:30am
            impact = event.find("impact").text # High, Medium, Low
            
            if country == "USD" and impact == "High":
                # Combine date and time
                # Note: FF XML time is usually EST/EDT. We need to handle timezones properly in production.
                # For now, we store as a string for the UI.
                events.append({
                    "title": title,
                    "impact": impact,
                    "country": country,
                    "time_str": f"{date} {time}",
                    "timestamp": None # Will calculate in logic
                })
        return events
    except Exception as e:
        logger.error(f"Error parsing news XML: {e}")
        return []

def update_news_data():
    """Main entry point to refresh news data."""
    logger.info("Refreshing economic calendar...")
    xml = fetch_economic_calendar()
    events = parse_calendar(xml)
    
    # Save to file
    with open(NEWS_FILE, "w") as f:
        json.dump(events, f, indent=2)
    
    logger.info(f"Saved {len(events)} high-impact USD events.")
    return events

if __name__ == "__main__":
    update_news_data()
