"""
LeadGen Pro — Google Search Scraper
Uses Playwright to scrape Google Search results with anti-detection measures.
Extracts business name, URL, snippet, and title from search result pages.
"""

import asyncio
import logging
import random
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, quote_plus

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

# ── User Agent Pool ────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Domains to skip (directories, social media, not real business sites)
SKIP_DOMAINS = {
    "yelp.com", "yellowpages.com", "bbb.org", "facebook.com", "twitter.com",
    "instagram.com", "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
    "wikipedia.org", "reddit.com", "quora.com", "glassdoor.com", "indeed.com",
    "craigslist.org", "amazon.com", "ebay.com", "walmart.com", "etsy.com",
    "angieslist.com", "angi.com", "thumbtack.com", "homeadvisor.com",
    "google.com", "bing.com", "yahoo.com", "apple.com", "microsoft.com",
    "tripadvisor.com", "trustpilot.com", "manta.com", "chamberofcommerce.com",
    "mapquest.com", "superpages.com", "whitepages.com", "foursquare.com",
}


@dataclass
class SearchResult:
    """A single search result from Google."""
    name: str
    url: str
    snippet: str
    title: str
    page_num: int


def _is_valid_business_url(url: str) -> bool:
    """Check if URL is likely a real business website (not a directory/social)."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")

        # Skip known non-business domains
        for skip in SKIP_DOMAINS:
            if domain == skip or domain.endswith(f".{skip}"):
                return False

        # Must have a proper TLD
        if "." not in domain:
            return False

        # Skip very long URLs (usually directory listings)
        if len(url) > 300:
            return False

        return True
    except Exception:
        return False


def _extract_business_name(title: str, url: str) -> str:
    """Extract clean business name from search result title."""
    if not title:
        try:
            return urlparse(url).netloc.replace("www.", "").split(".")[0].title()
        except Exception:
            return "Unknown"

    # Remove common suffixes
    name = title
    for sep in [" | ", " - ", " — ", " – ", " :: ", " // "]:
        if sep in name:
            name = name.split(sep)[0]

    # Clean up
    name = name.strip()
    if len(name) > 200:
        name = name[:200]

    return name or title


async def _random_delay(min_sec: float = 2.0, max_sec: float = 5.0):
    """Add randomized delay to avoid detection."""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


async def search_google(
    query: str,
    max_pages: int = 3,
    delay_min: float = 3.0,
    delay_max: float = 7.0,
    headless: bool = True,
) -> list[SearchResult]:
    """
    Search Google for a query and extract business website results.

    Args:
        query: Search query (e.g., "roofing company texas")
        max_pages: Maximum number of result pages to scrape
        delay_min: Minimum delay between actions (seconds)
        delay_max: Maximum delay between actions (seconds)
        headless: Run browser in headless mode

    Returns:
        List of SearchResult objects
    """
    results: list[SearchResult] = []
    user_agent = random.choice(USER_AGENTS)

    logger.info(f"Searching Google: '{query}' (max {max_pages} pages)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Stealth: mask navigator.webdriver
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        page = await context.new_page()

        for page_num in range(max_pages):
            start_index = page_num * 10
            search_url = (
                f"https://www.google.com/search?q={quote_plus(query)}"
                f"&start={start_index}&hl=en&gl=us"
            )

            logger.info(f"  Page {page_num + 1}/{max_pages}: {search_url}")

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await _random_delay(delay_min, delay_max)

                # Handle cookie consent
                for btn_text in ["Accept all", "Accept", "I agree", "Reject all"]:
                    try:
                        btn = page.locator(f'button:has-text("{btn_text}")').first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await _random_delay(1, 2)
                            break
                    except Exception:
                        pass

                # Check for CAPTCHA
                body_text = await page.inner_text("body")
                if "unusual traffic" in body_text.lower() or "captcha" in body_text.lower():
                    logger.warning("CAPTCHA detected! Stopping search.")
                    break

                # Extract search results
                result_blocks = await page.query_selector_all("div.g")

                if not result_blocks:
                    # Try alternative selectors
                    result_blocks = await page.query_selector_all("div[data-sokoban-container]")

                if not result_blocks:
                    logger.warning(f"  No results found on page {page_num + 1}")
                    break

                page_results = 0
                for block in result_blocks:
                    try:
                        # Extract URL
                        link_el = await block.query_selector("a[href]")
                        if not link_el:
                            continue
                        href = await link_el.get_attribute("href") or ""

                        if not href.startswith("http"):
                            continue
                        if not _is_valid_business_url(href):
                            continue

                        # Extract title
                        title_el = await block.query_selector("h3")
                        title = ""
                        if title_el:
                            title = (await title_el.inner_text()).strip()

                        # Extract snippet
                        snippet = ""
                        for sel in ["div.VwiC3b", "span.aCOpRe", "div[data-sncf]", "div.IsZvec"]:
                            snippet_el = await block.query_selector(sel)
                            if snippet_el:
                                snippet = (await snippet_el.inner_text()).strip()
                                break

                        if not title and not snippet:
                            continue

                        # Build result
                        name = _extract_business_name(title, href)
                        result = SearchResult(
                            name=name,
                            url=href,
                            snippet=snippet[:1000],
                            title=title[:500],
                            page_num=page_num + 1,
                        )
                        results.append(result)
                        page_results += 1

                    except Exception as e:
                        logger.debug(f"  Error extracting result: {e}")
                        continue

                logger.info(f"  Extracted {page_results} results from page {page_num + 1}")

                # Check if there's a next page
                if page_num < max_pages - 1:
                    next_btn = await page.query_selector('a#pnnext, a[aria-label="Next"]')
                    if not next_btn:
                        logger.info("  No more pages available")
                        break
                    await _random_delay(delay_min, delay_max)

            except PWTimeout:
                logger.error(f"  Timeout loading page {page_num + 1}")
                break
            except Exception as e:
                logger.error(f"  Error on page {page_num + 1}: {e}")
                break

        await browser.close()

    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in results:
        normalized = urlparse(r.url).netloc.lower().replace("www.", "")
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            unique_results.append(r)

    logger.info(f"Search complete: {len(unique_results)} unique results for '{query}'")
    return unique_results


def extract_niche_location(query: str) -> tuple[Optional[str], Optional[str]]:
    """
    Try to parse niche and location from a search query.
    E.g., "roofing company texas" -> ("roofing company", "texas")
    """
    # Common location prepositions
    for prep in [" in ", " near ", " around ", " at "]:
        if prep in query.lower():
            parts = query.lower().split(prep, 1)
            return parts[0].strip(), parts[1].strip()

    # Fallback: last word might be location
    words = query.strip().split()
    if len(words) >= 3:
        return " ".join(words[:-1]), words[-1]

    return query.strip(), None
