#!/usr/bin/env python3
"""
Magnificent Monsters Monitor - Anime Girl Edition (Monitor-chan 🌸)
DIRECT TARGETING EDITION: Sept 4th Release & Grandmaster Rares Sniper
Powered by Supabase Memory
"""

import os
import re
import logging
import requests
from curl_cffi.requests import Session
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from supabase import create_client, Client

# ====================== CONFIG & SECRETS ======================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
PAGE_TIMEOUT = 30000

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# Monitor-chan's Persona
BOT_NAME = "Monitor-chan 🌸 (Sniper Mode)"
BOT_AVATAR = "https://i.pinimg.com/originals/a4/0f/58/a40f589cda683eab5dc422d3d0f0d2c6.png"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

# ====================== 🎯 DIRECT TARGET URLS ======================
# UPDATE THESE LINKS! Monitor-chan will ONLY check these exact pages.
# If a site doesn't have a listing up yet, leave it as "XXXXX" and she will ignore it.
TARGET_URLS = {
    # PLAYWRIGHT (HTML) SITES
    "TCGplayer": "https://www.tcgplayer.com/product/XXXXX/yugioh-magnificent-monsters-booster-box",
    "GameNerdz_Display": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder",
    "GameNerdz_Box": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-1st-edition-preorder",
    "Dave_And_Adams": "https://www.dacardworld.com/gaming/yu-gi-oh-magnificent-monsters-booster-box",
    
    # SHOPIFY (JSON API) SITES
    "Prodigy_Games": "https://prodigygames.com/products/yu-gi-oh-magnificent-monsters-display-10x-boxes-preorder",
    "Gamers_Choice": "https://www.gamerschoice.com/products/XXXXX-magnificent-monsters-box",
    "CoreTCG": "https://www.coretcg.com/products/XXXXX-magnificent-monsters-box"
}

# ====================== STATE MANAGEMENT ======================
def load_state():
    """Loads the previous inventory state directly from Supabase."""
    if not supabase:
        log.warning("Supabase not configured. Running without memory!")
        return {}
    try:
        response = supabase.table("inventory_state").select("*").execute()
        state = {}
        for row in response.data:
            state[row['id']] = {
                "price": row['price'],
                "status": row['status'],
                "in_stock": row['in_stock']
            }
        return state
    except Exception as e:
        log.error(f"Failed to load state from Supabase: {e}")
        return {}

def save_state(state):
    """Saves the current inventory state to Supabase using an upsert."""
    if not supabase: return
    try:
        records = [{"id": k, "price": v['price'], "status": v['status'], "in_stock": v['in_stock']} for k, v in state.items()]
        if records:
            supabase.table("inventory_state").upsert(records).execute()
    except Exception as e:
        log.error(f"Failed to save state to Supabase: {e}")

# ====================== LOGIC & APPRAISAL ======================
def evaluate_price(name, price_str):
    """Evaluates the MSRP for the Sept 4th Magnificent Monsters release."""
    if not price_str or price_str == "N/A": return ""
    try:
        val = float(re.sub(r'[^\d.]', '', price_str))
        name_lower = name.lower()

        # MSRP: $34.99 per Box. Displays are usually 10 boxes ($349.90).
        if "display" in name_lower or "10x" in name_lower or "case" in name_lower:
            msrp = 350.0  
        elif "box" in name_lower or "booster" in name_lower:
            msrp = 35.0   
        else:
            return ""

        if val <= msrp * 0.95: return " 📉 (KYAA! Super Cheap, Senpai! ✨)"
        elif val <= msrp * 1.15: return " ✅ (Fair Price~! 🌸)"
        elif val <= msrp * 2.00: return " ⚠️ (Yabai! High Price! 💦)"
        else: return " 🛑 (Baka Scalper! 😡)"
    except Exception:
        return ""

