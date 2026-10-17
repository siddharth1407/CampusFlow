"""CampusFlow main ETL pipeline orchestrator.

Coordinates ingestion, validation, quarantine, transformation, staging,
core upserts, quality metrics, and audit logging.
"""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

from tabulate import tabulate

from config.settings import settings
from src.db import get_connection, init_db
from src.extract import (
    check_file_already_processed,
    compute_file_checksum,
    load_raw_data,
    verify_file_schema,
)
from src.load import (
    finalize_pipeline_run,
    load_staging_records,
    quarantine_rejects,
    record_file_ingestion,
    record_run_start,
    upsert_core_table,
)
from src.logging_setup import setup_logger
from src.quality import compute_and_record_metrics
from src.transform import compute_row_hash, deduplicate_records
from src.validate import (
    RejectedRecord,
    validate_applications,
    validate_companies,
    validate_offers,
    validate_students,
)

logger = setup_logger("campusflow.pipeline")


def get_existing_core_state(conn) -> tuple[set[str], set[str], dict[tuple[str, str], date]]:
    """Retrieve existing student_ids, company_ids, and application dates from core."""
    with conn.cursor() as cur:
        cur.execute("SELECT student_id FROM core.students")
        existing_students = {row[0] for row in cur.fetchall()}

        cur.execute("SELECT company_id FROM core.companies")
        existing_companies = {row[0] for row in cur.fetchall()}

        cur.execute("SELECT student_id, company_id, applied_at FROM core.applications")
        app_dates = {(row[0], row[1]): row[2] for row in cur.fetchall()}

    return existing_students, existing_companies, app_dates


def run_pipeline(
    batch_id: str,
    data_dir: Path | None = None,
    force_reprocess: bool = False,
) -> dict[str, Any]:
    """Execute the end-to-end data pipeline for a specific batch."""
    if data_dir is None:
        data_dir = settings.data_dir

    batch_path = data_dir / batch_id
    if not batch_path.exists():
        logger.error("Batch directory %s does not exist", batch_path)
        raise FileNotFoundError(f"Batch directory not found: {batch_path}")

    logger.info("==================================================")
    logger.info("Starting CampusFlow pipeline for batch: %s", batch_id)
    logger.info("==================================================")

    entities = ["students", "companies", "applications", "offers"]

    total_rows_read = 0
    total_loaded_new = 0
    total_updated = 0
    total_unchanged = 0
    all_rejects: list[RejectedRecord] = []

    stats: dict[str, Any] = {
        "rows_read": 0,
        "rows_rejected": 0,
        "apps_read": 0,
        "apps_duplicates": 0,
        "offers_read": 0,
        "offers_orphans": 0,
        "companies_read": 0,
        "companies_unmapped": 0,
    }

    has_partial_failures = False

    with get_connection() as conn:
        with conn.transaction():
            run_id = record_run_start(conn, batch_id)

        try:
            # 1. Fetch current core state for referential checks
            existing_students, existing_companies, app_dates = get_existing_core_state(conn)

            valid_batch_students: set[str] = set()
            valid_batch_companies: set[str] = set()

            # Process entities in dependency order
            for entity in entities:
                csv_file = batch_path / f"{entity}.csv"
                if not csv_file.exists():
                    logger.warning("File %s does not exist in batch %s, skipping", csv_file.name, batch_id)
                    continue

                file_key = f"{batch_id}/{csv_file.name}"
                checksum = compute_file_checksum(csv_file)

                # Check file-level idempotency
                if not force_reprocess and check_file_already_processed(conn, file_key, checksum):
                    logger.info(
                        "File %s already processed (checksum %s...). Skipping file (idempotent).",
                        file_key,
                        checksum[:8],
                    )
                    record_file_ingestion(conn, file_key, batch_id, checksum, 0, "skipped_duplicate")
                    continue

                # Schema verification
                is_valid_schema, missing_cols = verify_file_schema(csv_file, entity)
                if not is_valid_schema:
                    logger.error("Schema drift detected in %s: missing %s", file_key, missing_cols)
                    record_file_ingestion(conn, file_key, batch_id, checksum, 0, "failed")
                    all_rejects.append(
                        RejectedRecord(
                            entity,
                            0,
                            "SCHEMA_MISMATCH",
                            f"File missing required columns: {missing_cols}",
                            {"file": csv_file.name, "missing": missing_cols},
                        )
                    )
                    has_partial_failures = True
                    continue

                # Stage: Raw Load
                with conn.transaction():
                    rows_in_file, df_raw = load_raw_data(conn, csv_file, entity, batch_id)
                total_rows_read += rows_in_file

                # Stage: Validation & Cleaning
                valid_records: list[dict[str, Any]] = []
                entity_rejects: list[RejectedRecord] = []

                if entity == "students":
                    valid_records, entity_rejects = validate_students(df_raw)
                    # Deduplicate
                    valid_records, _ = deduplicate_records(valid_records, "student_id")
                    # Compute row hashes
                    for r in valid_records:
                        r["row_hash"] = compute_row_hash("students", r)
                        valid_batch_students.add(r["student_id"])

                elif entity == "companies":
                    valid_records, entity_rejects = validate_companies(df_raw)
                    valid_records, _ = deduplicate_records(valid_records, "company_id")
                    stats["companies_read"] = rows_in_file
                    for r in valid_records:
                        r["row_hash"] = compute_row_hash("companies", r)
                        valid_batch_companies.add(r["company_id"])

                elif entity == "applications":
                    stats["apps_read"] = rows_in_file
                    all_valid_students = existing_students | valid_batch_students
                    all_valid_companies = existing_companies | valid_batch_companies
                    valid_records, entity_rejects = validate_applications(
                        df_raw, all_valid_students, all_valid_companies
                    )
                    # Deduplicate applications
                    valid_records, dupes = deduplicate_records(valid_records, "application_id")
                    stats["apps_duplicates"] = dupes
                    for r in valid_records:
                        r["row_hash"] = compute_row_hash("applications", r)
                        # Record date for offer date checking
                        try:
                            d = date.fromisoformat(r["applied_at"])
                            app_dates[(r["student_id"], r["company_id"])] = d
                        except ValueError:
                            pass

                elif entity == "offers":
                    stats["offers_read"] = rows_in_file
                    all_valid_students = existing_students | valid_batch_students
                    all_valid_companies = existing_companies | valid_batch_companies
                    valid_records, entity_rejects = validate_offers(
                        df_raw, all_valid_students, all_valid_companies, app_dates
                    )
                    valid_records, _ = deduplicate_records(valid_records, "offer_id")
                    stats["offers_orphans"] = sum(
                        1 for rej in entity_rejects if rej.reason_code in ("ORPHAN_STUDENT", "ORPHAN_COMPANY")
                    )
                    for r in valid_records:
                        r["row_hash"] = compute_row_hash("offers", r)

                all_rejects.extend(entity_rejects)

                # Stage: Staging & Core Upsert within an atomic transaction
                with conn.transaction():
                    load_staging_records(conn, entity, valid_records, batch_id)
                    new_cnt, upd_cnt, unch_cnt = upsert_core_table(conn, entity, batch_id)

                    total_loaded_new += new_cnt
                    total_updated += upd_cnt
                    total_unchanged += unch_cnt

                    # Mark file ingestion as processed
                    record_file_ingestion(conn, file_key, batch_id, checksum, rows_in_file, "processed")

            # Stage: Quarantine Write
            total_rejected = len(all_rejects)
            with conn.transaction():
                quarantine_rejects(conn, run_id, batch_id, all_rejects)

            # Stage: Quality Metrics
            stats["rows_read"] = total_rows_read
            stats["rows_rejected"] = total_rejected
            with conn.transaction():
                metrics = compute_and_record_metrics(conn, run_id, stats)

            # Finalize run
            final_status = "partial" if has_partial_failures else "success"
            with conn.transaction():
                finalize_pipeline_run(
                    conn,
                    run_id,
                    final_status,
                    total_rows_read,
                    total_loaded_new,
                    total_updated,
                    total_unchanged,
                    total_rejected,
                )

            # Return run summary
            summary = {
                "run_id": run_id,
                "batch_id": batch_id,
                "status": final_status,
                "rows_read": total_rows_read,
                "rows_loaded_new": total_loaded_new,
                "rows_updated": total_updated,
                "rows_unchanged": total_unchanged,
                "rows_rejected": total_rejected,
                "reject_reasons": {
                    rej.reason_code: sum(1 for r in all_rejects if r.reason_code == rej.reason_code)
                    for rej in all_rejects
                },
                "metrics": metrics,
            }
            _print_run_summary(summary)
            return summary

        except Exception as e:
            logger.exception("Pipeline run %s failed with error: %s", run_id, e)
            conn.rollback()
            with conn.transaction():
                finalize_pipeline_run(
                    conn,
                    run_id,
                    "failed",
                    total_rows_read,
                    total_loaded_new,
                    total_updated,
                    total_unchanged,
                    len(all_rejects),
                    str(e),
                )
            raise


