"""Unit tests for date parsing and validation."""

from datetime import date

from src.validate import parse_iso_date


def test_valid_date_parsing():
    assert parse_iso_date("2024-10-15") == date(2024, 10, 15)
    assert parse_iso_date(" 2025-01-01 ") == date(2025, 1, 1)


def test_invalid_date_formats():
    assert parse_iso_date("2024-13-45") is None
    assert parse_iso_date("31/02/2025") is None
    assert parse_iso_date("2025-02-30") is None  # Feb 30 doesn't exist
    assert parse_iso_date("invalid_date") is None
    assert parse_iso_date("") is None
    assert parse_iso_date(None) is None


def test_future_dates_rejected():
    assert parse_iso_date("2099-01-01") is None
