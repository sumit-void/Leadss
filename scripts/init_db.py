"""
Initialize the database — creates all tables.
Run: python -m scripts.init_db
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import create_tables_sync, Base, get_sync_engine
import app.models  # noqa: F401 — register all models


def main():
    print("Creating database tables...")
    create_tables_sync()
    print("Done! All tables created.")

    # Print table names
    engine = get_sync_engine()
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\nTables ({len(tables)}):")
    for t in tables:
        print(f"  • {t}")


if __name__ == "__main__":
    main()
