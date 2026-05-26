import os
import logging
import datetime
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from supabase import create_client

# ================= Configuration & Setup =================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

SUPABASE = create_client(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", ""))
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# ================= Discord Helper =================
def send_to_discord(embeds, content_header):
    if not DISCORD_URL or not embeds: return
    for i in range(0, len(embeds), 10):
        try:
            requests.post(DISCORD_URL, json={"content": content_header, "embeds": embeds[i:i+10]})
        except Exception as e:
            log.error(f"Discord Webhook Error: {e}")

# ================= Scraper 1: Playwright (Direct URLs) =================
def check_playwright_sites():
    results = []
    
    # Define Direct Targets (Excluding TCGPlayer)
    targets = [
        {"site": "GameNerdz", "name": "Magnificent Monsters Display", "url": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder", "price_selector": ".price.price--withoutTax"},
        {"site": "Dave & Adams", "name": "Magnificent Monsters Booster Box", "url": "https://www.dacardworld.com/gaming/yu-gi-oh-magnificent-monsters-booster-box", "price_selector": ".price"}
    ]

    with sync_playwright() as p:
        # Running without proxy since TCGPlayer is removed
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        
        for t in targets:
            try:
                log.info(f"Checking {t['site']}...")
                page.goto(t['url'], timeout=20000)
                
                # If it can find the price, the page loaded successfully
                price = page.locator(t['price_selector']).first.inner_text(timeout=8000)
                
                # Check for Out of Stock indicators
                page_text = page.content().lower()
                is_oos = "out of stock" in page_text or "sold out" in page_text or "currently unavailable" in page_text
                
                status = "❌ Out of Stock" if is_oos else "✅ IN STOCK"
                color = 0xFF0000 if is_oos else 0x00FF00
                
                results.append({"site": t['site'], "name": t['name'], "price": price, "status": status, "url": t['url'], "color": color})
                
            except Exception as e:
                log.warning(f"{t['site']} scrape failed: {e}")
                
        browser.close()
            
    return results

# ================= Scraper 2: Shopify APIs =================
def check_shopify_sites():
    results = []
    stores = [
        {"name": "Forge and Fire", "url": "https://forgeandfiregaming.com"},
        {"name": "CoreTCG", "url": "https://www.coretcg.com"},
        {"name": "Gamers Choice", "url": "https://www.gamerschoice.com"},
        {"name": "Prodigy Games", "url": "https://prodigygames.com"},
        {"name": "Smoke & Mirrors Hobby", "url": "https://smokeandmirrorshobby.com"},
        {"name": "Ideal808", "url": "https://www.ideal808.com"},
        {"name": "YGO Black Market", "url": "https://ygoblackmarket.com"}
    ]
    
    for store in stores:
        try:
            log.info(f"Checking {store['name']}...")
            api_url = f"{store['url']}/search/suggest.json?q=magnificent+monsters+box&resources[type]=product"
            data = requests.get(api_url, timeout=10).json()
            products = data.get("resources", {}).get("results", {}).get("products", [])
            
            for p in products:
                title = p.get('title', '')
                
                # Filter out accessories to strictly target the boxes/cases
                if any(bad_word in title.lower() for bad_word in ["pack", "mat", "sleeve", "token", "promo", "single"]):
                    continue
                    
                variants = p.get("variants", [])
                price = variants[0].get("price", "0") if variants else "0"
                is_available = variants[0].get("available", False) if variants else False
                
                status = "✅ IN STOCK" if is_available else "❌ Out of Stock"
                color = 0x00FF00 if is_available else 0xFF0000
                
                results.append({
                    "site": store['name'], 
                    "name": title, 
                    "price": f"${price}", 
                    "status": status, 
                    "url": f"{store['url']}{p['url']}", 
                    "color": color
                })
        except Exception as e:
            # This try/except ensures that if one site goes down (like YGO Black Market), the rest still scan perfectly.
            log.error(f"Shopify Error for {store['name']}: {e}")
            
    return results

# ================= Main Logic =================
def main():
    log.info("Starting Magnificent Monsters Sweep...")
    
    all_results = check_playwright_sites() + check_shopify_sites()
    
    if not all_results:
        log.error("Scrapers returned no data. Ending run.")
        return

    # Fetch Old State
    old_state = {r['id']: r for r in SUPABASE.table("inventory_state").select("*").execute().data}
    new_state = []
    alerts = []
    
    # 6-Hour Report Check
    now = datetime.datetime.now(datetime.timezone.utc)
    is_report_time = now.hour % 6 == 0 and now.minute < 30

    for L in all_results:
        item_id = f"{L['site']}::{L['url']}"
        new_state.append({"id": item_id, "price": L['price'], "status": L['status']})
        
        # Determine if we should Alert
        is_in_stock = "✅ IN STOCK" in L['status']
        old_data = old_state.get(item_id)
        
        # Trigger an alert if the item is newly found, changed status, or changed price
        if not old_data or old_data['status'] != L['status'] or old_data['price'] != L['price']:
            # We strictly only want an alert to ping Discord if the item is available to purchase
            if is_in_stock:
                alerts.append({
                    "title": f"🚨 {L['site']} RESTOCK / PRE-ORDER LIVE", 
                    "description": f"**{L['name']}**\nPrice: {L['price']}\n[Click here to Buy!]({L['url']})", 
                    "color": L['color']
                })

    # Save New State
    if new_state:
        SUPABASE.table("inventory_state").upsert(new_state).execute()
        log.info(f"Saved {len(new_state)} items to database.")
    
    # Send Discord Messages
    if alerts: 
        send_to_discord(alerts, "🚨 **MAGNIFICENT MONSTERS ALERT** 🚨")
    if is_report_time: 
        send_to_discord([{"title": r['name'], "description": f"{r['site']} | {r['price']} | {r['status']}"} for r in all_results], "📅 **6-Hour Status Report**")
        
    log.info("Sweep finished.")

if __name__ == "__main__":
    main()
