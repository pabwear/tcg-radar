#!/usr/bin/env python3
"""
Magnificent Monsters Monitor - Anime Girl Edition (Monitor-chan 🌸)
SMART SNIPER EDITION: Automatically finds new links, but filters out junk!
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
PAGE_SETTLE_MS = 3000

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# Monitor-chan's Persona
BOT_NAME = "Monitor-chan 🌸 (Smart Sniper)"
BOT_AVATAR = "https://i.pinimg.com/originals/a4/0f/58/a40f589cda683eab5dc422d3d0f0d2c6.png"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

# ====================== STATE MANAGEMENT ======================
def load_state():
    if not supabase: return {}
    try:
        response = supabase.table("inventory_state").select("*").execute()
        return {row['id']: {"price": row['price'], "status": row['status'], "in_stock": row['in_stock']} for row in response.data}
    except Exception as e:
        log.error(f"Failed to load state from Supabase: {e}")
        return {}

def save_state(state):
    if not supabase: return
    try:
        records = [{"id": k, "price": v['price'], "status": v['status'], "in_stock": v['in_stock']} for k, v in state.items()]
        if records:
            supabase.table("inventory_state").upsert(records).execute()
    except Exception as e:
        log.error(f"Failed to save state to Supabase: {e}")

# ====================== AUTO-TARGETING LOGIC ======================
def is_valid_target(title, price_str):
    """STRICT FILTER: Only returns True for Booster Boxes and Displays."""
    title_lower = title.lower()
    
    # 1. Must be Magnificent Monsters
    if "magnificent" not in title_lower or "monsters" not in title_lower:
        return False
        
    # 2. Must NOT be singles, loose packs, or accessories
    bad_words = ["pack", "single", "sleeve", "mat", "token", "promo", "art", "deck box"]
    if any(bad in title_lower for bad in bad_words):
        return False
        
    # 3. MUST be a Box, Case, or Display
    good_words = ["box", "display", "case", "booster"]
    if not any(good in title_lower for good in good_words):
        return False
        
    # 4. Price Floor (If a price exists, it must be > $25 to filter out loose packs)
    if price_str and price_str != "N/A":
        try:
            val = float(re.sub(r'[^\d.]', '', price_str))
            if val < 25.0:
                return False
        except Exception:
            pass # Keep going if price formatting is weird
            
    return True

def evaluate_price(name, price_str):
    if not price_str or price_str == "N/A": return ""
    try:
        val = float(re.sub(r'[^\d.]', '', price_str))
        name_lower = name.lower()

        if "display" in name_lower or "10x" in name_lower or "case" in name_lower: msrp = 350.0  
        else: msrp = 35.0   

        if val <= msrp * 0.95: return " 📉 (Super Cheap! ✨)"
        elif val <= msrp * 1.15: return " ✅ (Fair Price~! 🌸)"
        elif val <= msrp * 2.00: return " ⚠️ (Yabai! High Price! 💦)"
        else: return " 🛑 (Baka Scalper! 😡)"
    except Exception:
        return ""

# ====================== SMART SCRAPERS ======================
def check_playwright_sites():
    listings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        # --- TCGPlayer (Targeted Search) ---
        tcg_url = "https://www.tcgplayer.com/search/yugioh/product?productLineName=yugioh&q=magnificent+monsters+booster&view=grid"
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        try:
            log.info("Scanning TCGPlayer...")
            page.goto(tcg_url, timeout=PAGE_TIMEOUT)
            if "just a moment" in page.title().lower() or "security" in page.title().lower():
                pass # Blocked, ignore quietly
            else:
                page.wait_for_selector(".search-result__item", timeout=10000)
                cards = page.query_selector_all(".search-result__item")
                for card in cards[:5]: # Check top 5 results
                    text = card.inner_text()
                    name = text.split('\n')[0].strip()
                    price_match = re.search(r"\$[\d,]+\.\d{2}", text)
                    price = price_match.group(0) if price_match else "N/A"
                    
                    if is_valid_target(name, price):
                        link_elem = card.query_selector("a")
                        product_url = f"https://www.tcgplayer.com{link_elem.get_attribute('href')}" if link_elem else tcg_url
                        display_price = f"{price}{evaluate_price(name, price)}"
                        listings.append({"site": "TCGplayer", "name": name, "price": display_price, "url": product_url, "status": "✅ IN STOCK! (Gotta go fast! 💨)", "color": 0x3498DB})
        except Exception as e:
            log.error(f"TCGPlayer search failed: {e}")
        finally:
            page.close()
            
        browser.close()
    return listings

def check_shopify_sites():
    """Sweeps Shopify APIs for new links automatically."""
    listings = []
    stores = [
        {"name": "Prodigy Games", "url": "https://prodigygames.com"},
        {"name": "Gamers Choice", "url": "https://www.gamerschoice.com"},
        {"name": "CoreTCG", "url": "https://www.coretcg.com"}
    ]
    
    with Session(impersonate="chrome120") as session:
        for store in stores:
            log.info(f"Sweeping {store['name']} API...")
            base = store["url"]
            # Search for 'magnificent monsters box' to narrow results
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
            pass

def main():
    log.info("Starting Auto-Discovery Sweep...")
    all_results = []
    all_results.extend(check_playwright_sites())
    all_results.extend(check_shopify_sites())
    analyze_changes_and_notify(all_results)
    log.info("Sweep complete.")

if __name__ == "__main__":
    main()
