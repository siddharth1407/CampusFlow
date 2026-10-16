"""Validation and quarantine module for CampusPulse.

Applies strict business validation rules, extracts clean records,
and prepares rejected records with standardized reason codes.
"""

from datetime import date, datetime
from typing import Any

import pandas as pd

from config.settings import load_validation_rules
from src.logging_setup import setup_logger
from src.transform import clean_string, normalize_company_name

logger = setup_logger("campuspulse.validate")


class RejectedRecord:
    def __init__(
        self,
        source_table: str,
        source_row_number: int,
        reason_code: str,
        reason_detail: str,
        raw_payload: dict[str, Any],
    ):
        self.source_table = source_table
        self.source_row_number = source_row_number
        self.reason_code = reason_code
        self.reason_detail = reason_detail
        self.raw_payload = raw_payload

    def to_dict(self, run_id: str | None = None, batch_id: str | None = None) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "batch_id": batch_id,
            "source_table": self.source_table,
            "source_row_number": self.source_row_number,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "raw_payload": self.raw_payload,
        }


def parse_iso_date(date_str: str) -> date | None:
    """Parse YYYY-MM-DD date, rejecting invalid or future dates."""
    cleaned = clean_string(date_str)
    if not cleaned:
        return None
    try:
        dt = datetime.strptime(cleaned, "%Y-%m-%d").date()
        # Today or reasonable past
        if dt > date.today():
            return None
        return dt
    except ValueError:
        return None


def validate_students(
    df_raw: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[RejectedRecord]]:
    """Validate student records according to spec."""
    valid_records = []
    rejects = []
    rules = load_validation_rules()
    bounds = rules.get("validation_bounds", {}).get("graduation_year", {"min": 2020, "max": 2030})

    for _, row in df_raw.iterrows():
        payload = row.to_dict()
        row_num = int(row.get("source_row_number", 0))
        s_id = clean_string(row.get("student_id"))
        dept = clean_string(row.get("department"))
        year_raw = clean_string(row.get("graduation_year"))
        cgpa_raw = clean_string(row.get("cgpa"))

        # 1. Missing PK
        if not s_id:
            rejects.append(RejectedRecord("students", row_num, "MISSING_PK", "student_id is missing or empty", payload))
            continue

        # 2. Missing Department
        if not dept:
            rejects.append(RejectedRecord("students", row_num, "MISSING_REQUIRED", "department is required", payload))
            continue

        # 3. Graduation Year
        try:
            year = int(year_raw)
            if year < bounds["min"] or year > bounds["max"]:
                rejects.append(
                    RejectedRecord(
                        "students",
                        row_num,
                        "INVALID_YEAR",
                        f"graduation_year {year} outside [{bounds['min']}, {bounds['max']}]",
                        payload,
                    )
                )
                continue
        except (ValueError, TypeError):
            rejects.append(
                RejectedRecord(
                    "students",
                    row_num,
                    "INVALID_YEAR",
                    f"graduation_year '{year_raw}' is not an integer",
                    payload,
                )
            )
            continue

        # 4. CGPA
        cgpa = None
        if cgpa_raw:
            try:
                cgpa = round(float(cgpa_raw), 2)
                if cgpa < 0.0 or cgpa > 10.0:
                    rejects.append(
                        RejectedRecord(
                            "students",
                            row_num,
                            "INVALID_CGPA",
                            f"cgpa {cgpa} outside [0.0, 10.0]",
                            payload,
                        )
                    )
                    continue
            except (ValueError, TypeError):
                rejects.append(
                    RejectedRecord(
                        "students",
                        row_num,
                        "INVALID_CGPA",
                        f"cgpa '{cgpa_raw}' not a valid float",
                        payload,
                    )
                )
                continue

        valid_records.append(
            {
                "student_id": s_id,
                "department": dept,
                "graduation_year": year,
                "cgpa": cgpa,
                "batch_id": row.get("batch_id"),
                "source_row_number": row_num,
            }
        )

    return valid_records, rejects


