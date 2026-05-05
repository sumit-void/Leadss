"""
LeadMiner — Batch Google Maps Scraper
  - Reads queries from queries.txt
  - Uses async Playwright for speed
  - HARD FILTERS: skip website, require phone, require 2+ rating
  - Each run = unique batch_id (never overwrites old data)
  - Saves directly to SQLite (leadminer.db)
"""

import asyncio, re, os, sys, time, argparse
from urllib.parse import quote_plus
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from database import insert_lead, generate_batch_id


async def scroll_results(page, max_results=60):
    feed = await page.query_selector('div[role="feed"]')
    if not feed:
        return 0
    last_count, stale = 0, 0
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
    return min(len(await page.query_selector_all('div[role="feed"] > div > div > a')), max_results)


async def collect_place_urls(page, max_results=60):
    links = await page.query_selector_all('div[role="feed"] > div > div > a')
    urls = []
    for link in links[:max_results]:
        href = await link.get_attribute("href")
        if href and "/maps/place/" in href:
            urls.append(href)
    return urls


def extract_lat_lng(url):
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


async def extract_from_place_page(context, url, query):
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        await asyncio.sleep(2)
        try:
            await page.wait_for_selector('h1.DUwDvf, h1.fontHeadlineLarge, h1', timeout=8000)
        except PWTimeout:
            await page.close()
            return None

        for panel in await page.query_selector_all('div[role="main"]'):
            try:
                for _ in range(3):
                    await panel.evaluate("el => el.scrollTop += 500")
                    await asyncio.sleep(0.2)
                await panel.evaluate("el => el.scrollTop = 0")
            except Exception:
                pass

        lat, lng = extract_lat_lng(page.url)
        data = {"name":"","address":"","phone":"","email":"","website":"",
                "rating":"","total_reviews":"","category":"","query":query,"lat":lat,"lng":lng}

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
            data["total_reviews"] = (await el.inner_text()).strip().replace("(","").replace(")","").replace(",","")

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

        # Email
        for sel in ['a[data-item-id*="email"]','button[data-item-id*="email"]','a[href^="mailto:"]',
                     'a[data-tooltip="Send email"]','button[data-tooltip="Send email"]']:
            el = await page.query_selector(sel)
            if el:
                href = await el.get_attribute("href") or ""
                if href.startswith("mailto:"):
                    data["email"] = href.replace("mailto:","").split("?")[0].strip()
                else:
                    aria = await el.get_attribute("aria-label") or ""
                    txt = (await el.inner_text()).strip()
                    m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', aria)
                    if m:
                        data["email"] = m.group()
                    elif "@" in txt:
                        data["email"] = txt
                if data["email"]:
                    break

        if not data["email"]:
            try:
                page_text = await page.inner_text('body')
                for email in re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', page_text):
                    if "google.com" not in email.lower() and "gstatic" not in email.lower():
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
    except Exception:
        await page.close()
        return None


async def process_place(sem, ctx, url, query, batch_id, stats):
    async with sem:
        data = await extract_from_place_page(ctx, url, query)
        if not data or not data["name"]:
            stats["failed"] += 1
            return None

        # FILTER 1: Skip if has website
        if data.get("website","").strip():
            print(f"  ⊘ {data['name']} — Has website, skipped")
            stats["skipped_website"] += 1
            return None

        # FILTER 2: Skip if no phone
        if not data.get("phone","").strip():
            print(f"  ⊘ {data['name']} — No phone, skipped")
            stats["skipped_no_phone"] += 1
            return None

        # FILTER 3: Skip if rating < 2.0 (keep unrated)
        try:
            rv = float(data.get("rating","") or "0")
        except ValueError:
            rv = 0.0
        if 0 < rv < 2.0:
            print(f"  ⊘ {data['name']} — Low rating ({rv}), skipped")
            stats["skipped_low_rating"] += 1
            return None

        inserted = insert_lead(data, batch_id=batch_id)
        em = f" | ✉ {data['email']}" if data['email'] else ""
        rt = f" | ⭐ {rv}" if rv > 0 else ""
        db = "(New)" if inserted else "(Dup)"
        print(f"  ✓ {data['name']} {db} | ☎ {data['phone']}{em}{rt}")
        stats["saved"] += 1
        return data


