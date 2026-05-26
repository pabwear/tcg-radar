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
def send_to_discord(text_content):
    if not DISCORD_URL or not text_content: return
    try:
        # Split message if it exceeds Discord's 2000 character limit
        if len(text_content) > 1900:
            chunks = [text_content[i:i+1900] for i in range(0, len(text_content), 1900)]
            for chunk in chunks:
                requests.post(DISCORD_URL, json={"content": chunk})
        else:
            requests.post(DISCORD_URL, json={"content": text_content})
    except Exception as e:
        log.error(f"Discord Webhook Error: {e}")

# ================= Scraper 1: Playwright (Direct URLs) =================
def check_playwright_sites():
    results = []
    targets = [
        {"site": "GameNerdz", "name": "Magnificent Monsters Display", "url": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder", "price_selector": ".price.price--withoutTax"},
        {"site": "Dave & Adams", "name": "Magnificent Monsters Booster Box", "url": "https://www.dacardworld.com/gaming/yu-gi-oh-magnificent-monsters-booster-box", "price_selector": ".price"}
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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
        log.error("Scrapers returned no data.")
        return

    # Fetch Old State to track explicit changes
    old_state = {r['id']: r for r in SUPABASE.table("inventory_state").select("*").execute().data}
    new_state = []
    
    # Header for the 10-minute block update
    message_lines = ["⏳ **10-MINUTE SYSTEM UPDATE**", "```"]
    instant_alerts = []

    for L in all_results:
        item_id = f"{L['site']}::{L['url']}"
        new_state.append({"id": item_id, "price": L['price'], "status": L['status']})
        
        old_data = old_state.get(item_id)
        has_changed = not old_data or old_data['status'] != L['status'] or old_data['price'] != L['price']
        
        # Build the exact line structure requested
        if has_changed:
            line = f"{L['site']} | {L['name']} ({L['status']}) | {L['price']} | {L['url']}"
            # If it transitions specifically into a purchase window, prepare an instant notification header
            if L['status'] == "LIVE":
                instant_alerts.append(f"🚨 **PRE-ORDER LIVE AT {L['site'].upper()}** 🚨\nLink: {L['url']}")
        else:
            line = f"{L['site']} | no update | {L['url']}"
            
        message_lines.append(line)

    message_lines.append("```")
    final_report = "\n".join(message_lines)

    # Save to Supabase
    if new_state:
        SUPABASE.table("inventory_state").upsert(new_state).execute()

    # If any store instantly went live, put those tags at the very top of the delivery box
    if instant_alerts:
        alert_header = "\n".join(instant_alerts)
        final_report = f"{alert_header}\n\n{final_report}"

    # Broadcast to Discord
    send_to_discord(final_report)
    log.info("Sweep execution complete.")

if __name__ == "__main__":
    main()
