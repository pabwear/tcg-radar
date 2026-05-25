import os
import re
import logging
import datetime
import requests
from curl_cffi.requests import Session
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from supabase import create_client

# ... [Keep your existing Config, TARGET_URLS, and Load/Save state functions here] ...

def send_to_discord(embeds, content_header):
    for i in range(0, len(embeds), 10):
        chunk = embeds[i:i+10]
        payload = {"username": "Monitor-chan 🌸", "content": content_header, "embeds": chunk}
        requests.post(DISCORD_WEBHOOK_URL, json=payload)

def analyze_changes_and_notify(all_listings):
    old_state = load_state()
    new_state = {}
    alert_embeds = []
    report_embeds = []
    
    # 6-Hour Report Logic (UTC time)
    now = datetime.datetime.utcnow()
    is_report_time = now.hour % 6 == 0 and now.minute < 30

    for L in all_listings:
        item_id = f"{L['site']}::{L['url']}"
        is_in_stock = "✅ IN STOCK" in L['status']
        new_state[item_id] = {"status": L['status'], "price": L['price'], "in_stock": is_in_stock}
        
        # Build Full Report Data
        report_embeds.append({"title": f"[{L['site']}] {L['name']}", "description": f"Price: {L['price']}\nStatus: {L['status']}", "color": L['color']})

        # Build Alert Data (Only if change detected)
        old_data = old_state.get(item_id)
        if not old_data or old_data['in_stock'] != is_in_stock or old_data['price'] != L['price']:
            if is_in_stock:
                alert_embeds.append({"title": f"🚨 CHANGE: {L['site']}", "description": f"{L['name']}\n{L['price']}\n{L['status']}\n[Link]({L['url']})", "color": 0x00FF00})

    save_state(new_state)

    if alert_embeds:
        send_to_discord(alert_embeds, "🔔 **Market Alert!**")
    if is_report_time:
        send_to_discord(report_embeds, "📅 **6-Hour Status Report**")

# ... [Keep your main() and scrapers here] ...