# ====================== DIRECT LINK SCRAPERS ======================
def check_playwright_sites():
    """Navigates directly to product pages avoiding search results."""
    listings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # --- 1. TCGPlayer Direct ---
        url = TARGET_URLS["TCGplayer"]
        if url and "XXXXX" not in url:
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                log.info("Direct hitting TCGPlayer...")
                page.goto(url, timeout=PAGE_TIMEOUT)
                title = page.title().lower()
                
                if "just a moment" in title or "security" in title:
                    listings.append({"site": "TCGplayer", "name": "Magnificent Monsters Box", "price": "N/A", "url": url, "status": "⛔ Blocked by Security Guards! 😤", "color": 0x95A5A6})
                else:
                    name_loc = page.locator(".product-details__name")
                    name = name_loc.inner_text() if name_loc.count() > 0 else "Magnificent Monsters Box"
                    price_loc = page.locator(".spotlight__price")
                    price = price_loc.inner_text() if price_loc.count() > 0 else "N/A"
                    
                    if price == "N/A":
                        listings.append({"site": "TCGplayer", "name": name, "price": "N/A", "url": url, "status": "❌ Out of Stock (Sadge... 🥺)", "color": 0xE74C3C})
                    else:
                        listings.append({"site": "TCGplayer", "name": name, "price": f"{price}{evaluate_price(name, price)}", "url": url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x3498DB})
            except Exception as e:
                log.error(f"TCGplayer Error: {e}")
            finally:
                page.close()

        # --- 2. GameNerdz Direct ---
        for gn_key in ["GameNerdz_Display", "GameNerdz_Box"]:
            url = TARGET_URLS[gn_key]
            if not url or "XXXXX" in url: continue
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                log.info(f"Direct hitting {gn_key}...")
                resp = page.goto(url, timeout=PAGE_TIMEOUT)
                if resp.status == 404:
                    listings.append({"site": "GameNerdz", "name": "Secret Listing", "price": "N/A", "url": url, "status": "🙈 Page Not Live Yet (Shh... 🤫)", "color": 0xE67E22})
                else:
                    page.wait_for_selector(".productView-title", timeout=10000)
                    name = page.locator(".productView-title").inner_text()
                    price = page.locator(".price.price--withoutTax").first.inner_text()
                    
                    try:
                        stock_text = page.locator("[data-product-stock]").inner_text().lower()
                    except Exception:
                        stock_text = page.locator("#form-action-addToCart").inner_text().lower()

                    if "out of stock" in stock_text or "sold out" in stock_text:
                        listings.append({"site": "GameNerdz", "name": name, "price": f"{price}{evaluate_price(name, price)}", "url": url, "status": "❌ Out of Stock (Sadge... 🥺)", "color": 0xE74C3C})
                    else:
                        listings.append({"site": "GameNerdz", "name": name, "price": f"{price}{evaluate_price(name, price)}", "url": url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x3498DB})
            except Exception as e:
                log.error(f"GameNerdz Error: {e}")
            finally:
                page.close()

        # --- 3. DA Card World Direct ---
        url = TARGET_URLS["Dave_And_Adams"]
        if url and "XXXXX" not in url:
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                log.info("Direct hitting Dave & Adam's...")
                page.goto(url, timeout=PAGE_TIMEOUT)
                name_loc = page.locator("h1.product-title")
                name = name_loc.inner_text() if name_loc.count() > 0 else "Magnificent Monsters Box"
                
                price_loc = page.locator(".price")
                price = price_loc.inner_text() if price_loc.count() > 0 else "N/A"
                
                btn_loc = page.locator("#add-to-cart")
                if btn_loc.count() == 0 or price == "N/A":
                    listings.append({"site": "Dave & Adam's", "name": name, "price": "N/A", "url": url, "status": "❌ Out of Stock (Sadge... 🥺)", "color": 0xE74C3C})
                else:
                    listings.append({"site": "Dave & Adam's", "name": name, "price": f"{price}{evaluate_price(name, price)}", "url": url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x3498DB})
            except Exception as e:
                log.error(f"DA Card World Error: {e}")
            finally:
                page.close()

        browser.close()
    return listings

