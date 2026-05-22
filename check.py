#!/usr/bin/env python3
"""
Magnificent Monsters Monitor - Radar Dashboard Edition
Reports ALL inventory, Out of Stock statuses, and site errors every run.
"""

import os
import re
import logging
import requests
from curl_cffi.requests import Session
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ====================== CONFIG ======================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
PAGE_TIMEOUT = 25000
PAGE_SETTLE_MS = 3000
KEYWORD = "magnificent monsters"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

def check_playwright_sites():
    """Scrapes JavaScript-heavy sites for all current listings."""
    listings = []
    sites = [
        {"name": "TCGplayer", "url": "https://www.tcgplayer.com/search/yugioh/magnificent-monsters?productLineName=yugioh&setName=magnificent-monsters&page=1&view=grid", "sel": ".search-result"},
        {"name": "GameNerdz", "url": "https://www.gamenerdz.com/search.php?search_query=magnificent+monsters", "sel": "article.card"},
        {"name": "Dave & Adam's", "url": "https://www.dacardworld.com/search?term=magnificent+monsters", "sel": "div.product-card"}
    ]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for s in sites:
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                log.info(f"Scanning Playwright site: {s['name']}")
                page.goto(s["url"], timeout=PAGE_TIMEOUT)
                
                try:
                    page.wait_for_selector(s["sel"], timeout=10000)
                    page.wait_for_timeout(PAGE_SETTLE_MS)
                    cards = page.query_selector_all(s["sel"])
                    
                    if not cards:
                        listings.append({"site": s["name"], "name": "No active listings", "price": "-", "url": s["url"], "status": "Out of Stock / Unlisted", "color": 0xE74C3C})
                    else:
                        for card in cards[:5]:
                            inner_text = card.inner_text()
                            name = inner_text.split('\n')[0].strip()
                            price_match = re.search(r"\$[\d,]+\.\d{2}", inner_text)
                            price = price_match.group(0) if price_match else "N/A"
                            listings.append({"site": s["name"], "name": name, "price": price, "url": s["url"], "status": "Available (See Price)", "color": 0x3498DB})
                except Exception:
                    listings.append({"site": s["name"], "name": "Standby", "price": "-", "url": s["url"], "status": "No results found on page", "color": 0x95A5A6})
            except Exception as e:
                listings.append({"site": s["name"], "name": "Error", "price": "-", "url": s["url"], "status": f"Connection Error: {str(e)[:20]}", "color": 0x95A5A6})
            finally:
                page.close()
        browser.close()
    return listings

def check_shopify_sites():
    """Scrapes Shopify backends for exact stock status."""
    listings = []
    shopify_stores = [
        {"name": "Prodigy Games", "url": "https://prodigygames.com"},
        {"name": "Gamers Choice", "url": "https://www.gamerschoice.com"},
        {"name": "CoreTCG", "url": "https://www.coretcg.com"}
    ]
    
    with Session() as session:
        session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        })

        for store in shopify_stores:
            log.info(f"Scanning Shopify site: {store['name']}")
            base_url = store["url"]
            json_url = f"{base_url}/products.json?limit=20"
            
            try:
                response = session.get(json_url, timeout=12)
                if response.status_code != 200:
                    listings.append({"site": store["name"], "name": "Error", "price": "-", "url": base_url, "status": f"HTTP {response.status_code}", "color": 0x95A5A6})
                    continue
                    
                data = response.json()
                found_item = False
                
                for product in data.get("products", []):
                    title = product.get("title", "")
                    if KEYWORD in title.lower():
                        found_item = True
                        variants = product.get("variants", [{}])
                        first_variant = variants[0]
                        price = f"${float(first_variant.get('price', 0)):.2f}"
                        is_available = first_variant.get("available", False)
                        product_url = f"{base_url}/products/{product.get('handle', '')}"
                        
                        if is_available:
                            listings.append({"site": store["name"], "name": title, "price": price, "url": product_url, "status": "In Stock", "color": 0x2ECC71})
                        else:
                            listings.append({"site": store["name"], "name": title, "price": price, "url": product_url, "status": "Out of Stock", "color": 0xE74C3C})
                
                if not found_item:
                    listings.append({"site": store["name"], "name": "Not Listed", "price": "-", "url": base_url, "status": "Item not found in recent uploads", "color": 0x95A5A6})
            except Exception as e:
                listings.append({"site": store["name"], "name": "Error", "price": "-", "url": base_url, "status": "Failed to parse store data", "color": 0x95A5A6})
                
    return listings

def send_radar_report(all_listings):
    """Chunks all statuses into Discord Embeds and sends them."""
    if not DISCORD_WEBHOOK_URL:
        log.error("Missing Webhook URL!")
        return

    embeds = []
    for L in all_listings:
        embeds.append({
            "title": f"[{L['site']}] {L['name']}",
            "description": f"**Price:** {L['price']}\n**Status:** {L['status']}",
            "url": L['url'],
            "color": L['color']
        })

    # Chunk into groups of 10 to bypass Discord's strict limits
    for i in range(0, len(embeds), 10):
        chunk = embeds[i:i+10]
        header = "📊 **System Radar Report**" if i == 0 else ""
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": header, "embeds": chunk})
        except Exception as e:
            log.error(f"Discord send failed: {e}")

def main():
    log.info("Generating full radar report...")
    all_results = []
    
    # 1. Scrape Playwright (TCGPlayer, etc.)
    all_results.extend(check_playwright_sites())
    
    # 2. Scrape Shopify
    all_results.extend(check_shopify_sites())
    
    # 3. Send out the complete status list
    send_radar_report(all_results)
    log.info("Radar report sent to Discord.")

if __name__ == "__main__":
    main()