def validate_companies(
    df_raw: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[RejectedRecord]]:
    """Validate company records and standardize names."""
    valid_records = []
    rejects = []
    rules = load_validation_rules()
    allowed_sectors = set(rules.get("allowed_sectors", []))

    for _, row in df_raw.iterrows():
        payload = row.to_dict()
        row_num = int(row.get("source_row_number", 0))
        c_id = clean_string(row.get("company_id"))
        raw_name = clean_string(row.get("company_name"))
        sector = clean_string(row.get("sector"))

        # 1. Missing PK
        if not c_id:
            rejects.append(
                RejectedRecord("companies", row_num, "MISSING_PK", "company_id is missing or empty", payload)
            )
            continue

        # 2. Missing Company Name
        if not raw_name:
            rejects.append(
                RejectedRecord("companies", row_num, "MISSING_REQUIRED", "company_name is required", payload)
            )
            continue

        # 3. Invalid Sector
        if allowed_sectors and sector not in allowed_sectors:
            rejects.append(
                RejectedRecord(
                    "companies",
                    row_num,
                    "INVALID_SECTOR",
                    f"sector '{sector}' not in allowed list",
                    payload,
                )
            )
            continue

        # Standardize company name
        standardized_name, _ = normalize_company_name(raw_name)

        valid_records.append(
            {
                "company_id": c_id,
                "company_name": standardized_name,
                "company_name_raw": raw_name,
                "sector": sector,
                "batch_id": row.get("batch_id"),
                "source_row_number": row_num,
            }
        )

    return valid_records, rejects


def validate_applications(
    df_raw: pd.DataFrame,
    valid_students: set[str],
    valid_companies: set[str],
) -> tuple[list[dict[str, Any]], list[RejectedRecord]]:
    """Validate applications and check referential integrity against students and companies."""
    valid_records = []
    rejects = []
    rules = load_validation_rules()
    allowed_statuses = set(rules.get("allowed_statuses", []))

    for _, row in df_raw.iterrows():
        payload = row.to_dict()
        row_num = int(row.get("source_row_number", 0))
        app_id = clean_string(row.get("application_id"))
        s_id = clean_string(row.get("student_id"))
        c_id = clean_string(row.get("company_id"))
        applied_at_raw = clean_string(row.get("applied_at"))
        status = clean_string(row.get("status")).lower()

        # 1. Missing PK
        if not app_id:
            rejects.append(
                RejectedRecord(
                    "applications",
                    row_num,
                    "MISSING_PK",
                    "application_id is missing or empty",
                    payload,
                )
            )
            continue

        # 2. Date validation
        parsed_date = parse_iso_date(applied_at_raw)
        if not parsed_date:
            rejects.append(
                RejectedRecord(
                    "applications",
                    row_num,
                    "INVALID_DATE",
                    f"applied_at '{applied_at_raw}' is invalid or in future",
                    payload,
                )
            )
            continue

        # 3. Status validation
        if allowed_statuses and status not in allowed_statuses:
            rejects.append(
                RejectedRecord(
                    "applications",
                    row_num,
                    "INVALID_STATUS",
                    f"status '{row.get('status')}' not in allowed statuses",
                    payload,
                )
            )
            continue

        # 4. Referential integrity: Student check
        if s_id not in valid_students:
            rejects.append(
                RejectedRecord(
                    "applications",
                    row_num,
                    "ORPHAN_STUDENT",
                    f"student_id '{s_id}' does not exist in core.students",
                    payload,
                )
            )
            continue

        # 5. Referential integrity: Company check
        if c_id not in valid_companies:
            rejects.append(
                RejectedRecord(
                    "applications",
                    row_num,
                    "ORPHAN_COMPANY",
                    f"company_id '{c_id}' does not exist in core.companies",
                    payload,
                )
            )
            continue

        valid_records.append(
            {
                "application_id": app_id,
                "student_id": s_id,
                "company_id": c_id,
                "applied_at": parsed_date.isoformat(),
                "status": status,
                "batch_id": row.get("batch_id"),
                "source_row_number": row_num,
            }
        )

    return valid_records, rejects


