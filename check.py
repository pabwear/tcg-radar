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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

# Config
SUPABASE = create_client(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", ""))
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

def send_to_discord(embeds, content_header):
    if not DISCORD_URL or not embeds: return
    for i in range(0, len(embeds), 10):
        requests.post(DISCORD_URL, json={"content": content_header, "embeds": embeds[i:i+10]})

def check_playwright_sites():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        Stealth().apply_stealth_sync(page)
        
        # Example TCGPlayer Check
        url = "https://www.tcgplayer.com/product/694828/yugioh-magnificent-monsters-magnificent-monsters-box"
        try:
            page.goto(url, timeout=20000)
            price = page.locator(".spotlight__price").first.inner_text(timeout=5000)
            results.append({"site": "TCGPlayer", "name": "Magnificent Monsters Box", "price": price, "status": "✅ IN STOCK", "url": url, "color": 0x00FF00})
        except Exception as e:
            log.warning(f"TCGPlayer scrape failed: {e}")
        browser.close()
    return results

def check_shopify_sites():
    results = []
    stores = [{"name": "Prodigy Games", "url": "https://prodigygames.com"}]
    for store in stores:
        try:
            api_url = f"{store['url']}/search/suggest.json?q=magnificent+monsters&resources[type]=product"
            data = requests.get(api_url, timeout=10).json()
            products = data.get("resources", {}).get("results", {}).get("products", [])
            for p in products:
                price = p.get("variants", [{}])[0].get("price", "0")
                results.append({"site": store['name'], "name": p['title'], "price": f"${price}", "status": "✅ IN STOCK", "url": f"{store['url']}{p['url']}", "color": 0x00FF00})
        except Exception as e:
            log.error(f"Shopify Error: {e}")
    return results

def main():
    log.info("Starting Sweep...")
    all_results = check_playwright_sites() + check_shopify_sites()
    
    # Supabase State
    old_state = {r['id']: r for r in SUPABASE.table("inventory_state").select("*").execute().data}
    new_state = []
    alerts = []
    
    now = datetime.datetime.utcnow()
    is_report_time = now.hour % 6 == 0 and now.minute < 30

    for L in all_results:
        item_id = f"{L['site']}::{L['url']}"
        new_state.append({"id": item_id, "price": L['price'], "status": L['status']})
        
        if item_id not in old_state or old_state[item_id]['price'] != L['price']:
            alerts.append({"title": f"🚨 {L['site']} Update", "description": f"{L['name']}\nPrice: {L['price']}\n[Link]({L['url']})", "color": L['color']})

    SUPABASE.table("inventory_state").upsert(new_state).execute()
    
    if alerts: send_to_discord(alerts, "🔔 **Market Alert!**")
    if is_report_time: send_to_discord([{"title": r['name'], "description": f"Price: {r['price']}"} for r in all_results], "📅 **6-Hour Report**")

if __name__ == "__main__":
    main()
