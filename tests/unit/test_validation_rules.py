"""Unit tests ensuring validation rules assign the exact expected reason codes."""

from datetime import date

import pandas as pd

from src.validate import (
    validate_applications,
    validate_companies,
    validate_offers,
    validate_students,
)


def test_validate_students_rules():
    # 1. Missing PK
    df_missing_pk = pd.DataFrame(
        [
            {
                "source_row_number": 1,
                "student_id": "",
                "department": "Computer Science",
                "graduation_year": "2025",
                "cgpa": "8.5",
            }
        ]
    )
    valid, rejects = validate_students(df_missing_pk)
    assert len(valid) == 0
    assert len(rejects) == 1
    assert rejects[0].reason_code == "MISSING_PK"

    # 2. Missing Department
    df_missing_dept = pd.DataFrame(
        [
            {
                "source_row_number": 2,
                "student_id": "STU_001",
                "department": "",
                "graduation_year": "2025",
                "cgpa": "8.5",
            }
        ]
    )
    valid, rejects = validate_students(df_missing_dept)
    assert len(valid) == 0
    assert len(rejects) == 1
    assert rejects[0].reason_code == "MISSING_REQUIRED"

    # 3. Invalid Graduation Year
    df_invalid_year = pd.DataFrame(
        [
            {
                "source_row_number": 3,
                "student_id": "STU_002",
                "department": "Mechanical",
                "graduation_year": "1899",
                "cgpa": "8.0",
            }
        ]
    )
    valid, rejects = validate_students(df_invalid_year)
    assert len(valid) == 0
    assert len(rejects) == 1
    assert rejects[0].reason_code == "INVALID_YEAR"


def test_validate_companies_rules():
    df = pd.DataFrame(
        [
            {"source_row_number": 1, "company_id": "", "company_name": "Google", "sector": "Software"},
            {"source_row_number": 2, "company_id": "COMP1", "company_name": "", "sector": "Software"},
            {"source_row_number": 3, "company_id": "COMP2", "company_name": "Meta", "sector": "SpaceExploration"},
        ]
    )
    valid, rejects = validate_companies(df)
    assert len(valid) == 0
    assert len(rejects) == 3
    assert rejects[0].reason_code == "MISSING_PK"
    assert rejects[1].reason_code == "MISSING_REQUIRED"
    assert rejects[2].reason_code == "INVALID_SECTOR"


def test_validate_applications_rules():
    valid_students = {"STU_001"}
    valid_companies = {"COMP_001"}

    df = pd.DataFrame(
        [
            {
                "source_row_number": 1,
                "application_id": "",
                "student_id": "STU_001",
                "company_id": "COMP_001",
                "applied_at": "2024-10-01",
                "status": "applied",
            },
            {
                "source_row_number": 2,
                "application_id": "APP1",
                "student_id": "STU_001",
                "company_id": "COMP_001",
                "applied_at": "2024-13-45",
                "status": "applied",
            },
            {
                "source_row_number": 3,
                "application_id": "APP2",
                "student_id": "STU_001",
                "company_id": "COMP_001",
                "applied_at": "2024-10-01",
                "status": "InvalidStatus!",
            },
            {
                "source_row_number": 4,
                "application_id": "APP3",
                "student_id": "STU_UNKNOWN",
                "company_id": "COMP_001",
                "applied_at": "2024-10-01",
                "status": "applied",
            },
            {
                "source_row_number": 5,
                "application_id": "APP4",
                "student_id": "STU_001",
                "company_id": "COMP_UNKNOWN",
                "applied_at": "2024-10-01",
                "status": "applied",
            },
        ]
    )
    valid, rejects = validate_applications(df, valid_students, valid_companies)
    assert len(valid) == 0
    assert len(rejects) == 5
    codes = [r.reason_code for r in rejects]
    assert codes == ["MISSING_PK", "INVALID_DATE", "INVALID_STATUS", "ORPHAN_STUDENT", "ORPHAN_COMPANY"]


def test_validate_offers_rules():
    valid_students = {"STU_001"}
    valid_companies = {"COMP_001"}
    app_dates = {("STU_001", "COMP_001"): date(2024, 10, 1)}

    df = pd.DataFrame(
        [
            {
                "source_row_number": 1,
                "offer_id": "",
                "student_id": "STU_001",
                "company_id": "COMP_001",
                "compensation_lpa": "25.0",
                "offer_date": "2024-11-01",
            },
            {
                "source_row_number": 2,
                "offer_id": "OFF1",
                "student_id": "STU_001",
                "company_id": "COMP_001",
                "compensation_lpa": "-10.0",
                "offer_date": "2024-11-01",
            },
            {
                "source_row_number": 3,
                "offer_id": "OFF2",
                "student_id": "STU_001",
                "company_id": "COMP_001",
                "compensation_lpa": "25.0",
                "offer_date": "2024-09-01",
            },  # Date order violation
            {
                "source_row_number": 4,
                "offer_id": "OFF3",
                "student_id": "STU_GHOST",
                "company_id": "COMP_001",
                "compensation_lpa": "25.0",
                "offer_date": "2024-11-01",
            },
        ]
    )
    valid, rejects = validate_offers(df, valid_students, valid_companies, app_dates)
    assert len(valid) == 0
    assert len(rejects) == 4
    codes = [r.reason_code for r in rejects]
    assert codes == ["MISSING_PK", "INVALID_COMPENSATION", "DATE_ORDER_VIOLATION", "ORPHAN_STUDENT"]
