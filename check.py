import os
import logging
import datetime
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s"
)
log = logging.getLogger(__name__)

DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

def send_to_discord(embeds):
    if not DISCORD_URL or not embeds:
        return
    for i in range(0, len(embeds), 10):
        try:
            requests.post(DISCORD_URL, json={"embeds": embeds[i:i+10]}, timeout=15)
        except Exception as e:
            log.error(f"Failed to send Discord message: {e}")

def check_playwright_sites():
    results = []
    targets = [
        {
            "site": "GameNerdz",
            "name": "Magnificent Monsters Display",
            "url": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder",
            "price_selector": ".price.price--withoutTax"
        },
        {
            "site": "Dave & Adams",
            "name": "Magnificent Monsters Booster Box",
            "url": "https://www.dacardworld.com/gaming/yu-gi-oh-magnificent-monsters-booster-box",
            "price_selector": ".price"
        }
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        Stealth().apply_stealth_sync(page)

        for t in targets:
            try:
                page.goto(t['url'], timeout=25000, wait_until="domcontentloaded")
                price_el = page.locator(t['price_selector']).first
                price = price_el.inner_text(timeout=8000).strip() if price_el.count() > 0 else "N/A"

                content = page.content().lower()
                sold_out_phrases = ["out of stock", "sold out", "currently unavailable", "no longer available"]
                is_sold_out = any(phrase in content for phrase in sold_out_phrases)

                status = "Sold Out" if is_sold_out else "LIVE"
                results.append({
                    "site": t['site'],
                    "name": t['name'],
                    "price": price,
                    "status": status,
                    "url": t['url']
                })
                log.info(f"{t['site']}: {status} - {price}")
            except Exception as e:
                log.error(f"Error checking {t['site']}: {e}")
                results.append({
                    "site": t['site'],
                    "name": t['name'],
                    "price": "N/A",
                    "status": "Error",
                    "url": t['url']
                })
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
        {"name": "Ideal808", "url": "https://www.ideal808.com"},
    ]

    for store in stores:
        try:
            resp = requests.get(
                f"{store['url']}/search/suggest.json?q=magnificent+monsters+box",
                timeout=12,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            data = resp.json()
            products = data.get("resources", {}).get("results", {}).get("products", [])

            found = False
            for p in products:
                title = p.get('title', '').lower()
                if any(w in title for w in ["pack", "mat", "sleeve", "deck"]):
                    continue

                variants = p.get("variants", [{}])
                if variants:
                    available = variants[0].get("available", False)
                    price = variants[0].get("price", 0)
                    status = "LIVE" if available else "Sold Out"
                    results.append({
                        "site": store['name'],
                        "name": p.get('title', 'Magnificent Monsters'),
                        "price": f"${price}",
                        "status": status,
                        "url": f"{store['url']}{p.get('url', '')}"
                    })
                    found = True
                    break

            if not found:
                results.append({
                    "site": store['name'],
                    "name": "Box",
                    "price": "N/A",
                    "status": "No Match",
                    "url": store['url']
                })
        except Exception as e:
            log.error(f"Error checking {store['name']}: {e}")
            results.append({
                "site": store['name'],
                "name": "Box",
                "price": "N/A",
                "status": "Down",
                "url": store['url']
            })
    return results

def main():
    log.info("Starting TCG Radar check...")

    all_results = check_playwright_sites() + check_shopify_sites()

    embeds = []
    status_fields = []
    live_count = 0

    for item in all_results:
        if item['status'] == "LIVE":
            emoji = "🟢"
            live_count += 1
            embeds.append({
                "title": f"🚨 LIVE: {item['site']}",
                "description": f"**{item['name']}**\nPrice: {item['price']}\n[Buy Now](<{item['url']}>)",
                "color": 0x00FF00,
                "url": item['url']
            })
        elif item['status'] == "Sold Out":
            emoji = "🔴"
        elif item['status'] == "Error":
            emoji = "⚠️"
        else:
            emoji = "⚪"

        status_fields.append({
            "name": item['site'],
            "value": f"{emoji} **{item['status']}**\n{item['price']}\n[View](<{item['url']}>)",
            "inline": True
        })

    # Summary embed
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary = {
        "title": "⏳ Magnificent Monsters Radar Update",
        "description": f"Checked {len(all_results)} stores • {live_count} LIVE\nLast checked: {now}",
        "color": 0x2b2d31,
        "fields": status_fields,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    embeds.append(summary)

    send_to_discord(embeds)
    log.info(f"Check complete. {live_count} LIVE items found.")

if __name__ == "__main__":
    main()