def _print_run_summary(summary: dict[str, Any]) -> None:
    """Print an attractive summary table to stdout."""
    table_data = [
        ["Run ID", summary["run_id"]],
        ["Batch ID", summary["batch_id"]],
        ["Status", summary["status"]],
        ["Rows Read", summary["rows_read"]],
        ["Rows Loaded (New)", summary["rows_loaded_new"]],
        ["Rows Updated", summary["rows_updated"]],
        ["Rows Unchanged", summary["rows_unchanged"]],
        ["Rows Quarantined", summary["rows_rejected"]],
    ]
    print("\n" + "=" * 50)
    print("           CAMPUSFLOW RUN SUMMARY")
    print("=" * 50)
    print(tabulate(table_data, tablefmt="fancy_grid"))

    if summary["reject_reasons"]:
        print("\nQuarantine Breakdown by Reason:")
        reject_table = [[k, v] for k, v in sorted(summary["reject_reasons"].items())]
        print(tabulate(reject_table, headers=["Reason Code", "Count"], tablefmt="grid"))
    print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(description="CampusFlow Placement Data Pipeline")
    parser.add_argument("--batch", type=str, required=True, help="Batch directory name (e.g. batch_001)")
    parser.add_argument("--data-dir", type=str, default="data/sample", help="Data root directory")
    parser.add_argument("--init-db", action="store_true", help="Initialize database schemas before running")
    parser.add_argument("--force", action="store_true", help="Force re-processing of already processed files")

    args = parser.parse_args()

    if args.init_db:
        logger.info("Initializing database schemas...")
        init_db()

    try:
        run_pipeline(
            batch_id=args.batch,
            data_dir=Path(args.data_dir),
            force_reprocess=args.force,
        )
    except Exception as e:
        logger.error("Pipeline execution failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
