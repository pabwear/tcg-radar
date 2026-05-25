import os
import logging
import datetime
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

# Config
SUPABASE = create_client(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", ""))
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Add your proxies to GitHub Secrets to stop TCGPlayer from blocking you!
PROXY_SERVER = os.environ.get("PROXY_SERVER")
PROXY_USER = os.environ.get("PROXY_USER")
PROXY_PASS = os.environ.get("PROXY_PASS")

def send_to_discord(embeds, content_header):
    if not DISCORD_URL or not embeds: return
    for i in range(0, len(embeds), 10):
        try:
            requests.post(DISCORD_URL, json={"content": content_header, "embeds": embeds[i:i+10]})
        except Exception as e:
            log.error(f"Discord Webhook Error: {e}")

def check_playwright_sites():
    results = []
    
    proxy_config = None
    if PROXY_SERVER and PROXY_USER and PROXY_PASS:
        # Format proxy string correctly for Playwright
        server_url = PROXY_SERVER if PROXY_SERVER.startswith("http") else f"http://{PROXY_SERVER}"
        proxy_config = {"server": server_url, "username": PROXY_USER, "password": PROXY_PASS}

    with sync_playwright() as p:
        # If proxy_config is None, it runs without a proxy (and likely gets blocked by TCGPlayer)
        browser = p.chromium.launch(headless=True, proxy=proxy_config)
        page = browser.new_page()
        Stealth().apply_stealth_sync(page)
        
        # TCGPlayer Check
        url = "https://www.tcgplayer.com/product/694828/yugioh-magnificent-monsters-magnificent-monsters-box"
        try:
            log.info("Checking TCGPlayer...")
            page.goto(url, timeout=20000)
            
            # Wait for price element. If it fails here, TCGPlayer is blocking the IP.
            price = page.locator(".spotlight__price").first.inner_text(timeout=8000)
            results.append({"site": "TCGPlayer", "name": "Magnificent Monsters Box", "price": price, "status": "✅ IN STOCK", "url": url, "color": 0x00FF00})
        except Exception as e:
            log.warning(f"TCGPlayer scrape failed (Likely IP Block): {e}")
        finally:
            browser.close()
            
    return results

def check_shopify_sites():
    results = []
    stores = [{"name": "Prodigy Games", "url": "https://prodigygames.com"}]
    
    for store in stores:
        try:
            log.info(f"Checking {store['name']}...")
            api_url = f"{store['url']}/search/suggest.json?q=magnificent+monsters&resources[type]=product"
            data = requests.get(api_url, timeout=10).json()
            products = data.get("resources", {}).get("results", {}).get("products", [])
            
            for p in products:
                # Safely handle missing variants
                variants = p.get("variants", [])
                price = variants[0].get("price", "0") if variants else "0"
                
                results.append({
                    "site": store['name'], 
                    "name": p['title'], 
                    "price": f"${price}", 
                    "status": "✅ IN STOCK", 
                    "url": f"{store['url']}{p['url']}", 
                    "color": 0x00FF00
                })
        except Exception as e:
            log.error(f"Shopify Error for {store['name']}: {e}")
            
    return results

def main():
    log.info("Starting Sweep...")
    
    # Run Scrapers
    all_results = check_playwright_sites() + check_shopify_sites()
    
    if not all_results:
        log.error("Both scrapers failed to find any data. Ending script early.")
        return

    # Supabase State Management
    old_state = {r['id']: r for r in SUPABASE.table("inventory_state").select("*").execute().data}
    new_state = []
    alerts = []
    
    now = datetime.datetime.utcnow()
    is_report_time = now.hour % 6 == 0 and now.minute < 30

    for L in all_results:
        item_id = f"{L['site']}::{L['url']}"
        new_state.append({"id": item_id, "price": L['price'], "status": L['status']})
        
        # Check if item is new or price changed
        if item_id not in old_state or old_state[item_id]['price'] != L['price']:
            alerts.append({"title": f"🚨 {L['site']} Update", "description": f"{L['name']}\nPrice: {L['price']}\n[Link]({L['url']})", "color": L['color']})

    # Safety check: Only save if we actually have data
    if new_state:
        SUPABASE.table("inventory_state").upsert(new_state).execute()
        log.info("Saved data to Supabase successfully.")
    
    # Discord Notifications
    if alerts: 
        send_to_discord(alerts, "🔔 **Market Alert!**")
    if is_report_time: 
        send_to_discord([{"title": r['name'], "description": f"Price: {r['price']}"} for r in all_results], "📅 **6-Hour Report**")
        
    log.info("Sweep finished.")

if __name__ == "__main__":
    main()
