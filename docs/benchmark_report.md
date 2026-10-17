# CampusFlow: High-Volume Scale & SQL Optimization Benchmark

This benchmark demonstrates pipeline throughput under high data volume and profiles the impact of relational indexing using PostgreSQL's `EXPLAIN (ANALYZE, BUFFERS)`.

---

## 1. Bulk Ingestion Throughput Benchmark

Testing ingestion of **50,000 rows** into PostgreSQL:

| Ingestion Method | Rows Tested | Duration (s) | Throughput (Rows/Sec) | Efficiency Factor |
|---|---|---|---|---|
| **Standard Row-by-Row `INSERT`** | 2,000 | 0.253s | 7,895 rows/s | Baseline (1.0x) |
| **Psycopg3 Streaming `COPY`** | **50,000** | **0.031s** | **1,638,162 rows/s** | **207.5x faster** 🚀 |

### Why Streaming `COPY` Outperforms `INSERT`
1. **Zero Round-Trip Overhead:** Standard `INSERT` sends a separate query string, parameter serialization, and network round-trip per row, whereas `COPY` streams contiguous binary/text chunks directly into PostgreSQL's engine.
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
| **Without Index** | `Seq Scan (Full Table Scan)` | 104 blocks | **0.183 ms** | Baseline |
| **With Composite Indexes** | `Index Scan (idx_core_applications_student)` | **7 blocks** | **0.048 ms** | **3.8x faster** ⚡ |

### Buffer & I/O Reduction
- **Memory Buffer Efficiency:** The indexed query hit **14.9x fewer buffer blocks** (7 vs 104), minimizing cache churn in shared buffers.
- **Disk I/O Impact at Scale:** At millions of records, sequential table scans cause heavy disk I/O, whereas B-Tree indexes keep operations memory-resident with O(log N) page lookups.

---

## 3. Interview Defense Talking Points

- **Q: How does this pipeline handle 100x data volume?**
  *"We use PostgreSQL's native streaming `COPY` protocol via `psycopg`, achieving **1,638,162 rows/second**. At 100x volume (millions of rows), we bypass individual insert round-trips and maintain composite B-tree indexes on foreign keys (`company_id`, `student_id`) and temporal columns (`applied_at`, `offer_date`), eliminating full table scans."*

- **Q: What did EXPLAIN (ANALYZE, BUFFERS) reveal about your indexes?**
  *"Without indexes, PostgreSQL must perform sequential heap scans over all relation pages. By indexing `applications(student_id)`, PostgreSQL uses an index scan that reduces execution time by **3.8x** and reduces shared buffer page hits by **14.9x**."*
