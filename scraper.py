"""
LeadGen — Search Scraper
Multi-source business URL discovery using:
  1. DuckDuckGo HTML (with retry on rate-limit)
  2. Bing HTML fallback
  3. SearXNG public instance fallback
Pure httpx — no browser / Playwright dependency.
"""

import asyncio
import random
import re
import logging
import json
import argparse
import sys
import os
import functools
from urllib.parse import urlparse, urlencode, quote_plus

# Force unbuffered stdout so progress is visible in real-time
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Override print to always flush
_builtin_print = print
def print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    _builtin_print(*args, **kwargs)

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── User-Agent pool ───────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]

# ── Public SearXNG instances (no auth, no key required) ───────────────────────
SEARXNG_INSTANCES = [
    "https://searx.be",
    "https://search.bus-hit.me",
    "https://searx.tiekoetter.com",
    "https://searxng.world",
    "https://search.inetol.net",
    "https://priv.au",
    "https://search.sapti.me",
    "https://searx.tuxcloud.net",
]

# ── Domains to skip ───────────────────────────────────────────────────────────
SKIP_DOMAINS = {
    "yelp.com", "yellowpages.com", "bbb.org", "facebook.com", "twitter.com",
    "x.com", "instagram.com", "linkedin.com", "youtube.com", "tiktok.com",
    "pinterest.com", "wikipedia.org", "reddit.com", "quora.com", "google.com",
    "bing.com", "amazon.com", "ebay.com", "tripadvisor.com", "trustpilot.com",
    "angieslist.com", "angi.com", "thumbtack.com", "homeadvisor.com",
    "manta.com", "foursquare.com", "apple.com", "microsoft.com",
    "duckduckgo.com", "yahoo.com",
}


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        if "." not in domain or len(url) > 300:
            return False
        for skip in SKIP_DOMAINS:
            if domain == skip or domain.endswith(f".{skip}"):
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
    for sep in [" | ", " - ", " — ", " – ", " :: "]:
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()[:200]


def parse_niche_location(query: str):
    for prep in [" in ", " near ", " around "]:
        if prep in query.lower():
            idx = query.lower().index(prep)
            return query[:idx].strip(), query[idx + len(prep):].strip()
    words = query.strip().split()
    if len(words) >= 3:
        return " ".join(words[:-1]), words[-1]
    return query.strip(), ""


def _dedupe(results: list) -> list:
    seen: set = set()
    unique = []
    for r in results:
        domain = urlparse(r["url"]).netloc.lower().replace("www.", "")
        if domain and domain not in seen:
            seen.add(domain)
            unique.append(r)
    return unique


# ── Source 1: DuckDuckGo HTML ─────────────────────────────────────────────────

async def _search_duckduckgo(query: str, max_results: int = 30) -> list:
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://duckduckgo.com",
        "Referer": "https://duckduckgo.com/",
    }
    results = []

    async with httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True) as client:
        resp = None
        for attempt in range(3):
            try:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query, "b": "", "kl": "us-en"},
                )
            except httpx.TimeoutException:
                print(f"    ⚠️  DDG timeout (attempt {attempt+1})")
                continue
            except Exception as e:
                print(f"    ⚠️  DDG error: {type(e).__name__}: {e}")
                return results

            if resp.status_code == 200:
                break
            if resp.status_code == 202:
                wait = 5 + attempt * 5
                print(f"    ⏳ DDG rate-limit (202), waiting {wait}s…")
                await asyncio.sleep(wait)
                continue
            # Other error
            print(f"    ⚠️  DDG HTTP {resp.status_code}")
            return results

        if resp is None or resp.status_code != 200:
            print(f"    ⚠️  DDG failed after 3 attempts")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")

        for div in soup.find_all("div", class_=re.compile(r"\bresult\b")):
            if "result--more" in " ".join(div.get("class") or []):
                continue

            a_tag = div.find("a", class_="result__a") or div.find("a", href=True)
            if not a_tag:
                continue

            href = a_tag.get("href", "")
            if "duckduckgo.com/l/?" in href or href.startswith("//duckduckgo.com"):
                import urllib.parse as _up
                if href.startswith("//"):
                    href = "https:" + href
                qs = _up.parse_qs(_up.urlparse(href).query)
                href = qs.get("uddg", [""])[0]
                if href:
                    href = _up.unquote(href)

            if not href.startswith("http") or not _is_valid_url(href):
                continue

            title = a_tag.get_text(strip=True)
            snippet_el = div.find(class_=re.compile(r"result__snippet|result__body"))
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            results.append({
                "name": _extract_name(title, href),
                "url": href,
                "snippet": snippet[:500],
                "title": title[:300],
                "source": "duckduckgo",
            })
            if len(results) >= max_results:
                break

    return results


