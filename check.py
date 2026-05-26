import os, logging, datetime, requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

SUPABASE = create_client(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", ""))
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

def send_to_discord(embeds):
    if not DISCORD_URL or not embeds: return
    for i in range(0, len(embeds), 10):
        requests.post(DISCORD_URL, json={"embeds": embeds[i:i+10]})

def check_playwright_sites():
    results = []
    targets = [
        {"site": "GameNerdz", "name": "Magnificent Monsters Display", "url": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder", "price_selector": ".price.price--withoutTax"},
        {"site": "Dave & Adams", "name": "Magnificent Monsters Booster Box", "url": "https://www.dacardworld.com/gaming/yu-gi-oh-magnificent-monsters-booster-box", "price_selector": ".price"}
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        Stealth().apply_stealth_sync(page)
        for t in targets:
            try:
                page.goto(t['url'], timeout=20000)
                price = page.locator(t['price_selector']).first.inner_text(timeout=8000)
                status = "Sold Out" if "out of stock" in page.content().lower() else "LIVE"
                results.append({"site": t['site'], "name": t['name'], "price": price.strip(), "status": status, "url": t['url']})
            except: results.append({"site": t['site'], "name": t['name'], "price": "N/A", "status": "Error", "url": t['url']})
        browser.close()
    return results

def check_shopify_sites():
    results = []
    stores = [
        {"name": "Forge and Fire", "url": "https://forgeandfiregaming.com"},
        {"name": "CoreTCG", "url": "https://www.coretcg.com"},
        {"name": "Gamers Choice", "url": "https://www.gamerschoice.com"},
        {"name": "Prodigy Games", "url": "https://prodigygames.com"},
        {"name": "Smoke & Mirrors", "url": "https://smokeandmirrorshobby.com"},
        {"name": "Ideal808", "url": "https://www.ideal808.com"}
    ]
    for store in stores:
        try:
            data = requests.get(f"{store['url']}/search/suggest.json?q=magnificent+monsters+box", timeout=10).json()
            products = data.get("resources", {}).get("results", {}).get("products", [])
            for p in products:
                title = p.get('title', '')
                if any(w in title.lower() for w in ["pack", "mat", "sleeve"]): continue
                status = "LIVE" if p.get("variants", [{}])[0].get("available") else "Sold Out"
                results.append({"site": store['name'], "name": title, "price": f"${p.get('variants', [{}])[0].get('price', '0')}", "status": status, "url": f"{store['url']}{p['url']}"})
        except: results.append({"site": store['name'], "name": "Box", "price": "N/A", "status": "Down", "url": store['url']})
    return results

def main():
    all_results = check_playwright_sites() + check_shopify_sites()
    embeds = []
    status_fields = []
    
    for L in all_results:
        emoji = "🟢" if L['status'] == "LIVE" else "🔴" if L['status'] == "Sold Out" else "⚠️"
        status_fields.append({"name": L['site'], "value": f"{emoji} {L['status']}\n{L['price']}\n[View](<{L['url']}>)", "inline": True})
        if L['status'] == "LIVE": embeds.append({"title": f"🚨 LIVE: {L['site']}", "description": f"Price: {L['price']}\n[Buy Now](<{L['url']}>)", "color": 0x00FF00})

    embeds.append({"title": "⏳ 10-Minute System Update", "color": 0x2b2d31, "fields": status_fields, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    send_to_discord(embeds)

if __name__ == "__main__":
    main()
