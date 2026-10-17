"""Data quality metrics calculation and recording for CampusFlow."""

from typing import Any

import psycopg

from src.logging_setup import setup_logger

logger = setup_logger("campusflow.quality")


def record_quality_metric(
    conn: psycopg.Connection,
    run_id: str,
    table_name: str,
    metric_name: str,
    metric_value: float,
) -> None:
    """Insert a single quality metric into ops.quality_metrics."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.quality_metrics (run_id, table_name, metric_name, metric_value)
            VALUES (%s, %s, %s, %s)
            """,
            (run_id, table_name, metric_name, round(metric_value, 4)),
        )


def compute_and_record_metrics(
    conn: psycopg.Connection,
    run_id: str,
    stats: dict[str, Any],
) -> dict[str, float]:
    """Calculate pipeline quality metrics and write them to ops.quality_metrics.

    Returns:
        Dictionary of calculated metric names and values.
    """
    metrics: dict[str, float] = {}

    total_read = stats.get("rows_read", 0)
    total_rejected = stats.get("rows_rejected", 0)
    if total_read > 0:
        metrics["overall_reject_rate_pct"] = (total_rejected / total_read) * 100.0

    # Applications duplication rate
    apps_read = stats.get("apps_read", 0)
    apps_dupes = stats.get("apps_duplicates", 0)
    if apps_read > 0:
        metrics["duplicate_rate_applications_pct"] = (apps_dupes / apps_read) * 100.0

    # Offers orphan rate
    offers_read = stats.get("offers_read", 0)
    offers_orphans = stats.get("offers_orphans", 0)
    if offers_read > 0:
        metrics["orphan_rate_offers_pct"] = (offers_orphans / offers_read) * 100.0

    # Company name unmapped rate
    companies_read = stats.get("companies_read", 0)
    companies_unmapped = stats.get("companies_unmapped", 0)
    if companies_read > 0:
        metrics["unmapped_rate_companies_pct"] = (companies_unmapped / companies_read) * 100.0

    # Record all calculated metrics
    for metric_name, val in metrics.items():
        table = metric_name.split("_")[-1]  # e.g. 'applications' or 'offers'
        record_quality_metric(conn, run_id, table, metric_name, val)

    logger.info("Recorded %d quality metrics for run %s", len(metrics), run_id)
    return metrics
