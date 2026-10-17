"""End-to-end integration tests for CampusFlow.

Tests:
1. Batch 001 baseline load & manifest ground-truth reject matching
2. Batch 002 incremental updates and new inserts
3. Batch 003 exact replay verifying zero net changes (Idempotency proof)
4. Batch 004 schema drift isolation and partial status
5. Referential integrity validation on core schema
6. Atomic transaction rollback verification
"""

import json
from pathlib import Path

import pytest

from src.db import get_connection, init_db
from src.pipeline import run_pipeline


def is_postgres_available() -> bool:
    """Check if PostgreSQL database is reachable."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not is_postgres_available(),
    reason="PostgreSQL is not reachable. Start container with `docker compose up -d`.",
)


@pytest.fixture(scope="module")
def setup_database():
    """Wipe and re-initialize database schemas for clean test execution."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DROP SCHEMA IF EXISTS raw CASCADE;
                DROP SCHEMA IF EXISTS staging CASCADE;
                DROP SCHEMA IF EXISTS core CASCADE;
                DROP SCHEMA IF EXISTS ops CASCADE;
                DROP SCHEMA IF EXISTS analytics CASCADE;
            """)
        conn.commit()
    init_db()


def test_batch_001_full_run_and_manifest_matching(setup_database):
    """Batch 001 must succeed and reject counts must match ground-truth faults_manifest.json."""
    manifest_path = Path("data/sample/faults_manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    expected_faults = manifest["batches"]["batch_001"]["injected_faults"]

    summary = run_pipeline("batch_001", data_dir=Path("data/sample"), force_reprocess=True)
    assert summary["status"] == "success"
    assert summary["rows_loaded_new"] > 0

    reasons = summary["reject_reasons"]

    # Verify key injected fault counts match exactly
    assert reasons.get("MISSING_PK", 0) == expected_faults["MISSING_PK"]
    assert reasons.get("MISSING_REQUIRED", 0) == expected_faults["MISSING_REQUIRED"]
    assert reasons.get("INVALID_YEAR", 0) == expected_faults["INVALID_YEAR"]
    assert reasons.get("INVALID_DATE", 0) == expected_faults["INVALID_DATE"]
    assert reasons.get("DATE_ORDER_VIOLATION", 0) == expected_faults["DATE_ORDER_VIOLATION"]
    assert reasons.get("ORPHAN_STUDENT", 0) == expected_faults["ORPHAN_STUDENT"]
    assert reasons.get("ORPHAN_COMPANY", 0) == expected_faults["ORPHAN_COMPANY"]
    assert reasons.get("INVALID_STATUS", 0) == expected_faults["INVALID_STATUS"]
    assert reasons.get("INVALID_COMPENSATION", 0) == expected_faults["INVALID_COMPENSATION"]


def test_core_referential_integrity():
    """Verify no orphaned applications or offers exist in core."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Check applications student FK
            cur.execute("""
                SELECT COUNT(*) FROM core.applications a
                LEFT JOIN core.students s ON a.student_id = s.student_id
                WHERE s.student_id IS NULL
            """)
            assert cur.fetchone()[0] == 0

            # Check applications company FK
            cur.execute("""
                SELECT COUNT(*) FROM core.applications a
                LEFT JOIN core.companies c ON a.company_id = c.company_id
                WHERE c.company_id IS NULL
            """)
            assert cur.fetchone()[0] == 0

            # Check offers student FK
            cur.execute("""
                SELECT COUNT(*) FROM core.offers o
                LEFT JOIN core.students s ON o.student_id = s.student_id
                WHERE s.student_id IS NULL
            """)
            assert cur.fetchone()[0] == 0


def test_batch_002_incremental_updates():
    """Batch 002 must insert new rows and update changed records."""
    summary = run_pipeline("batch_002", data_dir=Path("data/sample"), force_reprocess=True)
    assert summary["status"] == "success"
    assert summary["rows_loaded_new"] > 0
    assert summary["rows_updated"] > 0  # Interviewed -> Offered updates


def test_batch_003_idempotency_zero_net_changes():
    """Batch 003 is an exact replay of Batch 002; must yield zero new and zero updated rows."""
    summary = run_pipeline("batch_003", data_dir=Path("data/sample"), force_reprocess=True)
    assert summary["status"] == "success"
    assert summary["rows_loaded_new"] == 0
    assert summary["rows_updated"] == 0
    assert summary["rows_unchanged"] > 0


def test_batch_004_schema_drift_handling():
    """Batch 004 has corrupted headers; must mark file as failed without crashing."""
    summary = run_pipeline("batch_004", data_dir=Path("data/sample"), force_reprocess=True)
    assert summary["status"] == "partial"
    assert summary["reject_reasons"].get("SCHEMA_MISMATCH", 0) >= 1


def test_atomic_transaction_rollback():
    """Simulate a failure mid-transaction and verify no partial records persist."""
    with get_connection() as conn:
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO core.students (student_id, department, graduation_year, cgpa, row_hash, last_batch_id) "
                        "VALUES ('STU_TEMP_TEST', 'Chemical', 2025, 8.0, 'hash', 'test_rollback')"
                    )
                    # Force error
                    raise RuntimeError("Forced crash to test rollback")
        except RuntimeError:
            pass

        # Verify STU_TEMP_TEST was rolled back
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM core.students WHERE student_id = 'STU_TEMP_TEST'")
            assert cur.fetchone()[0] == 0