async def scrape_query(ctx, query, batch_id, max_results=100, concurrency=5):
    url = f"https://www.google.com/maps/search/{quote_plus(query)}"
    print(f"\n  ⏳ Loading: {url}")
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="load", timeout=60000)
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        await page.close()
        return {}
    await asyncio.sleep(4)

    for sel in ['button:has-text("Accept all")', 'button:has-text("Accept")']:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(3)
                await page.goto(url, wait_until="load", timeout=60000)
                await asyncio.sleep(5)
                break
        except Exception:
            pass

    try:
        await page.wait_for_selector('div[role="feed"]', timeout=30000)
    except PWTimeout:
        print("  ⚠ No results feed — skipping")
        await page.close()
        return {}

    await scroll_results(page, max_results)
    place_urls = await collect_place_urls(page, max_results)
    print(f"  📋 Found {len(place_urls)} places for '{query}'")
    await page.close()

    if not place_urls:
        return {}

    stats = {"saved":0,"skipped_website":0,"skipped_no_phone":0,"skipped_low_rating":0,"failed":0}
    sem = asyncio.Semaphore(concurrency)
    await asyncio.gather(*[process_place(sem, ctx, u, query, batch_id, stats) for u in place_urls])
    return stats


async def run_scraper(queries, max_results, headless, concurrency):
    batch_id = generate_batch_id()
    print("\n╔════════════════════════════════════════════════════╗")
    print("║   LeadMiner Scraper                                ║")
    print("╚════════════════════════════════════════════════════╝")
    print(f"  Batch  : {batch_id}")
    print(f"  Queries: {len(queries)}")
    print(f"  Filters: No website ✓ | Has phone ✓ | Rating ≥ 2.0 ✓")

    start = time.time()
    totals = {"saved":0,"skipped_website":0,"skipped_no_phone":0,"skipped_low_rating":0,"failed":0}

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=headless)
        except Exception:
            browser = None
            for path in ['/usr/bin/chromium-browser','/usr/bin/chromium','/snap/bin/chromium',
                         '/usr/bin/google-chrome','/usr/bin/google-chrome-stable']:
                if os.path.exists(path):
                    try:
                        browser = await p.chromium.launch(executable_path=path, headless=headless)
                        break
                    except Exception:
                        pass
            if not browser:
                print("❌ No browser found. Run: playwright install chromium")
                sys.exit(1)

        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="en-US")

        for i, q in enumerate(queries, 1):
            print(f"\n{'━'*55}")
            print(f"  🔍 [{i}/{len(queries)}] \"{q}\"")
            print(f"{'━'*55}")
            s = await scrape_query(ctx, q, batch_id, max_results, concurrency)
            for k in totals:
                totals[k] += s.get(k, 0)

        await browser.close()

    elapsed = time.strftime("%H:%M:%S", time.gmtime(time.time() - start))
    print(f"\n{'═'*55}")
    print(f"  📊 DONE — {batch_id}")
    print(f"  Time: {elapsed} | Saved: {totals['saved']}")
    print(f"  Skipped → Website: {totals['skipped_website']} | No phone: {totals['skipped_no_phone']} | Low rating: {totals['skipped_low_rating']}")
    print(f"{'═'*55}\n")


def main():
    ap = argparse.ArgumentParser(description="LeadMiner Scraper")
    ap.add_argument("--file", default="queries.txt")
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--headed", action="store_false", dest="headless")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        queries = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    if not queries:
        print("❌ No queries found.")
        sys.exit(1)

    asyncio.run(run_scraper(queries, args.max, args.headless, args.concurrency))


if __name__ == "__main__":
    main()
