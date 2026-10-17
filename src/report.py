"""CampusFlow analytical and pipeline health reporting tool."""

from tabulate import tabulate

from src.db import get_connection
from src.logging_setup import setup_logger

logger = setup_logger("campusflow.report")


def print_placement_summary():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT graduation_year, total_students, placed_students, placement_rate_pct
                FROM analytics.placement_summary
            """)
            rows = cur.fetchall()
            print("\n" + "=" * 60)
            print("         PLACEMENT SUMMARY BY GRADUATION YEAR")
            print("=" * 60)
            print(
                tabulate(
                    rows,
                    headers=["Grad Year", "Total Students", "Placed Students", "Placement Rate %"],
                    tablefmt="fancy_grid",
                )
            )


def print_department_compensation():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT department, total_offers, students_placed, mean_compensation_lpa, median_compensation_lpa, max_compensation_lpa
                FROM analytics.department_offers
            """)
            rows = cur.fetchall()
            print("\n" + "=" * 75)
            print("       COMPENSATION & OFFERS BY DEPARTMENT (LPA)")
            print("=" * 75)
            print(
                tabulate(
                    rows,
                    headers=[
                        "Department",
                        "Total Offers",
                        "Students Placed",
                        "Mean (LPA)",
                        "Median (LPA)",
                        "Max (LPA)",
                    ],
                    tablefmt="fancy_grid",
                )
            )


def print_company_funnel():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT company_name, sector, total_applications, total_shortlisted, total_interviewed, total_offered, conversion_rate_pct
                FROM analytics.company_funnel
                LIMIT 10
            """)
            rows = cur.fetchall()
            print("\n" + "=" * 85)
            print("         TOP 10 COMPANIES RECRUITMENT FUNNEL")
            print("=" * 85)
            print(
                tabulate(
                    rows,
                    headers=[
                        "Company",
                        "Sector",
                        "Applications",
                        "Shortlisted",
                        "Interviewed",
                        "Offered",
                        "Conversion %",
                    ],
                    tablefmt="fancy_grid",
                )
            )


def print_pipeline_health():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT batch_id, status, rows_read, rows_loaded_new, rows_updated, rows_unchanged, rows_rejected
                FROM ops.pipeline_runs
                ORDER BY started_at ASC
            """)

            rows = cur.fetchall()
            print("\n" + "=" * 80)
            print("             PIPELINE AUDIT & RUN HEALTH")
            print("=" * 80)
            print(
                tabulate(
                    rows,
                    headers=["Batch ID", "Status", "Read", "New", "Updated", "Unchanged", "Quarantined"],
                    tablefmt="fancy_grid",
                )
            )

            # Quarantined records breakdown
            cur.execute("""
                SELECT batch_id, source_table, reason_code, COUNT(*) AS count
                FROM ops.rejected_records
                GROUP BY batch_id, source_table, reason_code
                ORDER BY batch_id, count DESC
            """)
            rej_rows = cur.fetchall()
            if rej_rows:
                print("\n" + "=" * 65)
                print("           REJECTED RECORDS BREAKDOWN")
                print("=" * 65)
                print(
                    tabulate(
                        rej_rows,
                        headers=["Batch", "Table", "Reason Code", "Count"],
                        tablefmt="grid",
                    )
                )


def generate_full_report():
    """Generate all analytical and ops reports."""
    print_pipeline_health()
    print_placement_summary()
    print_department_compensation()
    print_company_funnel()


if __name__ == "__main__":
    generate_full_report()
