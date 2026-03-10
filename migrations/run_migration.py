#!/usr/bin/env python3
"""Execute SQL migrations for AZALPLUS."""

import os
import sys
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moteur.db import Database
from sqlalchemy import text

async def run_migration(sql_file: str):
    """Execute a SQL migration file."""

    # Initialize database connection
    await Database.connect()

    # Read SQL file
    with open(sql_file, 'r') as f:
        sql = f.read()

    print(f"Executing migration: {sql_file}")

    with Database.get_session() as session:
        session.execute(text(sql))
        session.commit()

    print("Migration completed successfully!")

if __name__ == "__main__":
    migration_dir = os.path.dirname(os.path.abspath(__file__))
    sql_file = os.path.join(migration_dir, "add_intervention_columns.sql")

    if os.path.exists(sql_file):
        asyncio.run(run_migration(sql_file))
    else:
        print(f"Migration file not found: {sql_file}")
        sys.exit(1)
