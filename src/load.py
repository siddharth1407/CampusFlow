"""Database loading, idempotent upserts, quarantine persistence, and run auditing."""

import json
import uuid
from typing import Any

import psycopg

from src.db import bulk_copy
from src.logging_setup import setup_logger
from src.validate import RejectedRecord

logger = setup_logger("campusflow.load")


def record_run_start(conn: psycopg.Connection, batch_id: str) -> str:
    """Create a new pipeline_runs record with status 'running' and return its UUID."""
    run_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.pipeline_runs (run_id, batch_id, started_at, status)
            VALUES (%s, %s, now(), 'running')
            """,
            (run_id, batch_id),
        )
    logger.info("Started pipeline run %s for %s", run_id, batch_id)
    return run_id


def record_file_ingestion(
    conn: psycopg.Connection,
    file_name: str,
    batch_id: str,
    file_checksum: str,
    rows_in_file: int,
    status: str,
) -> None:
    """Upsert file ingestion audit record."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.file_ingestions (file_name, batch_id, file_checksum, rows_in_file, status, ingested_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (file_name, file_checksum) DO UPDATE SET
                status = EXCLUDED.status,
                ingested_at = now()
            """,
            (file_name, batch_id, file_checksum, rows_in_file, status),
        )


def load_staging_records(
    conn: psycopg.Connection,
    entity_name: str,
    records: list[dict[str, Any]],
    batch_id: str,
) -> int:
    """Load validated records into staging.{entity_name} using bulk COPY."""
    if not records:
        return 0

    # Clean existing staging rows for this batch
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM staging.{entity_name} WHERE batch_id = %s", (batch_id,))

    # Map column definitions
    col_map = {
        "students": [
            "student_id",
            "department",
            "graduation_year",
            "cgpa",
            "row_hash",
            "batch_id",
            "source_row_number",
        ],
        "companies": [
            "company_id",
            "company_name",
            "company_name_raw",
            "sector",
            "row_hash",
            "batch_id",
            "source_row_number",
        ],
        "applications": [
            "application_id",
            "student_id",
            "company_id",
            "applied_at",
            "status",
            "row_hash",
            "batch_id",
            "source_row_number",
        ],
        "offers": [
            "offer_id",
            "student_id",
            "company_id",
            "compensation_lpa",
            "offer_date",
            "row_hash",
            "batch_id",
            "source_row_number",
        ],
    }
    columns = col_map[entity_name]

    rows = [tuple(r.get(c) for c in columns) for r in records]
    inserted = bulk_copy(conn, f"staging.{entity_name}", columns, rows)
    logger.info("Loaded %d records into staging.%s", inserted, entity_name)
    return inserted


def upsert_core_table(
    conn: psycopg.Connection,
    entity_name: str,
    batch_id: str,
) -> tuple[int, int, int]:
    """Execute idempotent upsert from staging to core.

    Returns:
        (rows_new, rows_updated, rows_unchanged)
    """
    pk_map = {
        "students": "student_id",
        "companies": "company_id",
        "applications": "application_id",
        "offers": "offer_id",
    }
    pk = pk_map[entity_name]

    with conn.cursor() as cur:
        # 1. Count new inserts
        cur.execute(
            f"""
            SELECT COUNT(*) FROM staging.{entity_name} s
            WHERE s.batch_id = %s
              AND NOT EXISTS (SELECT 1 FROM core.{entity_name} c WHERE c.{pk} = s.{pk})
            """,
            (batch_id,),
        )
        rows_new = cur.fetchone()[0]

        # 2. Count updates (where row_hash differed)
        cur.execute(
            f"""
            SELECT COUNT(*) FROM staging.{entity_name} s
            JOIN core.{entity_name} c ON s.{pk} = c.{pk}
            WHERE s.batch_id = %s
              AND c.row_hash <> s.row_hash
            """,
            (batch_id,),
        )
        rows_updated = cur.fetchone()[0]

        # 3. Total staging rows for batch
        cur.execute(
            f"SELECT COUNT(*) FROM staging.{entity_name} WHERE batch_id = %s",
            (batch_id,),
        )
        total_staging = cur.fetchone()[0]
        rows_unchanged = max(0, total_staging - rows_new - rows_updated)

        # 4. Perform atomic upsert with row_hash gating
        if entity_name == "students":
            cur.execute(
                """
                INSERT INTO core.students (student_id, department, graduation_year, cgpa, row_hash, last_batch_id)
                SELECT student_id, department, graduation_year, cgpa, row_hash, batch_id
                FROM staging.students WHERE batch_id = %s
                ON CONFLICT (student_id) DO UPDATE SET
                    department = EXCLUDED.department,
                    graduation_year = EXCLUDED.graduation_year,
                    cgpa = EXCLUDED.cgpa,
                    row_hash = EXCLUDED.row_hash,
                    last_updated_at = now(),
                    last_batch_id = EXCLUDED.last_batch_id
                WHERE core.students.row_hash <> EXCLUDED.row_hash
                """,
                (batch_id,),
            )
        elif entity_name == "companies":
            cur.execute(
                """
                INSERT INTO core.companies (company_id, company_name, company_name_raw, sector, row_hash, last_batch_id)
                SELECT company_id, company_name, company_name_raw, sector, row_hash, batch_id
                FROM staging.companies WHERE batch_id = %s
                ON CONFLICT (company_id) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    sector = EXCLUDED.sector,
                    row_hash = EXCLUDED.row_hash,
                    last_updated_at = now(),
                    last_batch_id = EXCLUDED.last_batch_id
                WHERE core.companies.row_hash <> EXCLUDED.row_hash
                """,
                (batch_id,),
            )
        elif entity_name == "applications":
            cur.execute(
                """
                INSERT INTO core.applications (application_id, student_id, company_id, applied_at, status, row_hash, last_batch_id)
                SELECT application_id, student_id, company_id, applied_at, status, row_hash, batch_id
                FROM staging.applications WHERE batch_id = %s
                ON CONFLICT (application_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    row_hash = EXCLUDED.row_hash,
                    last_updated_at = now(),
                    last_batch_id = EXCLUDED.last_batch_id
                WHERE core.applications.row_hash <> EXCLUDED.row_hash
                """,
                (batch_id,),
            )
        elif entity_name == "offers":
            cur.execute(
                """
                INSERT INTO core.offers (offer_id, student_id, company_id, compensation_lpa, offer_date, row_hash, last_batch_id)
                SELECT offer_id, student_id, company_id, compensation_lpa, offer_date, row_hash, batch_id
                FROM staging.offers WHERE batch_id = %s
                ON CONFLICT (offer_id) DO UPDATE SET
                    compensation_lpa = EXCLUDED.compensation_lpa,
                    offer_date = EXCLUDED.offer_date,
                    row_hash = EXCLUDED.row_hash,
                    last_updated_at = now(),
                    last_batch_id = EXCLUDED.last_batch_id
                WHERE core.offers.row_hash <> EXCLUDED.row_hash
                """,
                (batch_id,),
            )

    logger.info(
        "Upsert core.%s: %d new, %d updated, %d unchanged",
        entity_name,
        rows_new,
        rows_updated,
        rows_unchanged,
    )
    return rows_new, rows_updated, rows_unchanged


def quarantine_rejects(
    conn: psycopg.Connection,
    run_id: str,
    batch_id: str,
    rejects: list[RejectedRecord],
) -> int:
    """Bulk insert rejected records into ops.rejected_records."""
    if not rejects:
        return 0

    columns = [
        "run_id",
        "batch_id",
        "source_table",
        "source_row_number",
        "reason_code",
        "reason_detail",
        "raw_payload",
    ]

    rows = [
        (
            run_id,
            batch_id,
            r.source_table,
            r.source_row_number,
            r.reason_code,
            r.reason_detail,
            json.dumps(r.raw_payload),
        )
        for r in rejects
    ]

    inserted = bulk_copy(conn, "ops.rejected_records", columns, rows)
    logger.info("Quarantined %d rejected records for run %s", inserted, run_id)
    return inserted


def finalize_pipeline_run(
    conn: psycopg.Connection,
    run_id: str,
    status: str,
    rows_read: int,
    rows_new: int,
    rows_updated: int,
    rows_unchanged: int,
    rows_rejected: int,
    error_message: str | None = None,
) -> None:
    """Finalize run status and counts in ops.pipeline_runs."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ops.pipeline_runs SET
                finished_at = now(),
                status = %s,
                rows_read = %s,
                rows_loaded_new = %s,
                rows_updated = %s,
                rows_unchanged = %s,
                rows_rejected = %s,
                error_message = %s
            WHERE run_id = %s
            """,
            (
                status,
                rows_read,
                rows_new,
                rows_updated,
                rows_unchanged,
                rows_rejected,
                error_message,
                run_id,
            ),
        )
    logger.info(
        "Finalized pipeline run %s: status=%s, read=%d, new=%d, updated=%d, unchanged=%d, rejected=%d",
        run_id,
        status,
        rows_read,
        rows_new,
        rows_updated,
        rows_unchanged,
        rows_rejected,
    )
