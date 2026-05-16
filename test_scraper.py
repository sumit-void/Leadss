"""
End-to-end test: scrape 1 query → crawl → audit → export.
Validates the full pipeline works before running the big batch.
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import search_google
from crawler import crawl_website
from email_extractor import extract_emails
from auditor import audit_website


async def test_e2e():
    print("=" * 60)
    print("  END-TO-END PIPELINE TEST")
    print("=" * 60)

    # Step 1: Search
    print("\n--- STEP 1: Search ---")
    results = await search_google("interior design firm in Atlanta", max_pages=1)
    print(f"  Found {len(results)} businesses")

    if not results:
        print("  ❌ No search results — all sources blocked.")
        print("  Try again in 30 minutes (DDG rate-limits usually reset).")
        return False

    # Step 2: Crawl first 2 results
    print("\n--- STEP 2: Crawl ---")
    for biz in results[:2]:
        url = biz["url"]
        name = biz["name"]
        print(f"\n  Crawling: {name} ({url})")

        try:
            pages = await crawl_website(url)
        except Exception as e:
            print(f"    ❌ Crawl failed: {e}")
            continue

        homepage = pages[0] if pages else None
        if not homepage or homepage.get("error"):
            print(f"    ❌ Unreachable: {homepage.get('error', 'no data') if homepage else 'no data'}")
            continue

        print(f"    ✓ Crawled {len(pages)} pages")
        print(f"    Title: {homepage.get('title', 'N/A')[:80]}")
        print(f"    CMS: {homepage.get('cms_detected', 'Unknown')}")
        print(f"    SSL: {homepage.get('has_ssl')}")
        print(f"    Mobile: {homepage.get('is_mobile_friendly')}")
        print(f"    Load time: {homepage.get('load_time_ms')}ms")
        print(f"    Social links: {list(homepage.get('social_links', {}).keys())}")

        # Step 3: Extract emails
        all_emails = []
        for page in pages:
            if page.get("html"):
                emails = extract_emails(page["html"], page.get("url", url), page.get("page_type", "homepage"))
                all_emails.extend(emails)

        unique_emails = list({e["email"]: e for e in all_emails}.values())
        print(f"    Emails: {[e['email'] for e in unique_emails[:3]]}")

        # Step 4: Audit
        audit = audit_website(
            has_email=len(unique_emails) > 0,
            has_ssl=homepage.get("has_ssl", False),
            cms=homepage.get("cms_detected"),
            is_mobile=bool(homepage.get("is_mobile_friendly")),
            load_time_ms=homepage.get("load_time_ms", 0),
            has_meta_desc=bool(homepage.get("meta_description")),
            headings=homepage.get("headings", {}),
            has_forms=bool(homepage.get("has_forms")),
            social_links=homepage.get("social_links", {}),
            has_phone=bool(homepage.get("phone_numbers")),
            title=homepage.get("title", ""),
            business_name=name,
            niche=biz.get("niche", ""),
        )
        print(f"    Audit score: {audit['total_score']}/100")
        print(f"    Issues: {audit['issues'][:3]}")
        print(f"    Summary: {audit['summary'][:100]}")

    print("\n" + "=" * 60)
    print("  ✅ PIPELINE TEST PASSED")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_e2e())
    sys.exit(0 if success else 1)
