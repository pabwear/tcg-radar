#!/usr/bin/env python3
"""
Magnificent Monsters Monitor - Anime Girl Edition (Monitor-chan 🌸)
Reports exact statuses with a cute, weeb-friendly aesthetic.
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
DISPLAY_NAME = "Magnificent Monsters"

# Monitor-chan's Persona Settings
BOT_NAME = "Monitor-chan 🌸"
BOT_AVATAR = "https://i.pinimg.com/originals/a4/0f/58/a40f589cda683eab5dc422d3d0f0d2c6.png" # Cute anime girl placeholder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

def evaluate_price(name, price_str):
    """Evaluates the item price with an anime-themed markup system."""
    if not price_str or price_str == "N/A" or "See Link" in price_str: 
        return ""
        
    try:
        val = float(re.sub(r'[^\d.]', '', price_str))
        name_lower = name.lower()

        if "display" in name_lower or "10x" in name_lower or "case" in name_lower:
            msrp = 350.0  
        elif "pack" in name_lower:
            msrp = 12.0   
        elif "box" in name_lower or "booster" in name_lower:
            msrp = 35.0   
        else:
            return ""

        if val <= msrp * 0.95:
            return " 📉 (KYAA! Super Cheap, Senpai! ✨)"
        elif val <= msrp * 1.15:
            return " ✅ (Fair Price~! 🌸)"
        elif val <= msrp * 2.00:
            return " ⚠️ (Yabai! High Price! 💦)"
        else:
            return " 🛑 (Baka Scalper! 😡)"
    except Exception:
        return ""

def check_playwright_sites():
    """Scrapes JavaScript-heavy sites with specialized logic per site."""
    listings = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # --- 1. TCGPlayer ---
        tcg_url = "https://www.tcgplayer.com/search/yugioh/magnificent-monsters?productLineName=yugioh&setName=magnificent-monsters&page=1&view=grid"
        page = browser.new_page()
        Stealth().apply_stealth_sync(page)
        try:
            log.info("Scanning Playwright site: TCGplayer")
            page.goto(tcg_url, timeout=PAGE_TIMEOUT)
            
            title = page.title().lower()
            if "just a moment" in title or "access denied" in title or "security" in title:
                listings.append({"site": "TCGplayer", "name": DISPLAY_NAME, "price": "N/A", "url": tcg_url, "status": "⛔ Blocked by Baka Security Guards! 😤", "color": 0x95A5A6})
            else:
                try:
                    page.wait_for_selector(".search-result, .search-result__item", timeout=10000)
                    page.wait_for_timeout(PAGE_SETTLE_MS)
                    cards = page.query_selector_all(".search-result, .search-result__item")
                    
                    if not cards:
                        listings.append({"site": "TCGplayer", "name": DISPLAY_NAME, "price": "N/A", "url": tcg_url, "status": "❌ Out of Stock (Sadge... 🥺)", "color": 0xE74C3C})
                    else:
                        for card in cards[:3]:
                            inner_text = card.inner_text()
                            name = inner_text.split('\n')[0].strip()
                            price_match = re.search(r"\$[\d,]+\.\d{2}", inner_text)
                            price = price_match.group(0) if price_match else "N/A"
                            
                            display_price = f"{price}{evaluate_price(name, price)}"
                            listings.append({"site": "TCGplayer", "name": name, "price": display_price, "url": tcg_url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x3498DB})
                except Exception:
                    listings.append({"site": "TCGplayer", "name": DISPLAY_NAME, "price": "N/A", "url": tcg_url, "status": "❌ No data found (Gomenasai... 🙇‍♀️)", "color": 0x95A5A6})
        except Exception as e:
            listings.append({"site": "TCGplayer", "name": DISPLAY_NAME, "price": "N/A", "url": tcg_url, "status": "Site Error: I tripped! 🤕", "color": 0x95A5A6})
        finally:
            page.close()

        # --- 2. GameNerdz ---
        gn_urls = [
            "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder",
            "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-1st-edition-preorder"
        ]
        
        for gn_url in gn_urls:
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                log.info(f"Scanning Playwright site: GameNerdz direct link")
                response = page.goto(gn_url, timeout=PAGE_TIMEOUT)
                
                if response.status == 404:
                    listings.append({"site": "GameNerdz", "name": DISPLAY_NAME, "price": "N/A", "url": gn_url, "status": "🙈 Secret Draft Page! (Shh... 🤫)", "color": 0xE67E22})
                else:
                    page.wait_for_selector(".productView-title", timeout=10000)
                    name = page.locator(".productView-title").inner_text()
                    price = page.locator(".price.price--withoutTax").first.inner_text()
                    
                    stock_text = ""
                    try:
                        stock_text = page.locator("[data-product-stock]").inner_text().lower()
                    except Exception:
                        stock_text = page.locator("#form-action-addToCart").inner_text().lower()

                    display_price = f"{price}{evaluate_price(name, price)}"

                    if "out of stock" in stock_text or "sold out" in stock_text:
                        listings.append({"site": "GameNerdz", "name": name, "price": display_price, "url": gn_url, "status": "❌ Out of Stock (Sadge... 🥺)", "color": 0xE74C3C})
                    else:
                        listings.append({"site": "GameNerdz", "name": name, "price": display_price, "url": gn_url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x3498DB})
            except Exception as e:
                listings.append({"site": "GameNerdz", "name": DISPLAY_NAME, "price": "N/A", "url": gn_url, "status": "❌ Page Not Found (Where did it go?! 🕵️‍♀️)", "color": 0x95A5A6})
            finally:
                page.close()

        # --- 3. Dave & Adam's ---
        da_url = "https://www.dacardworld.com/search?term=magnificent+monsters"
        page = browser.new_page()
        Stealth().apply_stealth_sync(page)
        try:
            log.info("Scanning Playwright site: Dave & Adam's")
            page.goto(da_url, timeout=PAGE_TIMEOUT)
            try:
                page.wait_for_selector("div.product-card", timeout=10000)
                page.wait_for_timeout(PAGE_SETTLE_MS)
                cards = page.query_selector_all("div.product-card")
                
                if not cards:
                    listings.append({"site": "Dave & Adam's", "name": DISPLAY_NAME, "price": "N/A", "url": da_url, "status": "❌ Out of Stock (Sadge... 🥺)", "color": 0xE74C3C})
                else:
                    for card in cards[:1]:
                        name = card.locator(".product-title").inner_text().strip()
                        price_locator = card.locator(".price")
                        price = price_locator.inner_text() if price_locator.count() > 0 else "N/A"
                        
                        display_price = f"{price}{evaluate_price(name, price)}"
                        listings.append({"site": "Dave & Adam's", "name": name, "price": display_price, "url": da_url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x3498DB})
            except Exception:
                listings.append({"site": "Dave & Adam's", "name": DISPLAY_NAME, "price": "N/A", "url": da_url, "status": "❌ No data found (Gomenasai... 🙇‍♀️)", "color": 0x95A5A6})
        except Exception:
            listings.append({"site": "Dave & Adam's", "name": DISPLAY_NAME, "price": "N/A", "url": da_url, "status": "Site Error: I tripped! 🤕", "color": 0x95A5A6})
        finally:
            page.close()
            
        browser.close()
    return listings

def check_shopify_sites():
    """Uses Shopify's internal Search API to find ALL items, regardless of age."""
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
            log.info(f"Scanning Shopify site via Search API: {store['name']}")
            base_url = store["url"].rstrip('/')
            
            search_api_url = f"{base_url}/search/suggest.json?q=magnificent+monsters&resources[type]=product"
            
            try:
                response = session.get(search_api_url, timeout=12)
                if response.status_code != 200:
                    listings.append({"site": store["name"], "name": DISPLAY_NAME, "price": "N/A", "url": base_url, "status": f"Store Error (HTTP {response.status_code}) 😵‍💫", "color": 0x95A5A6})
                    continue
                    
                data = response.json()
                products = data.get("resources", {}).get("results", {}).get("products", [])
                
                if not products:
                    listings.append({"site": store["name"], "name": DISPLAY_NAME, "price": "N/A", "url": f"{base_url}/search?q=magnificent+monsters", "status": "❌ Not in database (They haven't added it yet! 📝)", "color": 0x95A5A6})
                    continue

                for p in products:
                    title = p.get("title", "")
                    if KEYWORD in title.lower():
                        product_path = p.get("url", "").split("?")[0] 
                        exact_json_url = f"{base_url}{product_path}.json"
                        
                        try:
                            prod_resp = session.get(exact_json_url, timeout=5)
                            prod_data = prod_resp.json().get("product", {})
                            
                            variants = prod_data.get("variants", [{}])
                            first_variant = variants[0] if variants else {}
                            
                            price = f"${float(first_variant.get('price', 0)):.2f}"
                            is_available = first_variant.get("available", False)
                            product_url = f"{base_url}{product_path}"
                            
                            price_tag = evaluate_price(title, price)
                            display_price = f"{price}{price_tag}"
                            
                            if is_available:
                                listings.append({"site": store["name"], "name": title, "price": display_price, "url": product_url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x2ECC71})
                            else:
                                listings.append({"site": store["name"], "name": title, "price": display_price, "url": product_url, "status": "❌ Out of Stock (Sadge... 🥺)", "color": 0xE74C3C})
                        except Exception:
                            listings.append({"site": store["name"], "name": title, "price": "See Link", "url": f"{base_url}{product_path}", "status": "Status Unknown (My scanner broke! 🔧)", "color": 0x95A5A6})

            except Exception as e:
                listings.append({"site": store["name"], "name": "Error", "price": "N/A", "url": base_url, "status": "Failed to search store 😵‍💫", "color": 0x95A5A6})
                
    return listings

