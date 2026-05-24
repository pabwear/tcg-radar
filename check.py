#!/usr/bin/env python3
"""
Magnificent Monsters Monitor (The Ultimate Hybrid Edition)
Direct targets GameNerdz/TCGPlayer/Dave&Adams + Auto-Sweeps Shopify sites!
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

BOT_NAME = "Monitor-chan 🌸 (Hybrid Sniper)"
BOT_AVATAR = "https://i.pinimg.com/originals/a4/0f/58/a40f589cda683eab5dc422d3d0f0d2c6.png"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

# ====================== 🎯 DIRECT TARGET URLS ======================
TARGET_URLS = {
    "TCGplayer_Box": "https://www.tcgplayer.com/product/694828/yugioh-magnificent-monsters-magnificent-monsters-box",
    "TCGplayer_Display": "https://www.tcgplayer.com/product/694826/yugioh-magnificent-monsters-magnificent-monsters-display",
    "GameNerdz_Display": "https://www.gamenerdz.com/yu-gi-oh-magnificent-monsters-display-1st-edition-preorder",
    "GameNerdz_Box": "https://www.gamenerdz.com/maganificent-monsters-1st-edition/",
    "Dave_And_Adams": "https://www.dacardworld.com/gaming/yu-gi-oh-magnificent-monsters-booster-box"
}

# ====================== STATE MANAGEMENT ======================
def load_state():
    if not supabase: return {}
    try:
        response = supabase.table("inventory_state").select("*").execute()
        return {row['id']: {"price": row['price'], "status": row['status'], "in_stock": row['in_stock']} for row in response.data}
    except Exception as e:
        log.error(f"Failed to load state: {e}")
        return {}

def save_state(state):
    if not supabase: return
    try:
        records = [{"id": k, "price": v['price'], "status": v['status'], "in_stock": v['in_stock']} for k, v in state.items()]
        if records:
            supabase.table("inventory_state").upsert(records).execute()
    except Exception as e:
        log.error(f"Failed to save state: {e}")

# ====================== LOGIC ======================
def is_valid_target(title, price_str):
    """Filters out single packs, sleeves, etc. during Shopify sweeps."""
    title_lower = title.lower()
    if "magnificent" not in title_lower or "monsters" not in title_lower: return False
    
    bad_words = ["pack", "single", "sleeve", "mat", "token", "promo"]
    if any(bad in title_lower for bad in bad_words): return False
        
    good_words = ["box", "display", "case", "booster"]
    if not any(good in title_lower for good in good_words): return False
        
    if price_str and price_str != "N/A":
        try:
            if float(re.sub(r'[^\d.]', '', price_str)) < 25.0: return False
        except Exception: pass
    return True

def evaluate_price(name, price_str):
    if not price_str or price_str == "N/A": return ""
    try:
        val = float(re.sub(r'[^\d.]', '', price_str))
        msrp = 350.0 if any(x in name.lower() for x in ["display", "10x", "case"]) else 35.0   

        if val <= msrp * 0.95: return " 📉 (Super Cheap! ✨)"
        elif val <= msrp * 1.15: return " ✅ (Fair Price~! 🌸)"
        elif val <= msrp * 2.00: return " ⚠️ (Yabai! High Price! 💦)"
        else: return " 🛑 (Baka Scalper! 😡)"
    except Exception:
        return ""

# ====================== HYBRID SCRAPERS ======================
def check_playwright_sites():
    """Hits the direct landing pages that already exist."""
    listings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        
        # --- TCGPlayer Direct Links ---
        for key in ["TCGplayer_Box", "TCGplayer_Display"]:
            url = TARGET_URLS[key]
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                page.goto(url, timeout=PAGE_TIMEOUT)
                if "security" not in page.title().lower():
                    name_loc = page.locator(".product-details__name")
                    name = name_loc.inner_text() if name_loc.count() > 0 else "Magnificent Monsters Box"
                    price_loc = page.locator(".spotlight__price")
                    price = price_loc.inner_text() if price_loc.count() > 0 else "N/A"
                    
                    status = "✅ IN STOCK! (Gotta go fast! 💨)" if price != "N/A" else "❌ Out of Stock (Sadge... 🥺)"
                    color = 0x3498DB if price != "N/A" else 0xE74C3C
                    
                    listings.append({"site": "TCGplayer", "name": name, "price": f"{price}{evaluate_price(name, price)}", "url": url, "status": status, "color": color})
            except Exception as e:
                log.error(f"TCGplayer Error: {e}")
            finally:
                page.close()

        # --- GameNerdz Direct Links ---
        for gn_key in ["GameNerdz_Display", "GameNerdz_Box"]:
            url = TARGET_URLS[gn_key]
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                resp = page.goto(url, timeout=PAGE_TIMEOUT)
                if resp.status != 404:
                    page.wait_for_selector(".productView-title", timeout=10000)
                    name = page.locator(".productView-title").inner_text()
                    price = page.locator(".price.price--withoutTax").first.inner_text()
                    
                    try:
                        stock_text = page.locator("[data-product-stock]").inner_text().lower()
                    except Exception:
                        stock_text = page.locator("#form-action-addToCart").inner_text().lower()

                    is_oos = "out of stock" in stock_text or "sold out" in stock_text
                    status = "❌ Out of Stock (Sadge... 🥺)" if is_oos else "✅ IN STOCK! (Gotta go fast! 💨)"
                    color = 0xE74C3C if is_oos else 0x3498DB
                    
                    listings.append({"site": "GameNerdz", "name": name, "price": f"{price}{evaluate_price(name, price)}", "url": url, "status": status, "color": color})
            except Exception as e:
                log.error(f"GameNerdz Error: {e}")
            finally:
                page.close()

        # --- DA Card World Direct ---
        url = TARGET_URLS["Dave_And_Adams"]
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        try:
            page.goto(url, timeout=PAGE_TIMEOUT)
            name_loc = page.locator("h1.product-title")
            name = name_loc.inner_text() if name_loc.count() > 0 else "Magnificent Monsters Box"
            price_loc = page.locator(".price")
            price = price_loc.inner_text() if price_loc.count() > 0 else "N/A"
            btn_loc = page.locator("#add-to-cart")
            
            is_oos = btn_loc.count() == 0 or price == "N/A"
            status = "❌ Out of Stock (Sadge... 🥺)" if is_oos else "✅ IN STOCK! (Gotta go fast! 💨)"
            color = 0xE74C3C if is_oos else 0x3498DB
            
            listings.append({"site": "Dave & Adam's", "name": name, "price": f"{price}{evaluate_price(name, price)}", "url": url, "status": status, "color": color})
        except Exception as e:
            log.error(f"DA Card World Error: {e}")
        finally:
            page.close()

        browser.close()
    return listings

def check_shopify_sites():
    """Sweeps Shopify APIs for links automatically."""
    listings = []
    stores = [
        {"name": "Prodigy Games", "url": "https://prodigygames.com"},
        {"name": "Gamers Choice", "url": "https://www.gamerschoice.com"},
        {"name": "CoreTCG", "url": "https://www.coretcg.com"},
        {"name": "Forge and Fire", "url": "https://forgeandfiregaming.com"},
        {"name": "Ideal808", "url": "https://www.ideal808.com"},
        {"name": "YGO Black Market", "url": "https://ygoblackmarket.com"}
    ]
    
    with Session(impersonate="chrome120") as session:
        for store in stores:
            log.info(f"Sweeping {store['name']} API...")
            base = store["url"]
            api_url = f"{base}/search/suggest.json?q=magnificent+monsters+box&resources[type]=product"
            
            try:
                resp = session.get(api_url, timeout=10)
                if resp.status_code != 200: continue
                
                products = resp.json().get("resources", {}).get("results", {}).get("products", [])
                for p in products:
                    title = p.get("title", "")
                    variants = p.get("variants", [{}])
                    first_variant = variants[0] if variants else {}
                    price = f"${float(first_variant.get('price', 0)):.2f}"
                    
                    if is_valid_target(title, price):
                        is_available = first_variant.get("available", False)
                        product_url = f"{base}{p.get('url', '').split('?')[0]}"
                        display_price = f"{price}{evaluate_price(title, price)}"
                        
                        status = "✅ IN STOCK! (Gotta go fast! 💨)" if is_available else "❌ Out of Stock (Sadge... 🥺)"
                        color = 0x2ECC71 if is_available else 0xE74C3C
                        
                        listings.append({"site": store["name"], "name": title, "price": display_price, "url": product_url, "status": status, "color": color})
            except Exception as e:
                log.error(f"Shopify Error for {store['name']}: {e}")
                
    return listings

def analyze_changes_and_notify(all_listings):
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
            if is_in_stock: ping_message = "@everyone 🚨 SENPAI! A NEW PRE-ORDER LINK JUST DROPPED! 🚨"
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
        log.info("No changes detected. Keeping quiet.")
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
        except Exception:
            pass

def main():
    log.info("Starting Hybrid Discovery Sweep...")
    all_results = []
    all_results.extend(check_playwright_sites())
    all_results.extend(check_shopify_sites())
    analyze_changes_and_notify(all_results)
    log.info("Sweep complete.")

if __name__ == "__main__":
    main()
