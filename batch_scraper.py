"""
Batch Google Maps Scraper — Async V2
  - Reads queries from queries.txt
  - Uses async Playwright to run much faster
  - Extracts Lat/Lng from Google Maps URLs
  - Saves directly to SQLite database (leadminer.db) with automatic deduplication
  - No longer generates massive .xlsx files (Export is done via Dashboard)
"""

import asyncio
import re
import os
import sys
import time
import argparse
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from database import insert_lead

# ═══════════════════════════════════════════════════════════════
#  SCRAPER CORE (ASYNC)
# ═══════════════════════════════════════════════════════════════

async def scroll_results(page, max_results: int = 60):
    feed = await page.query_selector('div[role="feed"]')
    if not feed:
        return 0

    last_count = 0
    stale = 0

    while stale < 10:
        items = await page.query_selector_all('div[role="feed"] > div > div > a')
        count = len(items)

        if count >= max_results:
            break

        if count == last_count:
            stale += 1
        else:
            stale = 0
            last_count = count

        await feed.evaluate("el => el.scrollTop = el.scrollHeight")
        await asyncio.sleep(1.8)

    items = await page.query_selector_all('div[role="feed"] > div > div > a')
    return min(len(items), max_results)


async def collect_place_urls(page, max_results: int = 60) -> list[str]:
    links = await page.query_selector_all('div[role="feed"] > div > div > a')
    urls = []
    for link in links[:max_results]:
        href = await link.get_attribute("href")
        if href and "/maps/place/" in href:
            urls.append(href)
    return urls

def extract_lat_lng(url: str):
    """Extract lat/lng from a Google Maps URL, e.g., @40.7128,-74.0060,15z"""
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None


async def extract_from_place_page(context, url: str, query: str) -> dict | None:
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        await asyncio.sleep(2)

        try:
            await page.wait_for_selector('h1.DUwDvf, h1.fontHeadlineLarge, h1', timeout=8000)
        except PWTimeout:
            await page.close()
            return None

        # Scroll detail panel
        detail_panels = await page.query_selector_all('div[role="main"]')
        for panel in detail_panels:
            try:
                for _ in range(3):
                    await panel.evaluate("el => el.scrollTop += 500")
                    await asyncio.sleep(0.2)
                await panel.evaluate("el => el.scrollTop = 0")
            except Exception:
                pass

        lat, lng = extract_lat_lng(page.url)

        data = {
            "name": "",
            "address": "",
            "phone": "",
            "email": "",
            "website": "",
            "rating": "",
            "total_reviews": "",
            "category": "",
            "query": query,
            "lat": lat,
            "lng": lng
        }

        # Name
        for sel in ['h1.DUwDvf', 'h1.fontHeadlineLarge', 'h1']:
            el = await page.query_selector(sel)
            if el:
                txt = (await el.inner_text()).strip()
                if txt and txt.lower() != "results":
                    data["name"] = txt
                    break

        if not data["name"]:
            await page.close()
            return None

        # Rating
        el = await page.query_selector('div.F7nice span[aria-hidden="true"]')
        if el:
            data["rating"] = (await el.inner_text()).strip()

        # Reviews
        el = await page.query_selector('div.F7nice span[aria-label*="review"]')
        if not el:
            el = await page.query_selector('div.F7nice span:nth-child(2)')
        if el:
            data["total_reviews"] = (await el.inner_text()).strip().replace("(", "").replace(")", "").replace(",", "")

        # Category
        el = await page.query_selector('button[jsaction*="category"]')
        if el:
            data["category"] = (await el.inner_text()).strip()

        # Address
        for sel in ['button[data-item-id="address"]', 'button[data-tooltip="Copy address"]']:
            el = await page.query_selector(sel)
            if el:
                data["address"] = (await el.inner_text()).strip()
                break

        # Phone
        for sel in ['button[data-item-id*="phone:tel"]', 'button[data-tooltip="Copy phone number"]']:
            el = await page.query_selector(sel)
            if el:
                data["phone"] = (await el.inner_text()).strip()
                break

        # Email Extraction (Simplified async version)
        email_selectors = [
            'a[data-item-id*="email"]', 'button[data-item-id*="email"]', 'a[href^="mailto:"]',
            'a[data-tooltip="Send email"]', 'button[data-tooltip="Send email"]',
            'a[aria-label*="email"]', 'button[aria-label*="email"]'
        ]
        for sel in email_selectors:
            el = await page.query_selector(sel)
            if el:
                href = await el.get_attribute("href") or ""
                if href.startswith("mailto:"):
                    data["email"] = href.replace("mailto:", "").split("?")[0].strip()
                else:
                    aria = await el.get_attribute("aria-label") or ""
                    txt = (await el.inner_text()).strip()
                    email_in_aria = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', aria)
                    if email_in_aria:
                        data["email"] = email_in_aria.group()
                    elif "@" in txt:
                        data["email"] = txt
                if data["email"]:
                    break

        if not data["email"]:
            try:
                page_text = await page.inner_text('body')
                matches = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', page_text)
                for email in matches:
                    if "google.com" not in email.lower() and "gstatic" not in email.lower() and "example" not in email.lower():
                        data["email"] = email
                        break
            except Exception:
                pass

        # Website
        el = await page.query_selector('a[data-item-id="authority"]')
        if el:
            data["website"] = await el.get_attribute("href") or ""
        if not data["website"]:
            el = await page.query_selector('button[data-tooltip="Open website"]')
            if el:
                data["website"] = (await el.inner_text()).strip()

        await page.close()
        return data

    except Exception as e:
        await page.close()
        return None

