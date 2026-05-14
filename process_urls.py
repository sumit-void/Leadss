"""
LeadGen — Process URLs (standalone)
Reads scraped_businesses.json (written by scraper.py) and
crawls / extracts emails / audits each site concurrently.

Usage:
  python scraper.py          # step 1 — collect URLs
  python process_urls.py     # step 2 — crawl & store results
"""

import asyncio
import argparse
import os
import sys
import time
import json

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from database import (
    generate_batch_id, insert_business, update_business,
    insert_website, insert_email, insert_audit, get_stats,
)
from crawler import crawl_website
from email_extractor import extract_emails
from auditor import audit_website


# ── Process a single business ─────────────────────────────────────────────────

async def process_one(url_data: dict, batch_id: str, stats: dict):
    """Crawl → extract emails → audit → store in DB."""
    biz_id = insert_business(url_data, batch_id)

    if biz_id is None:
        stats["dupes"] += 1
        return

    stats["new"] += 1
    name = url_data.get("name", "Unknown")
    url = url_data.get("url", "")

    # ── Crawl ──────────────────────────────────────────────────────────────────
    try:
        pages = await crawl_website(url)
    except Exception as e:
        print(f"    ⚠️  Crawl failed ({name}): {e}")
        return

    homepage = pages[0] if pages else None
    if not homepage or homepage.get("error"):
        err = homepage.get("error", "unknown") if homepage else "no data"
        print(f"    ⚠️  Unreachable: {url}  [{err}]")
        return

    # Save page metadata (without raw HTML)
    for page in pages:
        page_copy = {k: v for k, v in page.items() if k not in ("html", "error")}
        page_copy["business_id"] = biz_id
        try:
            insert_website(page_copy)
        except Exception:
            pass

    # ── Extract Emails ─────────────────────────────────────────────────────────
    all_emails: list = []
    for page in pages:
        if page.get("html"):
            emails = extract_emails(
                page["html"],
                page.get("url", url),
                page.get("page_type", "homepage"),
            )
            all_emails.extend(emails)

    seen: set = set()
    for em in all_emails:
        addr = em["email"]
        if addr not in seen:
            seen.add(addr)
            try:
                insert_email(
                    biz_id, addr, url,
                    em.get("method", "regex"),
                    em.get("confidence", 0.5),
                    em.get("is_generic", False),
                )
            except Exception:
                pass

    # ── Audit ──────────────────────────────────────────────────────────────────
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

    try:
        insert_audit(biz_id, audit)
        update_business(biz_id, lead_score=audit["total_score"], status="audited")
    except Exception:
        pass

    email_str = f" | ✉  {list(seen)[0]}" if seen else ""
    print(f"    ✓  {name}{email_str} | Score: {audit['total_score']}")
    stats["emails"] += len(seen)


# ── Concurrent worker ─────────────────────────────────────────────────────────

async def _worker(queue: asyncio.Queue, batch_id: str, stats: dict):
    while True:
        try:
            url_data = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        try:
            await process_one(url_data, batch_id, stats)
        except Exception as e:
            print(f"    ❌ Error ({url_data.get('name', '?')}): {e}")
        finally:
            queue.task_done()


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run_pipeline(businesses: list, concurrency: int):
    batch_id = generate_batch_id()

    print("\n================================================")
    print("        LeadGen — Concurrent Crawler          ")
    print("================================================")
    print(f"  Batch      : {batch_id}")
    print(f"  Businesses : {len(businesses)}")
    print(f"  Concurrency: {concurrency}")
    print()

    start = time.time()
    total_stats = {"new": 0, "dupes": 0, "emails": 0}

    queue: asyncio.Queue = asyncio.Queue()
    for b in businesses:
        queue.put_nowait(b)

    workers = [
        asyncio.create_task(_worker(queue, batch_id, total_stats))
        for _ in range(min(concurrency, len(businesses)))
    ]
    await queue.join()
    for w in workers:
        w.cancel()

    elapsed = time.strftime("%H:%M:%S", time.gmtime(time.time() - start))
    db_stats = get_stats()

    print(f"\n{'=' * 50}")
    print(f"  DONE — {batch_id}")
    print(f"  Time    : {elapsed}")
    print(f"  New     : {total_stats['new']} businesses")
    print(f"  Dupes   : {total_stats['dupes']} skipped")
    print(f"  Emails  : {total_stats['emails']} extracted")
    print(f"  Total DB: {db_stats['total']} businesses, {db_stats['with_email']} with email")
    print(f"{'=' * 50}")
    print(f"\n  ➡️  View leads: streamlit run app.py\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="LeadGen — Process URLs")
    ap.add_argument(
        "--file", default="scraped_businesses.json",
        help="Input JSON file (default: scraped_businesses.json)",
    )
    ap.add_argument(
        "--concurrency", type=int, default=5,
        help="Number of concurrent crawlers (default: 5)",
    )
    args = ap.parse_args()

    json_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.file)

    if not os.path.exists(json_file):
        print(f"❌ File not found: {json_file}")
        print("   Run 'python scraper.py' first to collect business URLs.")
        sys.exit(1)

    with open(json_file, "r", encoding="utf-8") as f:
        try:
            businesses = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in {json_file}: {e}")
            sys.exit(1)

    if not isinstance(businesses, list) or len(businesses) == 0:
        print(f"❌ No businesses found in {json_file}.")
        print("   Run 'python scraper.py' first.")
        sys.exit(1)

    # Filter out entries missing a URL
    businesses = [b for b in businesses if b.get("url")]
    if not businesses:
        print("❌ All entries are missing a 'url' field — cannot process.")
        sys.exit(1)

    print(f"  Loaded {len(businesses)} businesses from {args.file}")
    asyncio.run(run_pipeline(businesses, args.concurrency))


if __name__ == "__main__":
    main()
