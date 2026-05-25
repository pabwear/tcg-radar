import os
import re
import logging
import datetime
import requests
from curl_cffi.requests import Session
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from supabase import create_client, Client

# --- Configuration ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
SUPABASE = create_client(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", ""))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

def send_to_discord(embeds, header):
    if not DISCORD_WEBHOOK_URL: return
    for i in range(0, len(embeds), 10):
        requests.post(DISCORD_WEBHOOK_URL, json={"content": header, "embeds": embeds[i:i+10]})

def analyze_and_notify(all_listings):
    # Load previous state from Supabase
    old_state = {r['id']: r for r in SUPABASE.table("inventory_state").select("*").execute().data}
    new_state = {}
    alert_embeds = []
    report_embeds = []
    
    # 6-Hour Report Check (UTC Time: 00:00, 06:00, 12:00, 18:00)
    now = datetime.datetime.utcnow()
    is_report_time = now.hour % 6 == 0 and now.minute < 30

    for L in all_listings:
        item_id = f"{L['site']}::{L['url']}"
        in_stock = "✅ IN STOCK" in L['status']
        new_state[item_id] = {"id": item_id, "price": L['price'], "status": L['status'], "in_stock": in_stock}
        
        # Add to full report list
        report_embeds.append({"title": f"[{L['site']}] {L['name']}", "description": f"Price: {L['price']}\nStatus: {L['status']}\n[Link]({L['url']})", "color": L['color']})

        # Check for changes (Alerts)
        old = old_state.get(item_id)
        if not old or old['in_stock'] != in_stock or old['price'] != L['price']:
            if in_stock:
                alert_embeds.append({"title": f"🚨 CHANGE: {L['site']}", "description": f"{L['name']}\nPrice: {L['price']}\nStatus: {L['status']}\n[Link]({L['url']})", "color": 0x00FF00})

    # Save new state
    SUPABASE.table("inventory_state").upsert(list(new_state.values())).execute()

    # Dispatch messages
    if alert_embeds: send_to_discord(alert_embeds, "🔔 **Market Alert! Change Detected.**")
    if is_report_time: send_to_discord(report_embeds, "📅 **6-Hour Status Report**")

# ... [Keep your existing check_playwright_sites and check_shopify_sites functions here] ...
