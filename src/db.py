"""Database operations, connection pooling, and bulk loading for CampusFlow."""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg

from config.settings import settings
from src.logging_setup import setup_logger

logger = setup_logger("campusflow.db")


def get_db_params() -> dict:
    """Return database connection parameters dictionary."""
    return {
        "host": settings.postgres_host,
        "port": settings.postgres_port,
        "dbname": settings.postgres_db,
        "user": settings.postgres_user,
        "password": settings.postgres_password,
    }


@contextmanager
def get_connection() -> Generator[psycopg.Connection, None, None]:
    """Context manager for acquiring and safely closing a psycopg v3 connection."""
    conn = psycopg.connect(**get_db_params(), autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def init_db(sql_dir: Path | None = None) -> None:
    """Apply all SQL DDL migration files in order to initialize the database."""
    if sql_dir is None:
        sql_dir = Path(__file__).resolve().parent.parent / "sql"

    sql_files = [
        "00_schemas.sql",
        "01_raw.sql",
        "02_staging.sql",
        "03_core.sql",
        "04_ops.sql",
        "06_analytics_views.sql",
    ]

    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                for filename in sql_files:
                    filepath = sql_dir / filename
                    if filepath.exists():
                        logger.info("Applying schema migration: %s", filename)
                        with open(filepath, encoding="utf-8") as f:
                            cur.execute(f.read())
                    else:
                        logger.warning("Migration file not found: %s", filepath)
    logger.info("Database schemas and views initialized successfully.")


def bulk_copy(
    conn: psycopg.Connection,
    table_name: str,
    columns: list[str],
    rows: Iterable[tuple[Any, ...]],
) -> int:
    """Bulk copy rows into a PostgreSQL table using psycopg3 COPY protocol.

    Args:
        conn: Active psycopg connection.
        table_name: Qualified table name (e.g. 'staging.students').
        columns: List of column names in row order.
        rows: Iterable of tuples matching columns.

    Returns:
        Number of rows inserted.
    """
    col_str = ", ".join(f'"{col}"' for col in columns)
    copy_sql = f"COPY {table_name} ({col_str}) FROM STDIN"

    count = 0
    with conn.cursor() as cur, cur.copy(copy_sql) as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count
