"""Unit tests for row hashing determinism and deduplication resolution."""

from src.transform import compute_row_hash, deduplicate_records


def test_row_hash_determinism():
    row1 = {
        "student_id": "STU_001",
        "department": "Computer Science",
        "graduation_year": 2025,
        "cgpa": 8.75,
    }
    row2 = {
        "student_id": "STU_001",
        "department": "Computer Science",
        "graduation_year": 2025,
        "cgpa": 8.75,
    }
    assert compute_row_hash("students", row1) == compute_row_hash("students", row2)


def test_row_hash_detects_changes():
    app1 = {
        "application_id": "APP_001",
        "student_id": "STU_001",
        "company_id": "COMP_001",
        "applied_at": "2024-10-01",
        "status": "interviewed",
    }
    app2 = app1.copy()
    app2["status"] = "offered"

    hash1 = compute_row_hash("applications", app1)
    hash2 = compute_row_hash("applications", app2)
    assert hash1 != hash2


def test_deduplication_keeps_latest_row():
    records = [
        {"application_id": "APP_1", "status": "applied", "source_row_number": 10},
        {"application_id": "APP_2", "status": "interviewed", "source_row_number": 15},
        {"application_id": "APP_1", "status": "offered", "source_row_number": 20},  # Latest row
    ]

    deduped, dup_count = deduplicate_records(records, "application_id")
    assert dup_count == 1
    assert len(deduped) == 2

    # Map back to check winner
    lookup = {r["application_id"]: r for r in deduped}
    assert lookup["APP_1"]["status"] == "offered"
    assert lookup["APP_1"]["source_row_number"] == 20
