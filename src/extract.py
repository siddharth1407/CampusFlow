"""Extraction and raw ingestion module for CampusPulse.

Handles file checksumming (idempotency gate), schema validation, and raw landing.
"""

import hashlib
from pathlib import Path

import pandas as pd
import psycopg

from config.settings import load_validation_rules
from src.db import bulk_copy
from src.logging_setup import setup_logger

logger = setup_logger("campuspulse.extract")


def compute_file_checksum(filepath: Path) -> str:
    """Compute deterministic SHA-256 checksum of a file on disk."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def check_file_already_processed(conn: psycopg.Connection, file_name: str, checksum: str) -> bool:
    """Check if this exact file version was already processed successfully."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status FROM ops.file_ingestions
            WHERE file_name = %s AND file_checksum = %s
            """,
            (file_name, checksum),
        )
        row = cur.fetchone()
        if row and row[0] == "processed":
            return True
    return False


def verify_file_schema(filepath: Path, entity_name: str) -> tuple[bool, list[str]]:
    """Validate that all mandatory columns are present in the CSV header.

    Returns:
        (is_valid, missing_columns)
    """
    rules = load_validation_rules()
    required = rules.get("required_columns", {}).get(entity_name, [])

    try:
        # Read only the header row
        df_head = pd.read_csv(filepath, nrows=0)
        actual_cols = [c.strip() for c in df_head.columns]
        missing = [c for c in required if c not in actual_cols]
        if missing:
            logger.warning(
                "Schema mismatch in %s: missing required columns %s",
                filepath.name,
                missing,
            )
            return False, missing
        return True, []
    except Exception as e:
        logger.error("Failed to read header from %s: %s", filepath.name, e)
        return False, ["FILE_CORRUPTED"]


def load_raw_data(
    conn: psycopg.Connection,
    filepath: Path,
    entity_name: str,
    batch_id: str,
) -> tuple[int, pd.DataFrame]:
    """Read CSV, record raw metadata, and bulk load into raw.{entity_name}.

    Returns:
        (row_count, raw_dataframe_with_row_numbers)
    """
    # Read entire file as string/object to preserve exact incoming values
    df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
    row_count = len(df)

    # 1-based source row numbers (matching CSV lines after header)
    df["source_row_number"] = range(1, row_count + 1)
    df["source_file"] = filepath.name
    df["batch_id"] = batch_id

    # Filter columns to only those expected in raw table
    target_table = f"raw.{entity_name}"
    rules = load_validation_rules()
    entity_cols = rules.get("required_columns", {}).get(entity_name, [])

    # Prepare columns for bulk copy
    copy_columns = entity_cols + ["batch_id", "source_file", "source_row_number"]

    # Ensure all required copy columns exist in df
    for col in copy_columns:
        if col not in df.columns:
            df[col] = ""

    rows_to_insert = [tuple(row[col] for col in copy_columns) for _, row in df.iterrows()]

    inserted = bulk_copy(conn, target_table, copy_columns, rows_to_insert)
    logger.info("Loaded %d raw records into %s", inserted, target_table)

    return row_count, df
