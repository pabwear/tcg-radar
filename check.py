import os
import re
import logging
import datetime
import requests
import sys
from curl_cffi.requests import Session
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from supabase import create_client

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

# Configuration
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

TARGET_URLS = {
    "TCGplayer_Box": "https://www.tcgplayer.com/product/694828/yugioh-magnificent-monsters-magnificent-monsters-box",
    "GameNerdz_Display": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder",
    "Dave_And_Adams": "https://www.dacardworld.com/gaming/yu-gi-oh-magnificent-monsters-booster-box"
}

def load_state():
    if not SUPABASE: return {}
    try:
        response = SUPABASE.table("inventory_state").select("*").execute()
        return {row['id']: row for row in response.data}
    except Exception as e:
        log.error(f"Failed to load state: {e}")
        return {}

def send_to_discord(embeds, header):
    if not DISCORD_WEBHOOK_URL: return
    for i in range(0, len(embeds), 10):
        requests.post(DISCORD_WEBHOOK_URL, json={"content": header, "embeds": embeds[i:i+10]})

def check_playwright_sites():
    listings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0")
        for name, url in TARGET_URLS.items():
            page = context.new_page()
            try:
                page.goto(url, timeout=20000)
                # Simplified check logic for demo
                is_in_stock = "Add to Cart" in page.content() or "Pre-order" in page.content()
                status = "✅ IN STOCK" if is_in_stock else "❌ Out of Stock"
                listings.append({"site": name, "name": name, "status": status, "url": url, "color": 0x00FF00 if is_in_stock else 0xFF0000, "price": "Check Site"})
            except Exception as e:
                log.error(f"Error checking {name}: {e}")
            page.close()
        browser.close()
    return listings

def check_shopify_sites():
    # Only adding one for testing to ensure it runs
    listings = []
    store = {"name": "Prodigy Games", "url": "https://prodigygames.com"}
    try:
        api_url = f"{store['url']}/search/suggest.json?q=magnificent+monsters&resources[type]=product"
        resp = requests.get(api_url, timeout=10).json()
        # Add logic to parse products...
    except Exception as e:
        log.error(f"Shopify Error: {e}")
    return listings

def main():
    print("DEBUG: Starting Sweep...")
    all_results = check_playwright_sites() + check_shopify_sites()
    
    old_state = load_state()
    new_state = {}
    alert_embeds = []
    report_embeds = []
    
    now = datetime.datetime.utcnow()
    is_report_time = now.hour % 6 == 0 and now.minute < 30

    for L in all_results:
        item_id = f"{L['site']}::{L['url']}"
        in_stock = "✅" in L['status']
        new_state[item_id] = {"id": item_id, "price": L['price'], "status": L['status'], "in_stock": in_stock}
        
        report_embeds.append({"title": L['site'], "description": f"{L['name']}\n{L['status']}", "color": L['color']})
        
        old = old_state.get(item_id)
        if not old or old['in_stock'] != in_stock:
            if in_stock:
                alert_embeds.append({"title": "🚨 STOCK UPDATE", "description": f"{L['site']}: {L['name']} is available!", "color": 0x00FF00})

    if SUPABASE: SUPABASE.table("inventory_state").upsert(list(new_state.values())).execute()
    
    if alert_embeds: send_to_discord(alert_embeds, "🔔 **Alert**")
    if is_report_time: send_to_discord(report_embeds, "📅 **6-Hour Report**")

if __name__ == "__main__":
    main()