def send_radar_report(all_listings):
    """Chunks all statuses into highly detailed Discord Embeds and sends them."""
    if not DISCORD_WEBHOOK_URL:
        log.error("Missing Webhook URL!")
        return

    embeds = []
    for L in all_listings:
        embeds.append({
            "title": f"[{L['site']}] {L['name']}",
            "description": f"**Price:** {L['price']}\n**Status:** {L['status']}\n**Link:** [Click Here to View, Senpai!]({L['url']})",
            "color": L['color'],
            "footer": {
                "text": "Scouting the web just for you! (◕‿◕✿)"
            }
        })

    for i in range(0, len(embeds), 10):
        chunk = embeds[i:i+10]
        header = "✨ **Notice me, Senpai! Here is your latest Market Radar!** ✨" if i == 0 else ""
        
        payload = {
            "username": BOT_NAME,
            "avatar_url": BOT_AVATAR,
            "content": header,
            "embeds": chunk
        }
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
        except Exception as e:
            log.error(f"Discord send failed: {e}")

def main():
    log.info("Generating full anime radar report...")
    all_results = []
    
    all_results.extend(check_playwright_sites())
    all_results.extend(check_shopify_sites())
    
    send_radar_report(all_results)
    log.info("Radar report sent to Discord.")

if __name__ == "__main__":
    main()
