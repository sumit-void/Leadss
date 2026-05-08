"""
LeadGen — Main Runner
One command to run the entire pipeline:
  python run.py

That's it. No Docker, no setup, no config files.
"""

import asyncio
import argparse
import os
import sys
import time

from database import (
    generate_batch_id, insert_business, update_business,
    insert_website, insert_email, insert_audit, get_stats,
)
from scraper import search_google, parse_niche_location
from crawler import crawl_website
from email_extractor import extract_emails
from auditor import audit_website


async def process_one(url_data, batch_id, stats):
    """Process a single business: crawl → extract emails → audit."""
    biz_id = insert_business(url_data, batch_id)

    if biz_id is None:
        stats["dupes"] += 1
        return

    stats["new"] += 1
    name = url_data["name"]
    url = url_data["url"]

    # ── Crawl ──────────────────────────────────────
    try:
        pages = await crawl_website(url)
    except Exception as e:
        print(f"    ⚠️ Crawl failed for {name}: {e}")
        return

    homepage = pages[0] if pages else None
    if not homepage or homepage.get("error"):
        print(f"    ⚠️ Can't reach {url}")
        return

    # Store crawled pages
    for page in pages:
        page_copy = dict(page)
        page_copy["business_id"] = biz_id
        page_copy.pop("html", None)
        page_copy.pop("error", None)
        insert_website(page_copy)

    # ── Extract Emails ─────────────────────────────
    all_emails = []
    for page in pages:
        if page.get("html"):
            emails = extract_emails(page["html"], page["url"], page.get("page_type", "homepage"))
            all_emails.extend(emails)

    # Dedupe
    seen = set()
    for em in all_emails:
        if em["email"] not in seen:
            seen.add(em["email"])
            insert_email(
                biz_id, em["email"], url,
                em["method"], em["confidence"], em.get("is_generic", False),
            )

    # ── Audit ──────────────────────────────────────
    audit = audit_website(
        has_email=len(seen) > 0,
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
        niche=url_data.get("niche", ""),
    )

    insert_audit(biz_id, audit)
    update_business(biz_id, lead_score=audit["total_score"], status="audited")

    email_str = f" | ✉ {list(seen)[0]}" if seen else ""
    score_str = f" | Score: {audit['total_score']}"
    print(f"    ✓ {name}{email_str}{score_str}")
    stats["emails"] += len(seen)


async def run_pipeline(queries, max_pages, headless, max_per_query):
    batch_id = generate_batch_id()

    print("\n╔══════════════════════════════════════════════╗")
    print("║        LeadGen — Email Scraper               ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"  Batch    : {batch_id}")
    print(f"  Queries  : {len(queries)}")
    print(f"  Max pages: {max_pages} per query")
    print()

    start = time.time()
    total_stats = {"new": 0, "dupes": 0, "emails": 0}

    for i, query in enumerate(queries, 1):
        print(f"\n{'━' * 50}")
        print(f"  [{i}/{len(queries)}] \"{query}\"")
        print(f"{'━' * 50}")

        niche, location = parse_niche_location(query)

        # Search Google
        results = await search_google(query, max_pages=max_pages, headless=headless)

        if not results:
            print("  No results found.")
            continue

        # Limit per query
        results = results[:max_per_query]

        # Add niche/location
        for r in results:
            r["niche"] = niche
            r["location"] = location
            r["query"] = query

        # Process each business
        for r in results:
            try:
                await process_one(r, batch_id, total_stats)
            except Exception as e:
                print(f"    ❌ Error: {e}")

    elapsed = time.strftime("%H:%M:%S", time.gmtime(time.time() - start))
    db_stats = get_stats()

    print(f"\n{'═' * 50}")
    print(f"  📊 DONE — {batch_id}")
    print(f"  Time    : {elapsed}")
    print(f"  New     : {total_stats['new']} businesses")
    print(f"  Dupes   : {total_stats['dupes']} skipped")
    print(f"  Emails  : {total_stats['emails']} extracted")
    print(f"  Total DB: {db_stats['total']} businesses, {db_stats['with_email']} with email")
    print(f"{'═' * 50}")
    print(f"\n  ➡️  View leads: streamlit run app.py\n")


def main():
    ap = argparse.ArgumentParser(description="LeadGen — Email Scraper")
    ap.add_argument("--file", default="queriess.txt", help="Queries file (default: queriess.txt)")
    ap.add_argument("--pages", type=int, default=2, help="Google pages per query (default: 2)")
    ap.add_argument("--max", type=int, default=30, help="Max businesses per query (default: 30)")
    ap.add_argument("--headed", action="store_true", help="Show browser window")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        queries = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    if not queries:
        print("❌ No queries found.")
        sys.exit(1)

    asyncio.run(run_pipeline(queries, args.pages, not args.headed, args.max))


if __name__ == "__main__":
    main()
