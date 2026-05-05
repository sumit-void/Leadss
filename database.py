"""
LeadMiner Database — SQLite Backend
  - Stores leads with batch tracking
  - Each scraper run = unique batch_id
  - Automatic deduplication via (name, phone) UNIQUE constraint
"""

import sqlite3
import os
import re
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leadminer.db')


def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the SQLite database with the leads table."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            category TEXT,
            rating REAL,
            total_reviews INTEGER,
            address TEXT,
            lat REAL,
            lng REAL,
            query TEXT,
            batch_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, phone)
        )
    ''')

    # Add batch_id column if upgrading from old schema
    try:
        cursor.execute('ALTER TABLE leads ADD COLUMN batch_id TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()


def clean_phone(phone):
    """Normalize phone numbers for better deduplication."""
    if not phone:
        return ""
    return re.sub(r'\D', '', phone)


def generate_batch_id():
    """Generate a unique batch ID based on current timestamp."""
    return f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def insert_lead(data: dict, batch_id: str = None):
    """
    Insert a lead into the database.
    Uses INSERT OR IGNORE to automatically deduplicate based on (name, phone).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Clean phone for strict deduplication
    normalized_phone = clean_phone(data.get('phone', ''))

    # Parse rating
    rating = data.get('rating', 0.0)
    try:
        rating = float(rating) if rating else 0.0
    except ValueError:
        rating = 0.0

    # Parse reviews
    reviews = data.get('total_reviews', 0)
    try:
        reviews = int(str(reviews).replace(',', '')) if reviews else 0
    except ValueError:
        reviews = 0

    cursor.execute('''
        INSERT OR IGNORE INTO leads
        (name, phone, email, category, rating, total_reviews, address, lat, lng, query, batch_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name', ''),
        normalized_phone,
        data.get('email', ''),
        data.get('category', ''),
        rating,
        reviews,
        data.get('address', ''),
        data.get('lat', None),
        data.get('lng', None),
        data.get('query', ''),
        batch_id
    ))

    inserted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return inserted


def get_all_batches():
    """
    Returns list of dicts: [{"batch_id": "batch_20260505_...", "count": 42, "date": "..."}, ...]
    Ordered newest first.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            COALESCE(batch_id, 'Legacy') as batch_id,
            COUNT(*) as count,
            MIN(created_at) as first_scraped,
            MAX(created_at) as last_scraped
        FROM leads
        GROUP BY COALESCE(batch_id, 'Legacy')
        ORDER BY MAX(created_at) DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_leads_by_batch(batch_id: str = None):
    """
    Get leads for a specific batch. If batch_id is None, returns all leads.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if batch_id and batch_id != "All Batches":
        if batch_id == "Legacy":
            cursor.execute('SELECT * FROM leads WHERE batch_id IS NULL ORDER BY created_at DESC')
        else:
            cursor.execute('SELECT * FROM leads WHERE batch_id = ? ORDER BY created_at DESC', (batch_id,))
    else:
        cursor.execute('SELECT * FROM leads ORDER BY created_at DESC')

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_leads():
    """Retrieve all leads."""
    return get_leads_by_batch(None)


def get_total_lead_count():
    """Quick count of all leads."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM leads')
    count = cursor.fetchone()[0]
    conn.close()
    return count


# Initialize DB on import
init_db()
