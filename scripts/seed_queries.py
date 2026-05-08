"""
Seed search queries from queries.txt file.
Run: python -m scripts.seed_queries
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.search_worker import search_and_discover
from datetime import datetime, timezone


def main():
    queries_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "queriess.txt",
    )

    if not os.path.exists(queries_file):
        print(f"File not found: {queries_file}")
        return

    with open(queries_file, "r", encoding="utf-8") as f:
        queries = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    if not queries:
        print("No queries found.")
        return

    batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    print(f"Enqueueing {len(queries)} search queries (batch: {batch_id})...")

    for i, q in enumerate(queries, 1):
        search_and_discover.delay(q, max_pages=3, batch_id=batch_id)
        print(f"  [{i}/{len(queries)}] Enqueued: {q}")

    print(f"\nDone! All {len(queries)} queries enqueued.")
    print("Monitor progress: docker-compose logs -f worker-search")


if __name__ == "__main__":
    main()