def validate_offers(
    df_raw: pd.DataFrame,
    valid_students: set[str],
    valid_companies: set[str],
    app_dates: dict[tuple[str, str], date] | None = None,
) -> tuple[list[dict[str, Any]], list[RejectedRecord]]:
    """Validate offers: bounds, valid dates, FK references, and date order logic."""
    valid_records = []
    rejects = []
    rules = load_validation_rules()
    comp_bounds = rules.get("validation_bounds", {}).get("compensation_lpa", {"min": 1.0, "max": 300.0})

    if app_dates is None:
        app_dates = {}

    for _, row in df_raw.iterrows():
        payload = row.to_dict()
        row_num = int(row.get("source_row_number", 0))
        off_id = clean_string(row.get("offer_id"))
        s_id = clean_string(row.get("student_id"))
        c_id = clean_string(row.get("company_id"))
        comp_raw = clean_string(row.get("compensation_lpa"))
        offer_date_raw = clean_string(row.get("offer_date"))

        # 1. Missing PK
        if not off_id:
            rejects.append(RejectedRecord("offers", row_num, "MISSING_PK", "offer_id is missing or empty", payload))
            continue

        # 2. Compensation bounds
        try:
            comp = round(float(comp_raw), 2)
            if comp < comp_bounds["min"] or comp > comp_bounds["max"]:
                rejects.append(
                    RejectedRecord(
                        "offers",
                        row_num,
                        "INVALID_COMPENSATION",
                        f"compensation_lpa {comp} outside [{comp_bounds['min']}, {comp_bounds['max']}]",
                        payload,
                    )
                )
                continue
        except (ValueError, TypeError):
            rejects.append(
                RejectedRecord(
                    "offers",
                    row_num,
                    "INVALID_COMPENSATION",
                    f"compensation_lpa '{comp_raw}' is not a valid number",
                    payload,
                )
            )
            continue

        # 3. Date validation
        parsed_date = parse_iso_date(offer_date_raw)
        if not parsed_date:
            rejects.append(
                RejectedRecord(
                    "offers",
                    row_num,
                    "INVALID_DATE",
                    f"offer_date '{offer_date_raw}' is invalid or in future",
                    payload,
                )
            )
            continue

        # 4. Referential check: Student
        if s_id not in valid_students:
            rejects.append(
                RejectedRecord(
                    "offers",
                    row_num,
                    "ORPHAN_STUDENT",
                    f"student_id '{s_id}' does not exist in core.students",
                    payload,
                )
            )
            continue

        # 5. Referential check: Company
        if c_id not in valid_companies:
            rejects.append(
                RejectedRecord(
                    "offers",
                    row_num,
                    "ORPHAN_COMPANY",
                    f"company_id '{c_id}' does not exist in core.companies",
                    payload,
                )
            )
            continue

        # 6. Date order violation: offer_date cannot be before application date
        applied_at = app_dates.get((s_id, c_id))
        if applied_at and parsed_date < applied_at:
            rejects.append(
                RejectedRecord(
                    "offers",
                    row_num,
                    "DATE_ORDER_VIOLATION",
                    f"offer_date {parsed_date} is earlier than applied_at {applied_at}",
                    payload,
                )
            )
            continue

        valid_records.append(
            {
                "offer_id": off_id,
                "student_id": s_id,
                "company_id": c_id,
                "compensation_lpa": comp,
                "offer_date": parsed_date.isoformat(),
                "batch_id": row.get("batch_id"),
                "source_row_number": row_num,
            }
        )

    return valid_records, rejects
