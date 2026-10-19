"""Unit tests for quality metrics calculation and attribution."""

from unittest.mock import MagicMock

from src.quality import compute_and_record_metrics


def test_quality_metrics_table_attribution():
    """Verify that quality metrics are attributed to their correct tables and not 'pct'."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    stats = {
        "rows_read": 1000,
        "rows_rejected": 50,
        "apps_read": 500,
        "apps_duplicates": 10,
        "offers_read": 200,
        "offers_orphans": 4,
        "companies_read": 50,
        "companies_unmapped": 5,
    }

    metrics = compute_and_record_metrics(mock_conn, "test-run-123", stats)

    assert metrics["overall_reject_rate_pct"] == 5.0
    assert metrics["duplicate_rate_applications_pct"] == 2.0
    assert metrics["orphan_rate_offers_pct"] == 2.0
    assert metrics["unmapped_rate_companies_pct"] == 10.0

    # Verify calls to record_quality_metric inserted the right table names
    executed_calls = mock_cursor.execute.call_args_list
    recorded_tables = {call[0][1][1] for call in executed_calls}

    # Must contain the correct table names, and NEVER 'pct'
    assert recorded_tables == {"overall", "applications", "offers", "companies"}
    assert "pct" not in recorded_tables
