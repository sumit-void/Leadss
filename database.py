import sqlite3
import os
import re

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leadminer.db')

def init_db():
    """Initialize the SQLite database with the leads table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            website TEXT,
            category TEXT,
            rating REAL,
            total_reviews INTEGER,
            address TEXT,
            lat REAL,
            lng REAL,
            query TEXT,
            status TEXT DEFAULT 'New',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, phone)
        )
    ''')
    
    conn.commit()
    conn.close()

def clean_phone(phone):
    """Normalize phone numbers for better deduplication."""
    if not phone:
        return ""
    return re.sub(r'\D', '', phone)

def insert_lead(data: dict):
    """
    Insert a lead into the database. 
    Uses INSERT OR IGNORE to automatically deduplicate based on (name, phone).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clean phone for strict deduplication
    normalized_phone = clean_phone(data.get('phone', ''))
    
    # Try to extract numbers from rating/reviews if they are strings
    rating = data.get('rating', 0.0)
    try:
        rating = float(rating) if rating else 0.0
    except ValueError:
        rating = 0.0
        
    reviews = data.get('total_reviews', 0)
    try:
        reviews = int(str(reviews).replace(',', '')) if reviews else 0
    except ValueError:
        reviews = 0

    cursor.execute('''
        INSERT OR IGNORE INTO leads 
        (name, phone, email, website, category, rating, total_reviews, address, lat, lng, query)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name', ''),
        normalized_phone,
        data.get('email', ''),
        data.get('website', ''),
        data.get('category', ''),
        rating,
        reviews,
        data.get('address', ''),
        data.get('lat', None),
        data.get('lng', None),
        data.get('query', '')
    ))
    
    inserted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return inserted

def get_all_leads():
    """Retrieve all leads for the dashboard."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM leads ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_lead_status(lead_id: int, new_status: str):
    """Update the CRM status of a lead."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE leads SET status = ? WHERE id = ?', (new_status, lead_id))
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()
