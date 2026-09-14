#!/usr/bin/env python3
"""
Reset migrations for PrimeData.

This script:
1. Drops all alembic version tracking
2. Resets to the initial migration
3. Can be used when migration history is corrupted
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from primedata.core.settings import get_settings

def reset_migrations():
    """Reset the migration history."""
    try:
        settings = get_settings()
        engine = create_engine(settings.get_database_url())

        with engine.connect() as conn:
            try:
                # Drop alembic_version table if it exists
                conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE;"))
                print("✓ Dropped alembic_version table")
            except ProgrammingError as e:
                print(f"Note: Could not drop alembic_version: {e}")

            try:
                # Also drop the merge migration version if it exists
                conn.execute(text("DELETE FROM alembic_version WHERE version_num IN ('a1b2c3d4e5f6', '31912880d5e6', 'c3f2eeca3a86');"))
                print("✓ Cleaned up merge migration versions")
            except ProgrammingError:
                pass

            conn.commit()

        print("\n✓ Migration history reset!")
        print("You can now run: alembic upgrade head")

    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("Resetting migrations...")
    reset_migrations()
