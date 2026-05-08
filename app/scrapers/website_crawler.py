"""
LeadGen Pro — Website Crawler
Async crawler that extracts page data, detects CMS, SSL, mobile-friendliness.
Uses httpx for speed.
"""

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CONTACT_PATTERNS = ["/contact", "/contact-us", "/contactus", "/get-in-touch"]
ABOUT_PATTERNS = ["/about", "/about-us", "/aboutus", "/who-we-are", "/our-story"]
SERVICES_PATTERNS = ["/services", "/our-services", "/what-we-do", "/solutions"]

SOCIAL_PATTERNS = {
    "facebook": r"facebook\.com/",
    "twitter": r"(?:twitter|x)\.com/",
    "instagram": r"instagram\.com/",
    "linkedin": r"linkedin\.com/",
    "youtube": r"youtube\.com/",
    "tiktok": r"tiktok\.com/",
}

CMS_SIGNATURES = {
    "wordpress": ["wp-content", "wp-includes", 'content="WordPress'],
    "shopify": ["cdn.shopify.com", "myshopify.com"],
    "wix": ["wix.com", "parastorage.com"],
    "squarespace": ["squarespace.com", "sqsp.net"],
    "webflow": ["webflow.io", "assets.website-files.com"],
}

PHONE_RE = re.compile(
    r'(?:\+?\d{1,4}[\s.-]?)?(?:\(?\d{1,5}\)?[\s.-]?)?\d{2,5}[\s.-]?\d{2,5}[\s.-]?\d{0,5}'
)


@dataclass
class CrawlResult:
    """Result of crawling a single page."""
    url: str
    page_type: str = "homepage"
    title: str = ""
    meta_description: str = ""
    headings: dict = field(default_factory=dict)
    has_ssl: bool = False
    cms_detected: Optional[str] = None
    has_forms: bool = False
    social_links: dict = field(default_factory=dict)
    phone_numbers: list = field(default_factory=list)
    emails_found: list = field(default_factory=list)
    load_time_ms: int = 0
    is_mobile_friendly: bool = False
    status_code: int = 0
    raw_html_hash: str = ""
    error: Optional[str] = None


def _detect_cms(html: str) -> Optional[str]:
    html_lower = html.lower()
    for cms, patterns in CMS_SIGNATURES.items():
        for pattern in patterns:
            if pattern.lower() in html_lower:
                return cms
    return None


def _check_mobile_friendly(soup: BeautifulSoup) -> bool:
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if viewport and viewport.get("content"):
        if "width=device-width" in viewport["content"].lower():
            return True
    html = str(soup)
    for indicator in ["bootstrap", "foundation", "responsive"]:
        if indicator in html.lower():
            return True
    return False


def _extract_headings(soup: BeautifulSoup) -> dict:
    headings = {}
    for level in range(1, 7):
        tag = f"h{level}"
        found = soup.find_all(tag)
        if found:
            headings[tag] = [h.get_text(strip=True)[:200] for h in found[:10]]
    return headings


def _extract_social_links(soup: BeautifulSoup) -> dict:
    social = {}
    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        for platform, pattern in SOCIAL_PATTERNS.items():
            if re.search(pattern, href) and platform not in social:
                social[platform] = link["href"]
    return social


def _extract_phones(text: str) -> list[str]:
    phones = []
    for match in PHONE_RE.finditer(text):
        phone = match.group().strip()
        digits = re.sub(r'\D', '', phone)
        if 7 <= len(digits) <= 15:
            phones.append(phone)
    return list(dict.fromkeys(phones))[:10]


def _find_internal_pages(soup: BeautifulSoup, base_url: str) -> dict[str, str]:
    pages = {}
    base_domain = urlparse(base_url).netloc

    for link in soup.find_all("a", href=True):
        href = link["href"]
        full_url = urljoin(base_url, href)
        if urlparse(full_url).netloc != base_domain:
            continue

        path = urlparse(full_url).path.lower().rstrip("/")
        link_text = link.get_text(strip=True).lower()

        if "contact" not in pages:
            if any(p in path for p in CONTACT_PATTERNS) or "contact" in link_text:
                pages["contact"] = full_url
        if "about" not in pages:
            if any(p in path for p in ABOUT_PATTERNS) or "about" in link_text:
                pages["about"] = full_url
        if "services" not in pages:
            if any(p in path for p in SERVICES_PATTERNS) or "service" in link_text:
                pages["services"] = full_url

    return pages


async def _crawl_page(client: httpx.AsyncClient, url: str, page_type: str = "homepage") -> CrawlResult:
    result = CrawlResult(url=url, page_type=page_type)
    result.has_ssl = url.lower().startswith("https")

    try:
        start = time.monotonic()
        response = await client.get(url, follow_redirects=True, timeout=20.0)
        result.load_time_ms = int((time.monotonic() - start) * 1000)
        result.status_code = response.status_code

        if response.status_code != 200:
            result.error = f"HTTP {response.status_code}"
            return result

        html = response.text
        result.raw_html_hash = hashlib.sha256(html.encode()).hexdigest()[:16]
        soup = BeautifulSoup(html, "lxml")

        title_tag = soup.find("title")
        if title_tag:
            result.title = title_tag.get_text(strip=True)[:500]

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            result.meta_description = meta_desc["content"][:1000]

        result.headings = _extract_headings(soup)
        result.cms_detected = _detect_cms(html)
        result.has_forms = len(soup.find_all("form")) > 0
        result.social_links = _extract_social_links(soup)

        page_text = soup.get_text(separator=" ")
        result.phone_numbers = _extract_phones(page_text)
        result.is_mobile_friendly = _check_mobile_friendly(soup)

        from app.scrapers.email_extractor import extract_emails_from_html
        result.emails_found = extract_emails_from_html(html, url, page_type)

    except httpx.TimeoutException:
        result.error = "Timeout"
        logger.warning(f"Timeout crawling: {url}")
    except Exception as e:
        result.error = str(e)[:200]
        logger.error(f"Error crawling {url}: {e}")

    return result


async def crawl_website(url: str, concurrency: int = 3) -> list[CrawlResult]:
    """Crawl a website: homepage + contact/about/services pages."""
    results = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # 1. Crawl homepage
        logger.info(f"Crawling homepage: {url}")
        homepage_result = await _crawl_page(client, url, "homepage")
        results.append(homepage_result)

        if homepage_result.error:
            return results

        # 2. Discover internal pages
        html = (await client.get(url, follow_redirects=True, timeout=20.0)).text
        soup = BeautifulSoup(html, "lxml")
        internal_pages = _find_internal_pages(soup, url)

        # 3. Crawl discovered pages
        if internal_pages:
            sem = asyncio.Semaphore(concurrency)

            async def crawl_with_sem(page_url, page_type):
                async with sem:
                    await asyncio.sleep(1)
                    return await _crawl_page(client, page_url, page_type)

            tasks = [crawl_with_sem(pu, pt) for pt, pu in internal_pages.items()]
            sub_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in sub_results:
                if isinstance(r, CrawlResult):
                    results.append(r)

    logger.info(f"Crawled {len(results)} pages for {url}")
    return results
