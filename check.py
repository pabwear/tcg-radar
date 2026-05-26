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

# Load Proxy Secrets (if used)
PROXY_SERVER = os.environ.get("PROXY_SERVER")
PROXY_USER = os.environ.get("PROXY_USER")
PROXY_PASS = os.environ.get("PROXY_PASS")

# ================= Discord Helper =================
def send_to_discord(embeds):
    if not DISCORD_URL or not embeds: return
    try:
        # Discord limits us to 10 embeds per message
        for i in range(0, len(embeds), 10):
            response = requests.post(DISCORD_URL, json={"embeds": embeds[i:i+10]})
            if response.status_code >= 400:
                log.error(f"Discord API Error: {response.text}")
    except Exception as e:
        log.error(f"Discord Webhook Error: {e}")

# ================= Scraper 1: Playwright (Direct URLs) =================
def check_playwright_sites():
    results = []
    proxy_config = None
    
    if PROXY_SERVER and PROXY_USER and PROXY_PASS:
        server_url = PROXY_SERVER if PROXY_SERVER.startswith("http") else f"http://{PROXY_SERVER}"
        proxy_config = {"server": server_url, "username": PROXY_USER, "password": PROXY_PASS}

    targets = [
        {"site": "GameNerdz", "name": "Magnificent Monsters Display", "url": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder", "price_selector": ".price.price--withoutTax"},
        {"site": "Dave & Adams", "name": "Magnificent Monsters Booster Box", "url": "https://www.dacardworld.com/gaming/yu-gi-oh-magnificent-monsters-booster-box", "price_selector": ".price"}
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy=proxy_config)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        
        for t in targets:
            try:
                log.info(f"Checking {t['site']}...")
                page.goto(t['url'], timeout=20000)
                price = page.locator(t['price_selector']).first.inner_text(timeout=8000)
                
                page_text = page.content().lower()
                is_oos = "out of stock" in page_text or "sold out" in page_text or "currently unavailable" in page_text
                status = "Sold Out" if is_oos else "LIVE"
                
                results.append({"site": t['site'], "name": t['name'], "price": price.strip(), "status": status, "url": t['url']})
            except Exception as e:
                log.warning(f"{t['site']} scrape failed: {e}")
                results.append({"site": t['site'], "name": t['name'], "price": "N/A", "status": "Error/Blocked", "url": t['url']})
                
        browser.close()
    return results

# ================= Scraper 2: Shopify APIs =================
def check_shopify_sites():
    results = []
    
    req_proxies = None
    if PROXY_SERVER and PROXY_USER and PROXY_PASS:
        clean_server = PROXY_SERVER.replace('http://', '').replace('https://', '')
        req_proxies = {
            "http": f"http://{PROXY_USER}:{PROXY_PASS}@{clean_server}",
            "https": f"http://{PROXY_USER}:{PROXY_PASS}@{clean_server}"
        }

    stores = [
        {"name": "Forge and Fire", "url": "https://forgeandfiregaming.com"},
        {"name": "CoreTCG", "url": "https://www.coretcg.com"},
        {"name": "Gamers Choice", "url": "https://www.gamerschoice.com"},
        {"name": "Prodigy Games", "url": "https://prodigygames.com"},
        {"name": "Smoke & Mirrors", "url": "https://smokeandmirrorshobby.com"},
        {"name": "Ideal808", "url": "https://www.ideal808.com"},
        {"name": "YGO Black Market", "url": "https://ygoblackmarket.com"}
    ]
    
    for store in stores:
        try:
            log.info(f"Checking {store['name']}...")
            api_url = f"{store['url']}/search/suggest.json?q=magnificent+monsters+box&resources[type]=product"
            data = requests.get(api_url, timeout=10, proxies=req_proxies).json()
            products = data.get("resources", {}).get("results", {}).get("products", [])
            
            if not products:
                results.append({"site": store['name'], "name": "Magnificent Monsters Box", "price": "N/A", "status": "No Listing", "url": store['url']})
                continue

            for p in products:
                title = p.get('title', '')
                if any(bad_word in title.lower() for bad_word in ["pack", "mat", "sleeve", "token", "promo", "single"]):
                    continue
                    
                variants = p.get("variants", [])
                price = variants[0].get("price", "0") if variants else "0"
                is_available = variants[0].get("available", False) if variants else False
                status = "LIVE" if is_available else "Sold Out"
                
                results.append({"site": store['name'], "name": title, "price": f"${price}", "status": status, "url": f"{store['url']}{p['url']}"})
        except Exception as e:
            log.error(f"Shopify Error for {store['name']}: {e}")
            results.append({"site": store['name'], "name": "Magnificent Monsters Box", "price": "N/A", "status": "Down/Error", "url": store['url']})
            
    return results

# ================= Main Logic =================
def main():
    log.info("Starting Magnificent Monsters 10-Minute Sweep...")
    all_results = check_playwright_sites() + check_shopify_sites()
    
    if not all_results:
        log.error("Scrapers returned no data. Ending run.")
        return

    # Fetch Old State to track explicit changes
    old_state = {r['id']: r for r in SUPABASE.table("inventory_state").select("*").execute().data}
    new_state = []
    
    embeds = []
    status_fields = []

    for L in all_results:
        item_id = f"{L['site']}::{L['url']}"
        new_state.append({"id": item_id, "price": L['price'], "status": L['status']})
        
        old_data = old_state.get(item_id)
        has_changed = not old_data or old_data['status'] != L['status'] or old_data['price'] != L['price']
        
        # 1. Check for Emergency LIVE Alerts
        if has_changed and L['status'] == "LIVE":
            embeds.append({
                "title": f"🚨 PRE-ORDER LIVE: {L['site'].upper()} 🚨",
                "description": f"**{L['name']}**\n\n**Price:** {L['price']}\n\n👉 **[CLICK HERE TO BUY NOW]({L['url']})**",
                "color": 0x00FF00 # Bright Green
            })
            
        # 2. Build the Dashboard Grid
        emoji = "🟢" if L['status'] == "LIVE" else "🔴" if L['status'] == "Sold Out" else "⚪" if L['status'] == "No Listing" else "⚠️"
        
        status_fields.append({
            "name": L['site'],
            "value": f"{emoji} {L['status']}\n{L['price']}\n[Link](<{L['url']}>)",
            "inline": True # This forces Discord to arrange them in a neat grid!
        })

    # 3. Create the Main 10-Minute Dashboard Embed
    embeds.append({
        "title": "⏳ 10-Minute System Update",
        "description": "Current retail status for Magnificent Monsters:",
        "color": 0x2b2d31, # This is Discord's exact background color, making the panel look incredibly sleek
        "fields": status_fields,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })

    # Save to Supabase
    if new_state:
        SUPABASE.table("inventory_state").upsert(new_state).execute()
        log.info(f"Saved {len(new_state)} items to database.")

    # Broadcast to Discord
    send_to_discord(embeds)
    log.info("Sweep execution complete.")

if __name__ == "__main__":
    main()
