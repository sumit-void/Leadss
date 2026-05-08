"""
LeadGen — Google Search Scraper
Searches Google for businesses, extracts website URLs.
Uses Playwright with anti-detection.
"""

import asyncio
import random
import re
import logging
from urllib.parse import urlparse, quote_plus
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36",
]

SKIP_DOMAINS = {
    "yelp.com", "yellowpages.com", "bbb.org", "facebook.com", "twitter.com",
    "instagram.com", "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
    "wikipedia.org", "reddit.com", "quora.com", "google.com", "bing.com",
    "amazon.com", "ebay.com", "tripadvisor.com", "trustpilot.com",
    "angieslist.com", "angi.com", "thumbtack.com", "homeadvisor.com",
    "manta.com", "foursquare.com", "apple.com", "microsoft.com",
}


def _is_valid_url(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        for skip in SKIP_DOMAINS:
            if domain == skip or domain.endswith(f".{skip}"):
                return False
        if "." not in domain or len(url) > 300:
            return False
        return True
    except Exception:
        return False


def _extract_name(title: str, url: str) -> str:
    if not title:
        try:
            return urlparse(url).netloc.replace("www.", "").split(".")[0].title()
        except Exception:
            return "Unknown"
    for sep in [" | ", " - ", " — ", " – "]:
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()[:200]


def parse_niche_location(query: str):
    for prep in [" in ", " near ", " around "]:
        if prep in query.lower():
            parts = query.lower().split(prep, 1)
            return parts[0].strip(), parts[1].strip()
    words = query.strip().split()
    if len(words) >= 3:
        return " ".join(words[:-1]), words[-1]
    return query.strip(), ""


async def search_google(query: str, max_pages: int = 3, headless: bool = True):
    """
    Search Google and return list of dicts:
    [{name, url, snippet, title, page_num}, ...]
    """
    results = []
    ua = random.choice(USER_AGENTS)

    print(f"  🔍 Searching: {query}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=ua,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        for page_num in range(max_pages):
            start = page_num * 10
            url = f"https://www.google.com/search?q={quote_plus(query)}&start={start}&hl=en"

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.uniform(3, 6))

                # Cookie consent
                for txt in ["Accept all", "Reject all", "Accept"]:
                    try:
                        btn = page.locator(f'button:has-text("{txt}")').first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        pass

                # CAPTCHA check
                body = await page.inner_text("body")
                if "unusual traffic" in body.lower():
                    print("  ⚠️ CAPTCHA detected — stopping")
                    break

                # Extract results
                blocks = await page.query_selector_all("div.g")
                if not blocks:
                    blocks = await page.query_selector_all("div[data-sokoban-container]")
                if not blocks:
                    print(f"  ⚠️ No results on page {page_num + 1}")
                    break

                count = 0
                for block in blocks:
                    try:
                        link = await block.query_selector("a[href]")
                        if not link:
                            continue
                        href = await link.get_attribute("href") or ""
                        if not href.startswith("http") or not _is_valid_url(href):
                            continue

                        title_el = await block.query_selector("h3")
                        title = (await title_el.inner_text()).strip() if title_el else ""

                        snippet = ""
                        for sel in ["div.VwiC3b", "span.aCOpRe", "div[data-sncf]"]:
                            s = await block.query_selector(sel)
                            if s:
                                snippet = (await s.inner_text()).strip()
                                break

                        if not title and not snippet:
                            continue

                        results.append({
                            "name": _extract_name(title, href),
                            "url": href,
                            "snippet": snippet[:500],
                            "title": title[:300],
                            "page_num": page_num + 1,
                        })
                        count += 1
                    except Exception:
                        continue

                print(f"  📄 Page {page_num + 1}: {count} results")

                # Check next page exists
                if page_num < max_pages - 1:
                    nxt = await page.query_selector('a#pnnext, a[aria-label="Next"]')
                    if not nxt:
                        break
                    await asyncio.sleep(random.uniform(3, 6))

            except PWTimeout:
                print(f"  ⚠️ Timeout on page {page_num + 1}")
                break
            except Exception as e:
                print(f"  ❌ Error: {e}")
                break

        await browser.close()

    # Deduplicate by domain
    seen = set()
    unique = []
    for r in results:
        domain = urlparse(r["url"]).netloc.lower().replace("www.", "")
        if domain not in seen:
            seen.add(domain)
            unique.append(r)

    print(f"  ✅ {len(unique)} unique businesses found")
    return unique