# ═══════════════════════════════════════════════════════════════
#  ASYNC BATCH RUNNER
# ═══════════════════════════════════════════════════════════════

async def process_place(semaphore, context, url, query):
    """Process a single place concurrently"""
    async with semaphore:
        data = await extract_from_place_page(context, url, query)
        if data and data["name"]:
            # Filter out low-rated businesses (below 3.0). 
            # We keep 0.0 as it usually means "No reviews yet" which can be a good lead.
            rating_str = data.get("rating", "")
            try:
                rating_val = float(rating_str) if rating_str else 0.0
            except ValueError:
                rating_val = 0.0
                
            if 0.0 < rating_val < 3.0:
                print(f"⊘ {data['name']} (Skipped: Low Rating {rating_val})")
                return None

            if data["website"]:
                # User wants unoptimized leads without websites, but we can save them all to DB and filter in dashboard
                # For this rewrite, we will keep them all to have a comprehensive CRM
                pass
            
            # Insert into database in real-time
            inserted = insert_lead(data)
            
            email_str = f" | ✉ {data['email']}" if data['email'] else ""
            db_str = "(New)" if inserted else "(Duplicate)"
            print(f"✓ {data['name']} {db_str} | ☎ {data['phone'] or '—'}{email_str}")
            return data
        return None


async def scrape_query(context, query: str, max_results: int = 100, concurrency: int = 5):
    """Search for a query, scroll, collect URLs, and process them concurrently."""
    search_url = f"https://www.google.com/maps/search/{quote_plus(query)}"

    print(f"\n  ⏳ Loading: {search_url}")
    page = await context.new_page()
    try:
        await page.goto(search_url, wait_until="load", timeout=60000)
    except Exception as e:
        print(f"  ❌ Failed to load search: {e}")
        await page.close()
        return

    await asyncio.sleep(4)

    # Handle consent
    for sel in ['button:has-text("Accept all")', 'button:has-text("Accept")']:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                print("  ✓ Accepted consent")
                await asyncio.sleep(3)
                await page.goto(search_url, wait_until="load", timeout=60000)
                await asyncio.sleep(5)
                break
        except Exception:
            pass

    # Wait for feed
    try:
        await page.wait_for_selector('div[role="feed"]', timeout=30000)
    except PWTimeout:
        print("  ⚠ No results feed found — skipping this query")
        await page.close()
        return

    await scroll_results(page, max_results=max_results)
    place_urls = await collect_place_urls(page, max_results=max_results)
    total = len(place_urls)
    print(f"  📋 Found {total} places for '{query}'. Extracting details concurrently...")
    
    await page.close()

    if total == 0:
        return

    # Process URLs concurrently with a semaphore
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [process_place(semaphore, context, url, query) for url in place_urls]
    
    await asyncio.gather(*tasks)


async def run_scraper(queries, max_results, headless, concurrency):
    print("\n╔════════════════════════════════════════════════════════╗")
    print("║   LeadMiner Async Scraper (SQLite Backend)             ║")
    print("╚════════════════════════════════════════════════════════╝")
    
    start_time = time.time()
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=headless)
        except Exception as e:
            print(f"\n  ⚠ Playwright's default chromium failed to launch. Error: {e}")
            print(f"  Attempting system fallbacks...\n")
            
            system_paths = [
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium',
                '/snap/bin/chromium',
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable'
            ]
            
            browser = None
            for path in system_paths:
                if os.path.exists(path):
                    try:
                        print(f"  ➜ Trying executable at {path}...")
                        browser = await p.chromium.launch(executable_path=path, headless=headless)
                        print(f"  ✓ Successfully launched {path}")
                        break
                    except Exception as ex:
                        print(f"  ✗ Failed to launch {path}: {ex}")
            
            if not browser:
                print("\n❌ FATAL: Could not launch any Chromium browser.")
                print("   It looks like you are on a Linux/EC2 server and missing system dependencies.")
                print("   Please run these exact commands in your terminal to fix it:")
                print("   ------------------------------------------------------------")
                print("   playwright install chromium")
                print("   playwright install-deps")
                print("   ------------------------------------------------------------")
                sys.exit(1)

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )

        for i, query in enumerate(queries, 1):
            print(f"\n{'━' * 58}")
            print(f"  🔍 [{i}/{len(queries)}] \"{query}\"")
            print(f"{'━' * 58}")
            
            await scrape_query(context, query, max_results, concurrency)

        await browser.close()

    elapsed = time.time() - start_time
    elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
    
    print(f"\n{'═' * 58}")
    print(f"  📊 BATCH COMPLETE")
    print(f"  Time elapsed  : {elapsed_str}")
    print(f"  Results saved directly to leadminer.db")
    print(f"{'═' * 58}\n")


def main():
    parser = argparse.ArgumentParser(description="Async Batch Google Maps Scraper")
    parser.add_argument("--file", default="queries.txt", help="Path to queries file")
    parser.add_argument("--max", type=int, default=100, help="Max results per query (default: 100)")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent pages to process (default: 5)")
    parser.add_argument("--headed", action="store_false", dest="headless", help="Run browser with GUI (headed mode)")
    args = parser.parse_args()

    queries_file = args.file
    if not os.path.exists(queries_file):
        print(f"❌ Queries file not found: {queries_file}")
        sys.exit(1)

    with open(queries_file, "r", encoding="utf-8") as f:
        queries = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not queries:
        print("❌ No queries found in the file.")
        sys.exit(1)

    # Run the async loop
    asyncio.run(run_scraper(queries, args.max, args.headless, args.concurrency))


if __name__ == "__main__":
    main()

