import sqlite3
import pandas as pd

conn = sqlite3.connect('leadgen.db')
conn.row_factory = sqlite3.Row

cursor = conn.execute("SELECT COUNT(*) as cnt FROM businesses WHERE status='audited'")
row = cursor.fetchone()
print(f"Audited businesses: {row['cnt']}")

cursor = conn.execute("SELECT COUNT(*) as cnt FROM businesses")
row = cursor.fetchone()
print(f"Total businesses: {row['cnt']}")

conn.close()
