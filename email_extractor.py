"""
LeadGen — Email Extractor
Extracts emails from HTML using 4 methods: mailto, schema, HTML context, regex.
"""

import re
import json
import logging

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', re.I)

SKIP_LOCAL = {
    "noreply", "no-reply", "donotreply", "postmaster", "webmaster",
    "abuse", "root", "example", "test", "demo", "your", "name", "email",
}

SKIP_DOMAIN = {
    "example.com", "test.com", "domain.com", "company.com", "yoursite.com",
    "wixpress.com", "googleapis.com", "gstatic.com", "google.com",
    "w3.org", "schema.org", "gravatar.com", "wordpress.org", "sentry.io",
}

GENERIC_PREFIX = {
    "info", "contact", "hello", "hi", "support", "help", "sales",
    "enquiry", "inquiry", "office", "admin", "general", "team", "mail",
}


def _valid(email):
    e = email.lower().strip()
    if len(e) < 6 or len(e) > 254:
        return False
    local, domain = e.split("@", 1)
    if local in SKIP_LOCAL or domain in SKIP_DOMAIN:
        return False
    if ".." in e:
        return False
    if any(e.endswith(x) for x in [".png", ".jpg", ".gif", ".svg", ".css", ".js"]):
        return False
    tld = domain.split(".")[-1]
    if len(tld) < 2 or len(tld) > 10:
        return False
    return True


def extract_emails(html, source_url="", page_type="homepage"):
    """
    Extract emails from HTML. Returns list of dicts:
    [{email, method, confidence, is_generic}, ...]
    """
    from bs4 import BeautifulSoup
    found = {}

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # 1. Mailto links (best)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip().lower()
            if EMAIL_RE.match(email) and _valid(email) and email not in found:
                conf = 0.95 if page_type == "contact" else 0.90
                found[email] = {
                    "email": email, "method": "mailto",
                    "confidence": conf, "is_generic": email.split("@")[0] in GENERIC_PREFIX,
                }

    # 2. Schema / JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                for key in ["email", "contactPoint"]:
                    val = item.get(key)
                    if isinstance(val, str) and "@" in val:
                        email = val.replace("mailto:", "").strip().lower()
                        if EMAIL_RE.match(email) and _valid(email) and email not in found:
                            found[email] = {
                                "email": email, "method": "schema",
                                "confidence": 0.90, "is_generic": email.split("@")[0] in GENERIC_PREFIX,
                            }
                    elif isinstance(val, dict) and val.get("email"):
                        email = val["email"].replace("mailto:", "").strip().lower()
                        if EMAIL_RE.match(email) and _valid(email) and email not in found:
                            found[email] = {
                                "email": email, "method": "schema",
                                "confidence": 0.90, "is_generic": email.split("@")[0] in GENERIC_PREFIX,
                            }
        except Exception:
            pass

    # 3. HTML tags with @
    for tag in soup.find_all(["p", "span", "div", "li", "td", "a"]):
        text = tag.get_text(separator=" ")
        if "@" in text:
            for m in EMAIL_RE.finditer(text):
                email = m.group().lower()
                if _valid(email) and email not in found:
                    conf = 0.85 if page_type == "contact" else 0.75
                    found[email] = {
                        "email": email, "method": "html_parse",
                        "confidence": conf, "is_generic": email.split("@")[0] in GENERIC_PREFIX,
                    }

    # 4. Full text regex
    full_text = soup.get_text(separator=" ") if soup else html
    for m in EMAIL_RE.finditer(full_text):
        email = m.group().lower()
        if _valid(email) and email not in found:
            conf = 0.70 if page_type == "contact" else 0.60
            found[email] = {
                "email": email, "method": "regex",
                "confidence": conf, "is_generic": email.split("@")[0] in GENERIC_PREFIX,
            }

    return sorted(found.values(), key=lambda x: x["confidence"], reverse=True)[:15]