# ── Source 2: Bing HTML ───────────────────────────────────────────────────────

async def _search_bing(query: str, max_results: int = 30) -> list:
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    results = []
    seen_domains: set = set()

    async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
        for page in range(3):
            params = {"q": query, "first": str(page * 10 + 1), "count": "10"}
            try:
                resp = await client.get("https://www.bing.com/search", params=params)
            except httpx.TimeoutException:
                print(f"    ⚠️  Bing timeout (page {page+1})")
                break
            except Exception as e:
                print(f"    ⚠️  Bing error: {type(e).__name__}: {e}")
                break

            if resp.status_code != 200:
                print(f"    ⚠️  Bing HTTP {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Detect CAPTCHA / blocked page
            page_text = soup.get_text(separator=" ", strip=True).lower()
            if "captcha" in page_text or "unusual traffic" in page_text or "verify" in page_text[:200]:
                print(f"    ⚠️  Bing CAPTCHA/block detected on page {page+1}")
                break

            # Bing organic results are in <li class="b_algo">
            items = soup.find_all("li", class_="b_algo")
            if not items:
                # Try alternate selector
                items = soup.find_all(class_=re.compile(r"\bb_algo\b"))
            if not items:
                print(f"    ⚠️  Bing page {page+1}: 0 results parsed (possible block)")

            for li in items:
                a_tag = li.find("h2", recursive=True)
                if a_tag:
                    a_tag = a_tag.find("a", href=True)
                if not a_tag:
                    a_tag = li.find("a", href=True)
                if not a_tag:
                    continue

                href = a_tag.get("href", "")
                if not href.startswith("http") or not _is_valid_url(href):
                    continue

                domain = urlparse(href).netloc.lower().replace("www.", "")
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)

                title = a_tag.get_text(strip=True)
                snippet_el = li.find("p") or li.find(class_=re.compile(r"b_caption"))
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                results.append({
                    "name": _extract_name(title, href),
                    "url": href,
                    "snippet": snippet[:500],
                    "title": title[:300],
                    "source": "bing",
                })
                if len(results) >= max_results:
                    break

            if len(results) >= max_results:
                break

            await asyncio.sleep(random.uniform(1.5, 3.0))

    return results


# ── Source 3: SearXNG JSON API (free, open-source, no key) ───────────────────

async def _search_searxng(query: str, max_results: int = 30) -> list:
    """
    Try multiple public SearXNG instances. Returns on first success.
    """
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    results = []

    instances = random.sample(SEARXNG_INSTANCES, len(SEARXNG_INSTANCES))

    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
        for instance in instances:
            try:
                params = {
                    "q": query,
                    "format": "json",
                    "categories": "general",
                    "language": "en",
                }
                resp = await client.get(f"{instance}/search", params=params)

                if resp.status_code != 200:
                    print(f"    ⚠️  SearXNG {instance} → HTTP {resp.status_code}")
                    continue

                data = resp.json()
                search_results = data.get("results", [])

                for item in search_results:
                    href = item.get("url", "")
                    if not href.startswith("http") or not _is_valid_url(href):
                        continue
                    title = item.get("title", "")
                    snippet = item.get("content", "")

                    results.append({
                        "name": _extract_name(title, href),
                        "url": href,
                        "snippet": snippet[:500],
                        "title": title[:300],
                        "source": "searxng",
                    })
                    if len(results) >= max_results:
                        break

                if results:
                    print(f"    ✓ SearXNG ({instance}) → {len(results)} results")
                    return results
                else:
                    print(f"    ⚠️  SearXNG {instance} → 0 results")

            except httpx.TimeoutException:
                print(f"    ⚠️  SearXNG {instance} → timeout")
                continue
            except Exception as e:
                print(f"    ⚠️  SearXNG {instance} → {type(e).__name__}")
                continue

    return results


# ── Source 4: Brave Search HTML ───────────────────────────────────────────────

