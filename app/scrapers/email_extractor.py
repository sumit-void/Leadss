"""
LeadGen Pro — Email Extractor
Multi-method email extraction: regex, mailto, schema markup, HTML parsing.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Email regex (RFC 5322 basic)
EMAIL_RE = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE,
)

# Emails to skip
SKIP_EMAILS = {
    "noreply", "no-reply", "donotreply", "mailer-daemon", "postmaster",
    "webmaster", "hostmaster", "abuse", "root", "admin", "administrator",
    "example", "test", "demo", "sample", "email", "your", "name",
    "support@wix.com", "support@squarespace.com", "support@wordpress.com",
}

SKIP_DOMAINS = {
    "example.com", "test.com", "email.com", "domain.com", "company.com",
    "yoursite.com", "yourdomain.com", "website.com", "sentry.io",
    "wixpress.com", "googleapis.com", "gstatic.com", "google.com",
    "w3.org", "schema.org", "gravatar.com", "wordpress.org",
}

GENERIC_PREFIXES = {
    "info", "contact", "hello", "hi", "hey", "support", "help",
    "sales", "enquiry", "inquiry", "office", "admin", "general",
    "team", "mail", "email", "service", "services",
}


@dataclass
class ExtractedEmail:
    """An extracted email with metadata."""
    email: str
    source_url: str = ""
    method: str = "regex"
    confidence: float = 0.5
    is_generic: bool = False


def _is_valid_email(email: str) -> bool:
    """Basic email validation."""
    email = email.lower().strip()

    if len(email) < 6 or len(email) > 254:
        return False

    # Check local part
    local = email.split("@")[0]
    if local.lower() in SKIP_EMAILS:
        return False

    # Check domain
    domain = email.split("@")[1]
    if domain in SKIP_DOMAINS:
        return False

    # Must have valid TLD
    tld = domain.split(".")[-1]
    if len(tld) < 2 or len(tld) > 10:
        return False

    # No consecutive dots
    if ".." in email:
        return False

    # No image file extensions as "emails"
    if any(email.endswith(ext) for ext in [".png", ".jpg", ".gif", ".svg", ".css", ".js"]):
        return False

    return True


def _is_generic(email: str) -> bool:
    """Check if email is a generic address."""
    local = email.lower().split("@")[0]
    return local in GENERIC_PREFIXES


def _assign_confidence(method: str, page_type: str = "homepage") -> float:
    """Assign confidence score based on extraction method and page type."""
    base_scores = {
        "mailto": 0.95,
        "schema": 0.90,
        "html_parse": 0.85,
        "regex": 0.75,
        "js_render": 0.60,
    }
    score = base_scores.get(method, 0.5)

    # Boost for contact page
    if page_type == "contact":
        score = min(score + 0.05, 1.0)

    return round(score, 2)


def extract_emails_from_html(html: str, source_url: str = "", page_type: str = "homepage") -> list[ExtractedEmail]:
    """
    Extract emails from HTML using multiple methods.
    Returns deduplicated list sorted by confidence (highest first).
    """
    found: dict[str, ExtractedEmail] = {}

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # ── Method 1: mailto links (highest confidence) ────
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip().lower()
            if EMAIL_RE.match(email) and _is_valid_email(email):
                if email not in found:
                    found[email] = ExtractedEmail(
                        email=email,
                        source_url=source_url,
                        method="mailto",
                        confidence=_assign_confidence("mailto", page_type),
                        is_generic=_is_generic(email),
                    )

    # ── Method 2: Schema.org / JSON-LD ─────────────────
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            # Handle single object or list
            items = data if isinstance(data, list) else [data]
            for item in items:
                for key in ["email", "contactPoint"]:
                    val = item.get(key)
                    if isinstance(val, str) and "@" in val:
                        email = val.replace("mailto:", "").strip().lower()
                        if EMAIL_RE.match(email) and _is_valid_email(email) and email not in found:
                            found[email] = ExtractedEmail(
                                email=email, source_url=source_url,
                                method="schema",
                                confidence=_assign_confidence("schema", page_type),
                                is_generic=_is_generic(email),
                            )
                    elif isinstance(val, dict):
                        cp_email = val.get("email", "")
                        if cp_email and "@" in cp_email:
                            email = cp_email.replace("mailto:", "").strip().lower()
                            if EMAIL_RE.match(email) and _is_valid_email(email) and email not in found:
                                found[email] = ExtractedEmail(
                                    email=email, source_url=source_url,
                                    method="schema",
                                    confidence=_assign_confidence("schema", page_type),
                                    is_generic=_is_generic(email),
                                )
        except Exception:
            pass

    # ── Method 3: HTML context parsing ─────────────────
    # Look for emails near "email", "contact", "reach" text
    for tag in soup.find_all(["p", "span", "div", "li", "td", "a"]):
        text = tag.get_text(separator=" ")
        if "@" in text:
            for match in EMAIL_RE.finditer(text):
                email = match.group().lower()
                if _is_valid_email(email) and email not in found:
                    found[email] = ExtractedEmail(
                        email=email, source_url=source_url,
                        method="html_parse",
                        confidence=_assign_confidence("html_parse", page_type),
                        is_generic=_is_generic(email),
                    )

    # ── Method 4: Full-text regex scan ─────────────────
    full_text = soup.get_text(separator=" ") if soup else html
    for match in EMAIL_RE.finditer(full_text):
        email = match.group().lower()
        if _is_valid_email(email) and email not in found:
            found[email] = ExtractedEmail(
                email=email, source_url=source_url,
                method="regex",
                confidence=_assign_confidence("regex", page_type),
                is_generic=_is_generic(email),
            )

    # Sort by confidence descending
    results = sorted(found.values(), key=lambda e: e.confidence, reverse=True)
    return results[:20]  # Cap at 20 per page
