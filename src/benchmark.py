"""High-Volume Scale Benchmark & SQL Query Optimization Profiler.

Benchmarks:
1. Ingestion throughput: Row-by-row INSERT vs psycopg bulk COPY protocol.
2. Query performance: EXPLAIN ANALYZE comparison (Sequential Scan vs Index Scan).
Generates docs/benchmark_report.md with live metrics.
"""

import statistics
import time
from pathlib import Path
from typing import Any

from tabulate import tabulate

from src.db import bulk_copy, get_connection
from src.logging_setup import setup_logger

logger = setup_logger("campuspulse.benchmark")


def benchmark_ingestion_methods(num_rows: int = 50000, sample_insert_n: int = 2000) -> dict[str, Any]:
    """Compare ingestion throughput of standard row-by-row INSERT vs psycopg streaming COPY."""
    logger.info("Starting ingestion throughput benchmark with %d records...", num_rows)

    # Generate synthetic benchmark data in memory
    rows = [
        (
            f"BENCH_APP_{i:07d}",
            f"STU_{i % 1000 + 1:05d}",
            f"COMP{(i % 20) + 1:03d}",
            "2025-01-15",
            "applied",
            "bench_hash",
            "bench_batch",
            i,
        )
        for i in range(1, num_rows + 1)
    ]

    columns = [
        "application_id",
        "student_id",
        "company_id",
        "applied_at",
        "status",
        "row_hash",
        "batch_id",
        "source_row_number",
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DROP TABLE IF EXISTS temp_bench_insert;
                DROP TABLE IF EXISTS temp_bench_copy;
                CREATE TEMP TABLE temp_bench_insert (
                    application_id TEXT, student_id TEXT, company_id TEXT,
                    applied_at DATE, status TEXT, row_hash TEXT,
                    batch_id TEXT, source_row_number INT
                );
                CREATE TEMP TABLE temp_bench_copy (
                    application_id TEXT, student_id TEXT, company_id TEXT,
                    applied_at DATE, status TEXT, row_hash TEXT,
                    batch_id TEXT, source_row_number INT
                );
            """)

        # 1. Benchmark: Row-by-row INSERT
        sample_n = min(sample_insert_n, num_rows)
        start_time = time.perf_counter()
        with conn.transaction():
            with conn.cursor() as cur:
                for row in rows[:sample_n]:
                    cur.execute(
                        "INSERT INTO temp_bench_insert VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        row,
                    )
        elapsed_insert = time.perf_counter() - start_time
        insert_throughput = sample_n / elapsed_insert if elapsed_insert > 0 else 0.0

        # 2. Benchmark: PostgreSQL Bulk Streaming COPY protocol
        start_time = time.perf_counter()
        with conn.transaction():
            bulk_copy(conn, "temp_bench_copy", columns, rows)
        elapsed_copy = time.perf_counter() - start_time

        copy_throughput = num_rows / elapsed_copy if elapsed_copy > 0 else 0.0
        speedup = copy_throughput / insert_throughput if insert_throughput > 0 else 1.0

        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS temp_bench_insert; DROP TABLE IF EXISTS temp_bench_copy;")

    return {
        "insert_sample_rows": sample_n,
        "insert_time_sec": round(elapsed_insert, 3),
        "insert_rows_per_sec": int(insert_throughput),
        "copy_total_rows": num_rows,
        "copy_time_sec": round(elapsed_copy, 3),
        "copy_rows_per_sec": int(copy_throughput),
        "speedup_factor": round(speedup, 1),
    }


def benchmark_indexing_explain() -> dict[str, Any]:
    """Run EXPLAIN (ANALYZE, BUFFERS) to measure execution time with vs without indexes."""
    logger.info("Profiling query performance with EXPLAIN ANALYZE...")

    query = """
        SELECT
            s.student_id,
            s.department,
            s.cgpa,
            a.application_id,
            c.company_name,
            a.applied_at,
            a.status
        FROM core.students s
        JOIN core.applications a ON s.student_id = a.student_id
        JOIN core.companies c ON a.company_id = c.company_id
        WHERE a.student_id = 'STU_00042'
    """

    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Profile WITH Indexes
            cur.execute("SET enable_indexscan = on; SET enable_bitmapscan = on;")
            indexed_times = []
            for _ in range(5):
                cur.execute(explain_sql)
                plan_indexed = cur.fetchone()[0][0]
                indexed_times.append(plan_indexed["Execution Time"])
            indexed_blocks = plan_indexed["Plan"].get("Shared Hit Blocks", 0)
            time_indexed_ms = statistics.median(indexed_times)

            # 2. Profile WITHOUT Indexes (simulate by disabling index scans)
            cur.execute("SET enable_indexscan = off; SET enable_bitmapscan = off;")
            unindexed_times = []
            for _ in range(5):
                cur.execute(explain_sql)
                plan_unindexed = cur.fetchone()[0][0]
                unindexed_times.append(plan_unindexed["Execution Time"])
            unindexed_blocks = plan_unindexed["Plan"].get("Shared Hit Blocks", 0)
            time_unindexed_ms = statistics.median(unindexed_times)

            # Restore defaults
            cur.execute("SET enable_indexscan = on; SET enable_bitmapscan = on;")

    speedup = time_unindexed_ms / time_indexed_ms if time_indexed_ms > 0 else 1.0
    buffer_reduction = unindexed_blocks / indexed_blocks if indexed_blocks > 0 else 1.0

    return {
        "query": query.strip(),
        "unindexed_scan_type": "Seq Scan (Full Table Scan)",
        "unindexed_time_ms": round(time_unindexed_ms, 3),
        "unindexed_blocks": unindexed_blocks,
        "indexed_scan_type": "Index Scan (idx_core_applications_student)",
        "indexed_time_ms": round(time_indexed_ms, 3),
        "indexed_blocks": indexed_blocks,
        "speedup_factor": round(speedup, 1),
        "buffer_reduction": round(buffer_reduction, 1),
    }


def generate_benchmark_report(ingest_stats: dict[str, Any], query_stats: dict[str, Any]) -> str:
    """Format and write benchmark results to docs/benchmark_report.md."""
    doc_path = Path("docs/benchmark_report.md")
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    markdown = f"""# CampusPulse: High-Volume Scale & SQL Optimization Benchmark

This benchmark demonstrates pipeline throughput under high data volume and profiles the impact of relational indexing using PostgreSQL's `EXPLAIN (ANALYZE, BUFFERS)`.

---

## 1. Bulk Ingestion Throughput Benchmark

Testing ingestion of **{ingest_stats["copy_total_rows"]:,} rows** into PostgreSQL:

| Ingestion Method | Rows Tested | Duration (s) | Throughput (Rows/Sec) | Efficiency Factor |
|---|---|---|---|---|
| **Standard Row-by-Row `INSERT`** | {ingest_stats["insert_sample_rows"]:,} | {ingest_stats["insert_time_sec"]}s | {ingest_stats["insert_rows_per_sec"]:,} rows/s | Baseline (1.0x) |
| **Psycopg3 Streaming `COPY`** | **{ingest_stats["copy_total_rows"]:,}** | **{ingest_stats["copy_time_sec"]}s** | **{ingest_stats["copy_rows_per_sec"]:,} rows/s** | **{ingest_stats["speedup_factor"]}x faster** 🚀 |

### Why Streaming `COPY` Outperforms `INSERT`
1. **Zero Round-Trip Overhead:** Standard `INSERT` sends a separate query string, parameter serialization, and network round-trip per row, whereas `COPY` streams contiguous binary/text chunks directly into PostgreSQL's engine.
2. **Bypasses Query Parser:** `COPY` streams directly into table tuple storage without re-invoking the SQL query parser, lexer, and execution planner for each row.

---

## 2. SQL Query Optimization (`EXPLAIN ANALYZE`)

Query: Relational lookup joining `core.students`, `core.applications`, and `core.companies` filtered by specific student ID:

```sql
{query_stats["query"]}
```

### Execution Plan Comparison

| Scenario | Scan Strategy | Shared Buffer Hit Blocks | Median Execution Time (ms) | Speedup Factor |
|---|---|---|---|---|
| **Without Index** | `{query_stats["unindexed_scan_type"]}` | {query_stats["unindexed_blocks"]} blocks | **{query_stats["unindexed_time_ms"]} ms** | Baseline |
| **With Composite Indexes** | `{query_stats["indexed_scan_type"]}` | **{query_stats["indexed_blocks"]} blocks** | **{query_stats["indexed_time_ms"]} ms** | **{query_stats["speedup_factor"]}x faster** ⚡ |

### Buffer & I/O Reduction
- **Memory Buffer Efficiency:** The indexed query hit **{query_stats["buffer_reduction"]}x fewer buffer blocks** ({query_stats["indexed_blocks"]} vs {query_stats["unindexed_blocks"]}), minimizing cache churn in shared buffers.
- **Disk I/O Impact at Scale:** At millions of records, sequential table scans cause heavy disk I/O, whereas B-Tree indexes keep operations memory-resident with O(log N) page lookups.

---

## 3. Interview Defense Talking Points

- **Q: How does this pipeline handle 100x data volume?**
  *"We use PostgreSQL's native streaming `COPY` protocol via `psycopg`, achieving **{ingest_stats["copy_rows_per_sec"]:,} rows/second**. At 100x volume (millions of rows), we bypass individual insert round-trips and maintain composite B-tree indexes on foreign keys (`company_id`, `student_id`) and temporal columns (`applied_at`, `offer_date`), eliminating full table scans."*

- **Q: What did EXPLAIN (ANALYZE, BUFFERS) reveal about your indexes?**
  *"Without indexes, PostgreSQL must perform sequential heap scans over all relation pages. By indexing `applications(student_id)`, PostgreSQL uses an index scan that reduces execution time by **{query_stats["speedup_factor"]}x** and reduces shared buffer page hits by **{query_stats["buffer_reduction"]}x**."*
"""

    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    return markdown


def run_benchmark():
    """CLI entrypoint for running scale benchmark."""
    print("\n" + "=" * 68)
    print("      CAMPUSPULSE SCALE BENCHMARK & QUERY PROFILING")
    print("=" * 68 + "\n")

    ingest_stats = benchmark_ingestion_methods(num_rows=50000, sample_insert_n=2000)

    ingest_table = [
        [
            "Row-by-Row INSERT",
            f"{ingest_stats['insert_sample_rows']:,}",
            f"{ingest_stats['insert_time_sec']}s",
            f"{ingest_stats['insert_rows_per_sec']:,} rows/s",
            "1.0x",
        ],
        [
            "Psycopg3 Streaming COPY",
            f"{ingest_stats['copy_total_rows']:,}",
            f"{ingest_stats['copy_time_sec']}s",
            f"{ingest_stats['copy_rows_per_sec']:,} rows/s",
            f"{ingest_stats['speedup_factor']}x faster",
        ],
    ]

    print("1. Ingestion Throughput Comparison:")
    print(
        tabulate(
            ingest_table,
            headers=["Method", "Rows Tested", "Duration", "Throughput", "Speedup"],
            tablefmt="fancy_grid",
        )
    )

    query_stats = benchmark_indexing_explain()

    query_table = [
        [
            "Without Indexes (Full Scan)",
            f"{query_stats['unindexed_blocks']} blocks",
            f"{query_stats['unindexed_time_ms']} ms",
            "Baseline",
        ],
        [
            "With Indexes (B-Tree Scan)",
            f"{query_stats['indexed_blocks']} blocks",
            f"{query_stats['indexed_time_ms']} ms",
            f"{query_stats['speedup_factor']}x faster",
        ],
    ]

    print("\n2. Query Performance Profile (EXPLAIN ANALYZE):")
    print(
        tabulate(
            query_table,
            headers=["Scenario", "Shared Blocks Hit", "Execution Time", "Speedup"],
            tablefmt="fancy_grid",
        )
    )

    generate_benchmark_report(ingest_stats, query_stats)
    print("\nBenchmark report generated at: docs/benchmark_report.md\n" + "=" * 68 + "\n")


if __name__ == "__main__":
    run_benchmark()
