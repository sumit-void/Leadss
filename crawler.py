"""
LeadGen — Website Crawler
Crawls homepage + contact/about pages. Detects CMS, SSL, emails, phones.
Pure httpx — no browser needed.
"""

import asyncio
import hashlib
import re
import time
import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CMS_SIGNS = {
    "wordpress": ["wp-content", "wp-includes", 'content="WordPress'],
    "shopify": ["cdn.shopify.com", "myshopify.com"],
    "wix": ["wix.com", "parastorage.com"],
    "squarespace": ["squarespace.com", "sqsp.net"],
    "webflow": ["webflow.io", "assets.website-files.com"],
}

SOCIAL_RE = {
    "facebook": r"facebook\.com/",
    "twitter": r"(?:twitter|x)\.com/",
    "instagram": r"instagram\.com/",
    "linkedin": r"linkedin\.com/",
    "youtube": r"youtube\.com/",
}

PHONE_RE = re.compile(
    r'(?:\+?\d{1,4}[\s.-]?)?(?:\(?\d{1,5}\)?[\s.-]?)?\d{2,5}[\s.-]?\d{2,5}[\s.-]?\d{0,5}'
)

CONTACT_WORDS = ["/contact", "/contact-us", "/get-in-touch"]
ABOUT_WORDS = ["/about", "/about-us", "/who-we-are"]
SERVICES_WORDS = ["/services", "/our-services", "/what-we-do"]


def _detect_cms(html):
    h = html.lower()
    for cms, signs in CMS_SIGNS.items():
        for s in signs:
            if s.lower() in h:
                return cms
    return None


def _get_headings(soup):
    out = {}
    for lvl in range(1, 4):
        tag = f"h{lvl}"
        found = soup.find_all(tag)
        if found:
            out[tag] = [h.get_text(strip=True)[:150] for h in found[:5]]
    return out


def _get_socials(soup):
    links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        for platform, pattern in SOCIAL_RE.items():
            if re.search(pattern, href) and platform not in links:
                links[platform] = a["href"]
    return links


def _get_phones(text):
    phones = []
    for m in PHONE_RE.finditer(text):
        p = m.group().strip()
        digits = re.sub(r'\D', '', p)
        if 7 <= len(digits) <= 15:
            phones.append(p)
    return list(dict.fromkeys(phones))[:5]


def _find_pages(soup, base_url):
    pages = {}
    domain = urlparse(base_url).netloc

    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"])
        if urlparse(full).netloc != domain:
            continue
        path = urlparse(full).path.lower().rstrip("/")
        txt = a.get_text(strip=True).lower()

        if "contact" not in pages:
            if any(p in path for p in CONTACT_WORDS) or "contact" in txt:
                pages["contact"] = full
        if "about" not in pages:
            if any(p in path for p in ABOUT_WORDS) or "about" in txt:
                pages["about"] = full
        if "services" not in pages:
            if any(p in path for p in SERVICES_WORDS) or "service" in txt:
                pages["services"] = full
    return pages


async def crawl_page(client, url, page_type="homepage"):
    """Crawl one page, return dict of extracted data."""
    data = {
        "url": url, "page_type": page_type, "title": "", "meta_description": "",
        "headings": {}, "has_ssl": url.startswith("https"), "cms_detected": None,
        "has_forms": 0, "social_links": {}, "phone_numbers": [],
        "load_time_ms": 0, "is_mobile_friendly": 0, "status_code": 0,
        "html": "", "error": None,
    }

    try:
        t0 = time.monotonic()
        resp = await client.get(url, follow_redirects=True, timeout=15.0)
        data["load_time_ms"] = int((time.monotonic() - t0) * 1000)
        data["status_code"] = resp.status_code

        if resp.status_code != 200:
            data["error"] = f"HTTP {resp.status_code}"
            return data

        html = resp.text
        data["html"] = html
        soup = BeautifulSoup(html, "lxml")

        # Title
        t = soup.find("title")
        if t:
            data["title"] = t.get_text(strip=True)[:300]

        # Meta desc
        m = soup.find("meta", attrs={"name": "description"})
        if m and m.get("content"):
            data["meta_description"] = m["content"][:500]

        # Headings
        data["headings"] = _get_headings(soup)

        # CMS
        data["cms_detected"] = _detect_cms(html)

        # Forms
        data["has_forms"] = 1 if soup.find("form") else 0

        # Social
        data["social_links"] = _get_socials(soup)

        # Phones
        data["phone_numbers"] = _get_phones(soup.get_text(separator=" "))

        # Mobile
        vp = soup.find("meta", attrs={"name": "viewport"})
        if vp and vp.get("content") and "width=device-width" in vp["content"].lower():
            data["is_mobile_friendly"] = 1

    except httpx.TimeoutException:
        data["error"] = "Timeout"
    except Exception as e:
        data["error"] = str(e)[:100]

    return data


async def crawl_website(url):
    """Crawl homepage + internal pages. Returns list of page data dicts."""
    results = []

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        # Homepage
        home = await crawl_page(client, url, "homepage")
        results.append(home)

        if home["error"] or not home["html"]:
            return results

        # Find internal pages
        soup = BeautifulSoup(home["html"], "lxml")
        pages = _find_pages(soup, url)

        # Crawl them
        for ptype, purl in pages.items():
            await asyncio.sleep(1)  # Polite delay
            page_data = await crawl_page(client, purl, ptype)
            results.append(page_data)

    return results
