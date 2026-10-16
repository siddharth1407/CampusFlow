"""Data transformation, standardization, hashing, and deduplication for CampusPulse."""

import hashlib
import re
from typing import Any

from config.settings import load_company_aliases


def clean_string(val: Any) -> str:
    """Trim whitespace and collapse multiple spaces."""
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def normalize_company_name(raw_name: str, alias_map: dict[str, str] | None = None) -> tuple[str, bool]:
    """Standardize company name by stripping noise, legal suffixes, and checking aliases.

    Returns:
        (standardized_name, is_mapped_from_alias)
    """
    if alias_map is None:
        alias_map = load_company_aliases()

    cleaned = clean_string(raw_name)
    if not cleaned:
        return "", False

    # Check direct lookup first
    lowered = cleaned.lower()
    if lowered in alias_map:
        return alias_map[lowered], True

    # Strip punctuation and trailing legal corporate suffixes
    stripped = re.sub(r"[^\w\s&]", "", lowered)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    if stripped in alias_map:
        return alias_map[stripped], True

    # Strip common suffixes
    suffix_pattern = r"\b(inc|llc|ltd|pvt|corp|corporation|technologies|systems|dev center)\b"
    simplified = re.sub(suffix_pattern, "", stripped, flags=re.IGNORECASE)
    simplified = re.sub(r"\s+", " ", simplified).strip()

    if simplified in alias_map:
        return alias_map[simplified], True

    # Return normalized title-cased version if unmapped
    return (simplified.title() if simplified else cleaned.title()), False


def compute_row_hash(entity_name: str, row: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash across canonical business attributes."""
    if entity_name == "students":
        cgpa_val = f"{float(row.get('cgpa') or 0.0):.2f}"
        canonical = f"{clean_string(row.get('student_id'))}|{clean_string(row.get('department'))}|{row.get('graduation_year')}|{cgpa_val}"
    elif entity_name == "companies":
        canonical = f"{clean_string(row.get('company_id'))}|{clean_string(row.get('company_name'))}|{clean_string(row.get('sector'))}"
    elif entity_name == "applications":
        canonical = f"{clean_string(row.get('application_id'))}|{clean_string(row.get('student_id'))}|{clean_string(row.get('company_id'))}|{clean_string(row.get('applied_at'))}|{clean_string(row.get('status'))}"
    elif entity_name == "offers":
        comp_val = f"{float(row.get('compensation_lpa') or 0.0):.2f}"
        canonical = f"{clean_string(row.get('offer_id'))}|{clean_string(row.get('student_id'))}|{clean_string(row.get('company_id'))}|{comp_val}|{clean_string(row.get('offer_date'))}"
    else:
        canonical = "|".join(f"{k}:{v}" for k, v in sorted(row.items()))

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def deduplicate_records(records: list[dict[str, Any]], pk_field: str) -> tuple[list[dict[str, Any]], int]:
    """Deduplicate records by primary key.

    If conflicting PKs exist, the record with the higher source_row_number wins.
    Returns:
        (deduplicated_list, duplicate_count)
    """
    seen: dict[str, dict[str, Any]] = {}
    duplicate_count = 0

    for rec in records:
        pk_val = rec.get(pk_field)
        if not pk_val:
            continue
        if pk_val in seen:
            duplicate_count += 1
            # Higher row number wins
            if rec.get("source_row_number", 0) >= seen[pk_val].get("source_row_number", 0):
                seen[pk_val] = rec
        else:
            seen[pk_val] = rec

    return list(seen.values()), duplicate_count
