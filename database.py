"""
LeadGen — SQLite Database
All tables in one file. Zero setup needed.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leadgen.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            website_url TEXT UNIQUE,
            snippet TEXT,
            title TEXT,
            source_query TEXT,
            niche TEXT,
            location TEXT,
            status TEXT DEFAULT 'discovered',
            lead_score REAL DEFAULT 0,
            batch_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS websites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER REFERENCES businesses(id),
            url TEXT,
            page_type TEXT DEFAULT 'homepage',
            title TEXT,
            meta_description TEXT,
            headings TEXT,
            has_ssl INTEGER DEFAULT 0,
            cms_detected TEXT,
            has_forms INTEGER DEFAULT 0,
            social_links TEXT,
            phone_numbers TEXT,
            load_time_ms INTEGER DEFAULT 0,
            is_mobile_friendly INTEGER DEFAULT 0,
            status_code INTEGER,
            crawled_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER REFERENCES businesses(id),
            email TEXT NOT NULL,
            source_url TEXT,
            extraction_method TEXT,
            confidence REAL DEFAULT 0.5,
            is_generic INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(business_id, email)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER REFERENCES businesses(id),
            overall_score REAL,
            design_score REAL,
            seo_score REAL,
            mobile_score REAL,
            speed_score REAL,
            trust_score REAL,
            cta_score REAL,
            issues TEXT,
            summary TEXT,
            outreach_opener TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


def generate_batch_id():
    return f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def insert_business(data: dict, batch_id: str = None) -> int | None:
    """Insert business. Returns id if new, None if duplicate."""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO businesses
               (name, website_url, snippet, title, source_query, niche, location, batch_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data.get("name", ""), data.get("url", ""), data.get("snippet", ""),
             data.get("title", ""), data.get("query", ""),
             data.get("niche", ""), data.get("location", ""), batch_id),
        )
        conn.commit()
        if conn.total_changes > 0:
            row = conn.execute(
                "SELECT id FROM businesses WHERE website_url = ?", (data["url"],)
            ).fetchone()
            return row["id"] if row else None
        return None
    finally:
        conn.close()


def update_business(biz_id: int, **kwargs):
    conn = get_conn()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [biz_id]
    conn.execute(f"UPDATE businesses SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def insert_website(data: dict):
    conn = get_conn()
    conn.execute(
        """INSERT INTO websites
           (business_id, url, page_type, title, meta_description, headings,
            has_ssl, cms_detected, has_forms, social_links, phone_numbers,
            load_time_ms, is_mobile_friendly, status_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data["business_id"], data.get("url", ""), data.get("page_type", "homepage"),
         data.get("title", ""), data.get("meta_description", ""),
         str(data.get("headings", {})), data.get("has_ssl", 0),
         data.get("cms_detected"), data.get("has_forms", 0),
         str(data.get("social_links", {})), str(data.get("phone_numbers", [])),
         data.get("load_time_ms", 0), data.get("is_mobile_friendly", 0),
         data.get("status_code", 0)),
    )
    conn.commit()
    conn.close()


def insert_email(business_id: int, email: str, source_url: str = "",
                 method: str = "regex", confidence: float = 0.5, is_generic: bool = False):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO emails
               (business_id, email, source_url, extraction_method, confidence, is_generic)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (business_id, email.lower().strip(), source_url, method, confidence, int(is_generic)),
        )
        conn.commit()
    finally:
        conn.close()


def insert_audit(business_id: int, data: dict):
    conn = get_conn()
    conn.execute(
        """INSERT INTO audits
           (business_id, overall_score, design_score, seo_score, mobile_score,
            speed_score, trust_score, cta_score, issues, summary, outreach_opener)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (business_id, data.get("total_score", 0), data.get("design_score", 5),
         data.get("seo_score", 5), data.get("mobile_score", 5),
         data.get("speed_score", 5), data.get("trust_score", 5),
         data.get("cta_score", 5), str(data.get("issues", [])),
         data.get("summary", ""), data.get("outreach_opener", "")),
    )
    conn.commit()
    conn.close()


def get_all_leads(batch_id=None, min_score=None, has_email=None, niche=None):
    conn = get_conn()
    sql = """
        SELECT b.*,
               GROUP_CONCAT(DISTINCT e.email) as all_emails,
               COUNT(DISTINCT e.id) as email_count,
               a.overall_score as audit_score,
               a.summary as audit_summary,
               a.outreach_opener
        FROM businesses b
        LEFT JOIN emails e ON e.business_id = b.id
        LEFT JOIN audits a ON a.business_id = b.id
        WHERE 1=1
    """
    params = []

    if batch_id and batch_id != "All":
        sql += " AND b.batch_id = ?"
        params.append(batch_id)
    if min_score is not None:
        sql += " AND b.lead_score >= ?"
        params.append(min_score)
    if niche:
        sql += " AND b.niche LIKE ?"
        params.append(f"%{niche}%")

    sql += " GROUP BY b.id ORDER BY b.lead_score DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = [dict(r) for r in rows]
    if has_email:
        results = [r for r in results if r.get("email_count", 0) > 0]
    return results


def get_batches():
    conn = get_conn()
    rows = conn.execute("""
        SELECT batch_id, COUNT(*) as count, MIN(created_at) as started
        FROM businesses
        WHERE batch_id IS NOT NULL
        GROUP BY batch_id
        ORDER BY MAX(created_at) DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
    with_email = conn.execute("""
        SELECT COUNT(DISTINCT business_id) FROM emails
    """).fetchone()[0]
    audited = conn.execute("""
        SELECT COUNT(DISTINCT business_id) FROM audits
    """).fetchone()[0]
    avg_score = conn.execute("""
        SELECT COALESCE(AVG(lead_score), 0) FROM businesses WHERE lead_score > 0
    """).fetchone()[0]
    conn.close()
    return {"total": total, "with_email": with_email, "audited": audited, "avg_score": round(avg_score, 1)}


# Auto-init on import
init_db()
