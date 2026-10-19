# CampusFlow: High-Volume Scale & SQL Optimization Benchmark

This benchmark demonstrates pipeline throughput under high data volume and profiles the impact of relational indexing using PostgreSQL's `EXPLAIN (ANALYZE, BUFFERS)`.

---

## 1. Bulk Ingestion Throughput Benchmark

Testing ingestion of **10,000 rows** into PostgreSQL (median of **3 timed runs**):

| Ingestion Method | Rows Tested | Median Duration (s) | Throughput (Rows/Sec) | Efficiency Factor |
|---|---|---|---|---|
| **Standard Row-by-Row `INSERT`** | 10,000 | 1.765s | 5,664 rows/s | Baseline (1.0x) |
| **Psycopg Streaming `COPY` Protocol** | **10,000** | **0.008s** | **1,307,595 rows/s** | **230.8x faster** 🚀 |

### Why Streaming `COPY` Outperforms `INSERT`
1. **Zero Round-Trip Overhead:** Standard `INSERT` sends a separate query string, parameter serialization, and network round-trip per row, whereas PostgreSQL's `COPY` protocol streams records continuously in bulk directly into the database engine.
2. **Bypasses Query Parser:** `COPY` streams directly into table tuple storage without re-invoking the SQL query parser, lexer, and execution planner for each row.

---

## 2. SQL Query Optimization (`EXPLAIN ANALYZE`)

Query: Relational lookup joining `core.students`, `core.applications`, and `core.companies` filtered by specific student ID:

```sql
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
```

### Execution Plan Comparison

| Scenario | Scan Strategy | Shared Buffer Hit Blocks | Median Execution Time (ms) | Speedup Factor |
|---|---|---|---|---|
| **Without Index** | `Seq Scan (Full Table Scan)` | 104 blocks | **0.162 ms** | Baseline |
| **With Composite Indexes** | `Index Scan (idx_core_applications_student)` | **7 blocks** | **0.04 ms** | **4.0x faster** ⚡ |

### Buffer & I/O Reduction
- **Memory Buffer Efficiency:** The indexed query hit **14.9x fewer buffer blocks** (7 vs 104), minimizing cache churn in shared buffers.
- **Disk I/O Impact at Scale:** At millions of records, sequential table scans cause heavy disk I/O, whereas B-Tree indexes keep operations memory-resident with O(log N) page lookups.

---

## 3. Scale & Performance Architecture Insights

- **High-Volume Ingestion Strategy:**
  PostgreSQL's native streaming `COPY` protocol via `psycopg` achieves **1,307,595 rows/second**. When scaling to millions of rows, bypassing individual insert round-trips and using staging tables for bulk load followed by set-based upserts (`ON CONFLICT DO UPDATE`) maximizes database write bandwidth.

- **Query Planner & Buffer Cache Optimization:**
  Profiling with `EXPLAIN (ANALYZE, BUFFERS)` reveals that without indexes, PostgreSQL must perform sequential heap scans over all relation pages. By indexing `applications(student_id)`, PostgreSQL uses an index scan that reduces execution time by **4.0x** and reduces shared buffer page hits by **14.9x**, preserving buffer cache capacity.