def check_shopify_sites():
    """Hits Shopify JSON APIs directly using the exact URL slug."""
    listings = []
    sites = {
        "Prodigy Games": TARGET_URLS["Prodigy_Games"],
        "Gamers Choice": TARGET_URLS["Gamers_Choice"],
        "CoreTCG": TARGET_URLS["CoreTCG"]
    }
    
    with Session(impersonate="chrome120") as session:
        for site_name, url in sites.items():
            if not url or "XXXXX" in url: continue
            log.info(f"Direct API hitting {site_name}...")
            
            json_url = f"{url}.json"
            try:
                response = session.get(json_url, timeout=10)
                if response.status_code == 404:
                    listings.append({"site": site_name, "name": "Magnificent Monsters", "price": "N/A", "url": url, "status": "❌ Page Not Live Yet (404) 📝", "color": 0x95A5A6})
                    continue
                
                prod_data = response.json().get("product", {})
                title = prod_data.get("title", "Unknown Product")
                variants = prod_data.get("variants", [{}])
                first_variant = variants[0] if variants else {}
                
                price = f"${float(first_variant.get('price', 0)):.2f}"
                is_available = first_variant.get("available", False)
                display_price = f"{price}{evaluate_price(title, price)}"
                
                if is_available:
                    listings.append({"site": site_name, "name": title, "price": display_price, "url": url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x2ECC71})
                else:
                    listings.append({"site": site_name, "name": title, "price": display_price, "url": url, "status": "❌ Out of Stock (Sadge... 🥺)", "color": 0xE74C3C})
            except Exception as e:
                log.error(f"Shopify Error for {site_name}: {e}")
                
    return listings

def analyze_changes_and_notify(all_listings):
    """Compares current listings with Supabase state. Only alerts on restocks/price changes."""
    if not DISCORD_WEBHOOK_URL: return

    old_state = load_state()
    new_state = {}
    embeds_to_send = []
    ping_message = ""

    for L in all_listings:
        item_id = f"{L['site']}::{L['url']}"
        is_in_stock = "✅ IN STOCK" in L['status']
        
        new_state[item_id] = {"status": L['status'], "price": L['price'], "in_stock": is_in_stock}

        should_notify = False
        old_data = old_state.get(item_id)

        if not old_data:
            should_notify = True
            if is_in_stock: ping_message = "@everyone 🚨 SENPAI! A NEW PRE-ORDER JUST DROPPED! 🚨"
        else:
            status_changed = old_data['in_stock'] != is_in_stock
            price_changed = old_data['price'] != L['price']

            if status_changed or price_changed:
                should_notify = True
                if is_in_stock and not old_data['in_stock']:
                    ping_message = "@everyone 🌸 SENPAI! RESTOCK DETECTED! GET THOSE GRANDMASTER RARES! 🌸"

        if should_notify:
            embeds_to_send.append({
                "title": f"[{L['site']}] {L['name']}",
                "description": f"**Price:** {L['price']}\n**Status:** {L['status']}\n**Link:** [Click Here to View, Senpai!]({L['url']})",
                "color": L['color'],
                "footer": {"text": "Scouting the web just for you! (◕‿◕✿)"}
            })

    save_state(new_state)

    if not embeds_to_send:
        log.info("No changes detected. Keeping quiet to avoid spamming Senpai.")
        return

    for i in range(0, len(embeds_to_send), 10):
        chunk = embeds_to_send[i:i+10]
        payload = {
            "username": BOT_NAME,
            "avatar_url": BOT_AVATAR,
            "content": ping_message if (i == 0 and ping_message) else "✨ **Market Radar Update!** ✨",
            "embeds": chunk
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
        except Exception as e:
            log.error(f"Discord send failed: {e}")

def main():
    log.info("Generating full anime radar report (Sniper Mode)...")
    all_results = []
    all_results.extend(check_playwright_sites())
    all_results.extend(check_shopify_sites())
    analyze_changes_and_notify(all_results)
    log.info("Radar report evaluation complete.")

if __name__ == "__main__":
    main()