async def _search_brave(query: str, max_results: int = 30) -> list:
    """Scrape Brave Search HTML results (no API key required)."""
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    results = []

    async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
        try:
            params = {"q": query, "source": "web"}
            resp = await client.get("https://search.brave.com/search", params=params)
        except httpx.TimeoutException:
            print(f"    ⚠️  Brave timeout")
            return results
        except Exception as e:
            print(f"    ⚠️  Brave error: {type(e).__name__}: {e}")
            return results

        if resp.status_code != 200:
            print(f"    ⚠️  Brave HTTP {resp.status_code}")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")

        # Brave organic results
        for div in soup.find_all("div", class_=re.compile(r"snippet")):
            a_tag = div.find("a", href=True)
            if not a_tag:
                continue
            href = a_tag.get("href", "")
            if not href.startswith("http") or not _is_valid_url(href):
                continue

            title_el = div.find(class_=re.compile(r"title|heading")) or a_tag
            title = title_el.get_text(strip=True) if title_el else ""
            snippet_el = div.find(class_=re.compile(r"description|snippet-description"))
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            results.append({
                "name": _extract_name(title, href),
                "url": href,
                "snippet": snippet[:500],
                "title": title[:300],
                "source": "brave",
            })
            if len(results) >= max_results:
                break

    return results


# ── Public API ────────────────────────────────────────────────────────────────

async def search_google(query: str, max_pages: int = 3, headless: bool = True) -> list:
    """
    Search for businesses using DuckDuckGo → Brave → SearXNG → Bing (in order).
    Returns list of {name, url, snippet, title, page_num}.
    `max_pages` and `headless` kept for backward compatibility.
    """
    print(f"  🔍 Searching: {query}")
    max_results = max(max_pages * 10, 20)

    # --- 1. Try DuckDuckGo ---
    results = await _search_duckduckgo(query, max_results=max_results)
    if results:
        print(f"  ✅ DuckDuckGo: {len(results)} results")
    else:
        # --- 2. Try Brave (most reliable fallback) ---
        await asyncio.sleep(random.uniform(1.0, 2.0))
        results = await _search_brave(query, max_results=max_results)
        if results:
            print(f"  ✅ Brave: {len(results)} results")
        else:
            # --- 3. Try SearXNG ---
            await asyncio.sleep(random.uniform(1.0, 2.0))
            results = await _search_searxng(query, max_results=max_results)
            if results:
                print(f"  ✅ SearXNG: {len(results)} results")
            else:
                # --- 4. Try Bing (often JS-only, last resort) ---
                await asyncio.sleep(random.uniform(1.0, 2.0))
                results = await _search_bing(query, max_results=max_results)
                if results:
                    print(f"  ✅ Bing: {len(results)} results")
                else:
                    print(f"  ⚠️  All search sources returned 0 results for: {query}")

    unique = _dedupe(results)
    for r in unique:
        r["page_num"] = 1
    print(f"  ✅ {len(unique)} unique businesses found")
    return unique


# ── Scraper main ──────────────────────────────────────────────────────────────

async def main_scraper(queries, max_pages, headless):
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "scraped_businesses.json")
    all_results = []

    # Load existing so progress isn't lost on crash
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    all_results = existing
        except Exception:
            pass

    existing_urls = {r.get("url", "") for r in all_results}

    print("\n================================================")
    print("        LeadGen — Independent Scraper         ")
    print("================================================")
    print(f"  Queries  : {len(queries)}")
    print(f"  Max pages: {max_pages} per query")
    print()

    for i, query in enumerate(queries, 1):
        print(f"\n{'-' * 50}")
        print(f"  [{i}/{len(queries)}] \"{query}\"")
        print(f"{'-' * 50}")

        niche, location = parse_niche_location(query)
        results = await search_google(query, max_pages=max_pages, headless=headless)

        added = 0
        for r in results:
            if r.get("url") and r["url"] not in existing_urls:
                r["niche"] = niche
                r["location"] = location
                r["query"] = query
                all_results.append(r)
                existing_urls.add(r["url"])
                added += 1

        print(f"  ➕ {added} new businesses added (total: {len(all_results)})")

        # Save after every query
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        if i < len(queries):
            delay = random.uniform(4, 8)
            print(f"  💤 Waiting {delay:.1f}s…")
            await asyncio.sleep(delay)

    print(f"\n✅ Finished! Saved {len(all_results)} businesses to {output_file}")
    print("➡️  Run 'python process_urls.py' to extract emails and audit websites.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LeadGen — Search Scraper")
    ap.add_argument("--file", default="queriess.txt",
                    help="Queries file (default: queriess.txt)")
    ap.add_argument("--pages", type=int, default=3,
                    help="Result pages per query (default: 3)")
    ap.add_argument("--headed", action="store_true",
                    help="(Ignored — no browser used)")
    args = ap.parse_args()

    qfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.file)
    if not os.path.exists(qfile):
        print(f"❌ File not found: {qfile}")
        sys.exit(1)

    with open(qfile, "r", encoding="utf-8") as f:
        queries = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    if not queries:
        print("❌ No queries found.")
        sys.exit(1)

    asyncio.run(main_scraper(queries, args.pages, not args.headed))
