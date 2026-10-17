"""Synthetic placement data generator with reproducible seeding and fault injection.

Produces CSV batches (batch_001, batch_002, batch_003, batch_004) and a
ground-truth faults_manifest.json detailing injected errors per batch.
"""

import argparse
import csv
import json
import random
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DEPARTMENTS = [
    "Computer Science",
    "Electronics",
    "Electrical",
    "Mechanical",
    "Civil",
    "Chemical",
    "Design",
    "Physics",
    "Mathematics",
    "Biosciences",
]

SECTORS = [
    "Software",
    "Fintech",
    "Consulting",
    "Core Engineering",
    "Analytics",
    "Product",
    "Hardware",
]

BASE_COMPANIES = [
    ("COMP001", "Google", "Software", ["google", "Google LLC", " google inc. "]),
    (
        "COMP002",
        "Microsoft",
        "Software",
        ["microsoft", "Microsoft Corp", " MICROSOFT CORPORATION "],
    ),
    ("COMP003", "Amazon", "Software", ["amazon", "Amazon Web Services", "aws"]),
    ("COMP004", "Apple", "Hardware", ["apple", "Apple Inc.", " apple  "]),
    ("COMP005", "Goldman Sachs", "Fintech", ["goldman sachs", "GS", " Goldman Sachs India "]),
    ("COMP006", "JPMorgan Chase", "Fintech", ["jpmorgan", "JP Morgan", "JPMC"]),
    ("COMP007", "Morgan Stanley", "Fintech", ["morgan stanley", "Morgan Stanley Asia"]),
    ("COMP008", "McKinsey & Company", "Consulting", ["mckinsey", "McKinsey & Company"]),
    ("COMP009", "Boston Consulting Group", "Consulting", ["bcg", "Boston Consulting Group"]),
    ("COMP010", "Bain & Company", "Consulting", ["bain", "Bain & Company"]),
    ("COMP011", "Qualcomm", "Hardware", ["qualcomm", "Qualcomm India"]),
    ("COMP012", "NVIDIA", "Hardware", ["nvidia", "Nvidia Corp", " NVIDIA "]),
    ("COMP013", "Intel", "Hardware", ["intel", "Intel Corporation"]),
    ("COMP014", "Texas Instruments", "Core Engineering", ["texas instruments", "TI"]),
    ("COMP015", "Samsung", "Product", ["samsung", "Samsung R&D"]),
    ("COMP016", "Uber", "Product", ["uber", "Uber Technologies"]),
    ("COMP017", "Flipkart", "Product", ["flipkart", "Flipkart Internet"]),
    ("COMP018", "Tata Consultancy Services", "Software", ["tcs", "Tata Consultancy Services"]),
    ("COMP019", "Infosys", "Software", ["infosys", "Infosys Ltd"]),
    ("COMP020", "Oracle", "Software", ["oracle", "Oracle India"]),
]

STATUSES = ["applied", "shortlisted", "interviewed", "offered", "rejected", "withdrawn"]


class DataGenerator:
    def __init__(self, seed: int = 42, base_students: int = 1000):
        self.seed = seed
        self.rng = random.Random(seed)
        self.base_students = base_students
        self.current_date = date(2025, 4, 1)

    def _random_cgpa(self) -> float:
        """Generate realistic CGPA between 6.0 and 9.9."""
        return round(self.rng.triangular(6.0, 9.9, 8.2), 2)

    def _random_salary(self, sector: str) -> float:
        """Generate realistic compensation in LPA based on sector."""
        medians = {
            "Software": 28.0,
            "Fintech": 32.0,
            "Consulting": 22.0,
            "Product": 26.0,
            "Hardware": 20.0,
            "Analytics": 18.0,
            "Core Engineering": 15.0,
        }
        med = medians.get(sector, 18.0)
        val = self.rng.gauss(med, med * 0.25)
        return max(5.0, round(val, 2))

    def generate_all(self, output_dir: Path) -> dict[str, Any]:
        """Generate all batches and write faults_manifest.json."""
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {
            "seed": self.seed,
            "generated_at": datetime.now().isoformat(),
            "batches": {},
        }

        # 1. Batch 001 - Initial Full Load
        b1_dir = output_dir / "batch_001"
        b1_manifest, b1_data = self._generate_batch_001(b1_dir)
        manifest["batches"]["batch_001"] = b1_manifest

        # 2. Batch 002 - Incremental Load with Changes and Late Arrivals
        b2_dir = output_dir / "batch_002"
        b2_manifest, b2_data = self._generate_batch_002(b2_dir, b1_data)
        manifest["batches"]["batch_002"] = b2_manifest

        # 3. Batch 003 - Exact Replay of Batch 002 for Idempotency
        b3_dir = output_dir / "batch_003"
        b3_manifest = self._generate_batch_003(b3_dir, b2_dir, b2_manifest)
        manifest["batches"]["batch_003"] = b3_manifest

        # 4. Batch 004 - Schema Drift Failure Demo
        b4_dir = output_dir / "batch_004"
        b4_manifest = self._generate_batch_004(b4_dir)
        manifest["batches"]["batch_004"] = b4_manifest

        manifest_file = output_dir / "faults_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest

    def _generate_batch_001(self, out_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        out_dir.mkdir(parents=True, exist_ok=True)
        faults: dict[str, int] = {
            "MISSING_PK": 0,
            "MISSING_REQUIRED": 0,
            "INVALID_YEAR": 0,
            "INVALID_DATE": 0,
            "DATE_ORDER_VIOLATION": 0,
            "ORPHAN_STUDENT": 0,
            "ORPHAN_COMPANY": 0,
            "INVALID_STATUS": 0,
            "INVALID_COMPENSATION": 0,
            "EXACT_DUPLICATE_ROWS": 0,
        }

        # Generate Students
        students = []
        for i in range(1, self.base_students + 1):
            s_id = f"STU_{i:05d}"
            dept = self.rng.choice(DEPARTMENTS)
            grad_year = self.rng.choice([2024, 2025, 2026])
            cgpa = self._random_cgpa()
            students.append(
                {
                    "student_id": s_id,
                    "department": dept,
                    "graduation_year": grad_year,
                    "cgpa": cgpa,
                }
            )

        # Inject Faults in Students:
        # 1. Missing PK
        students.append(
            {
                "student_id": "",
                "department": "Computer Science",
                "graduation_year": 2025,
                "cgpa": 8.5,
            }
        )
        faults["MISSING_PK"] += 1

        # 2. Missing Department
        students.append(
            {
                "student_id": f"STU_{len(students) + 1:05d}",
                "department": "",
                "graduation_year": 2025,
                "cgpa": 8.0,
            }
        )
        faults["MISSING_REQUIRED"] += 1

        # 3. Invalid Graduation Year
        students.append(
            {
                "student_id": f"STU_{len(students) + 1:05d}",
                "department": "Mechanical",
                "graduation_year": 1899,
                "cgpa": 7.5,
            }
        )
        faults["INVALID_YEAR"] += 1

        # Generate Companies
        companies = []
        for c_id, canonical, sector, aliases in BASE_COMPANIES:
            # Randomly use alias or messy name in CSV
            c_name = self.rng.choice([canonical] + aliases)
            companies.append(
                {
                    "company_id": c_id,
                    "company_name": c_name,
                    "sector": sector,
                }
            )

        # Inject Fault in Companies:
        companies.append({"company_id": "", "company_name": "Ghost Tech", "sector": "Software"})
        faults["MISSING_PK"] += 1

        companies.append({"company_id": "COMP999", "company_name": "", "sector": "Fintech"})
        faults["MISSING_REQUIRED"] += 1

        # Generate Applications
        applications = []
        app_counter = 1
        valid_students = [
            s["student_id"] for s in students if s["student_id"] and s["department"] and s["graduation_year"] >= 2020
        ]
        valid_companies = [c["company_id"] for c in companies if c["company_id"] and c["company_name"]]

        app_date_start = date(2024, 8, 1)

        for s_id in valid_students:
            num_apps = self.rng.randint(1, 6)
            chosen_companies = self.rng.sample(valid_companies, min(num_apps, len(valid_companies)))
            for c_id in chosen_companies:
                app_id = f"APP_{app_counter:06d}"
                app_counter += 1
                app_days = self.rng.randint(0, 180)
                applied_date = app_date_start + timedelta(days=app_days)

                # Realistic status progression
                roll = self.rng.random()
                if roll < 0.40:
                    status = "applied"
                elif roll < 0.65:
                    status = "shortlisted"
                elif roll < 0.85:
                    status = "interviewed"
                elif roll < 0.95:
                    status = "offered"
                else:
                    status = "rejected"

                applications.append(
                    {
                        "application_id": app_id,
                        "student_id": s_id,
                        "company_id": c_id,
                        "applied_at": applied_date.isoformat(),
                        "status": status,
                    }
                )

        # Inject Faults in Applications
        # 1. Missing PK
        applications.append(
            {
                "application_id": "",
                "student_id": valid_students[0],
                "company_id": valid_companies[0],
                "applied_at": "2024-10-01",
                "status": "applied",
            }
        )
        faults["MISSING_PK"] += 1

        # 2. Invalid Date format/impossible date
        applications.append(
            {
                "application_id": f"APP_{app_counter:06d}",
                "student_id": valid_students[1],
                "company_id": valid_companies[0],
                "applied_at": "2024-13-45",
                "status": "applied",
            }
        )
        app_counter += 1
        faults["INVALID_DATE"] += 1

        # 3. Future date
        applications.append(
            {
                "application_id": f"APP_{app_counter:06d}",
                "student_id": valid_students[2],
                "company_id": valid_companies[1],
                "applied_at": "2099-01-01",
                "status": "applied",
            }
        )
        app_counter += 1
        faults["INVALID_DATE"] += 1

        # 4. Orphan Student
        applications.append(
            {
                "application_id": f"APP_{app_counter:06d}",
                "student_id": "STU_ORPHAN_99999",
                "company_id": valid_companies[0],
                "applied_at": "2024-10-15",
                "status": "applied",
            }
        )
        app_counter += 1
        faults["ORPHAN_STUDENT"] += 1

        # 5. Orphan Company
        applications.append(
            {
                "application_id": f"APP_{app_counter:06d}",
                "student_id": valid_students[3],
                "company_id": "COMP_ORPHAN_999",
                "applied_at": "2024-10-15",
                "status": "applied",
            }
        )
        app_counter += 1
        faults["ORPHAN_COMPANY"] += 1

        # 6. Invalid Status
        applications.append(
            {
                "application_id": f"APP_{app_counter:06d}",
                "student_id": valid_students[4],
                "company_id": valid_companies[1],
                "applied_at": "2024-11-01",
                "status": "Selected!!",
            }
        )
        app_counter += 1
        faults["INVALID_STATUS"] += 1

        # 7. Exact duplicate row
        applications.append(applications[0].copy())
        faults["EXACT_DUPLICATE_ROWS"] += 1

        # Generate Offers
        offers = []
        offer_counter = 1
        comp_sector_map = {c["company_id"]: c["sector"] for c in companies if c["company_id"]}

        for app in applications:
            if app["status"] == "offered" and app["application_id"] and app["student_id"] in valid_students:
                off_id = f"OFF_{offer_counter:05d}"
                offer_counter += 1
                app_dt = date.fromisoformat(app["applied_at"])
                off_date = app_dt + timedelta(days=self.rng.randint(7, 45))
                sec = comp_sector_map.get(app["company_id"], "Software")
                comp = self._random_salary(sec)
                offers.append(
                    {
                        "offer_id": off_id,
                        "student_id": app["student_id"],
                        "company_id": app["company_id"],
                        "compensation_lpa": comp,
                        "offer_date": off_date.isoformat(),
                        "_applied_date": app_dt,
                    }
                )

        # Inject Faults in Offers
        # 1. Missing PK
        offers.append(
            {
                "offer_id": "",
                "student_id": valid_students[0],
                "company_id": valid_companies[0],
                "compensation_lpa": 24.0,
                "offer_date": "2024-12-01",
            }
        )
        faults["MISSING_PK"] += 1

        # 2. Date order violation (offer before application)
        app_target = next(
            a for a in applications if a.get("application_id") and a.get("status") in STATUSES and a.get("applied_at")
        )
        offers.append(
            {
                "offer_id": f"OFF_{offer_counter:05d}",
                "student_id": app_target["student_id"],
                "company_id": app_target["company_id"],
                "compensation_lpa": 25.0,
                "offer_date": "2020-01-01",  # Before application date
            }
        )
        offer_counter += 1
        faults["DATE_ORDER_VIOLATION"] += 1

        # 3. Invalid compensation (negative)
        offers.append(
            {
                "offer_id": f"OFF_{offer_counter:05d}",
                "student_id": valid_students[6],
                "company_id": valid_companies[1],
                "compensation_lpa": -15.5,
                "offer_date": "2024-12-10",
            }
        )
        offer_counter += 1
        faults["INVALID_COMPENSATION"] += 1

        # 4. Orphan student in offers
        offers.append(
            {
                "offer_id": f"OFF_{offer_counter:05d}",
                "student_id": "STU_ORPHAN_88888",
                "company_id": valid_companies[0],
                "compensation_lpa": 30.0,
                "offer_date": "2024-12-15",
            }
        )
        offer_counter += 1
        faults["ORPHAN_STUDENT"] += 1

        # Clean private helper fields
        for off in offers:
            off.pop("_applied_date", None)

        # Write files
        self._write_csv(
            out_dir / "students.csv",
            ["student_id", "department", "graduation_year", "cgpa"],
            students,
        )
        self._write_csv(out_dir / "companies.csv", ["company_id", "company_name", "sector"], companies)
        self._write_csv(
            out_dir / "applications.csv",
            ["application_id", "student_id", "company_id", "applied_at", "status"],
            applications,
        )
        self._write_csv(
            out_dir / "offers.csv",
            ["offer_id", "student_id", "company_id", "compensation_lpa", "offer_date"],
            offers,
        )

        manifest = {
            "batch_id": "batch_001",
            "total_students": len(students),
            "total_companies": len(companies),
            "total_applications": len(applications),
            "total_offers": len(offers),
            "injected_faults": faults,
        }

        batch_data = {
            "students": students,
            "companies": companies,
            "applications": applications,
            "offers": offers,
            "app_counter": app_counter,
            "offer_counter": offer_counter,
        }

        return manifest, batch_data

    def _generate_batch_002(self, out_dir: Path, prev_data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        out_dir.mkdir(parents=True, exist_ok=True)
        faults: dict[str, int] = {
            "MISSING_PK": 0,
            "MISSING_REQUIRED": 0,
            "INVALID_YEAR": 0,
            "INVALID_DATE": 0,
            "DATE_ORDER_VIOLATION": 0,
            "ORPHAN_STUDENT": 0,
            "ORPHAN_COMPANY": 0,
            "INVALID_STATUS": 0,
            "INVALID_COMPENSATION": 0,
            "EXACT_DUPLICATE_ROWS": 0,
        }

        # 1. New students
        new_students = []
        start_idx = self.base_students + 10
        for i in range(start_idx, start_idx + 200):
            new_students.append(
                {
                    "student_id": f"STU_{i:05d}",
                    "department": self.rng.choice(DEPARTMENTS),
                    "graduation_year": 2025,
                    "cgpa": self._random_cgpa(),
                }
            )

        # 2. Changed records: Take some interviewed apps from batch 1 and update status to 'offered'
        changed_apps = []
        new_offers = []
        offer_counter = prev_data["offer_counter"]

        eligible_interviewed = [
            a for a in prev_data["applications"] if a.get("status") == "interviewed" and a.get("application_id")
        ]

        # Pick 20 applications to update to offered
        for app in eligible_interviewed[:20]:
            updated_app = app.copy()
            updated_app["status"] = "offered"
            changed_apps.append(updated_app)

            # Create corresponding new offer
            off_id = f"OFF_{offer_counter:05d}"
            offer_counter += 1
            new_offers.append(
                {
                    "offer_id": off_id,
                    "student_id": app["student_id"],
                    "company_id": app["company_id"],
                    "compensation_lpa": round(self.rng.uniform(16.0, 35.0), 2),
                    "offer_date": "2025-01-20",
                }
            )

        # 3. Late arriving records: Applications from previous semester
        app_counter = prev_data["app_counter"]
        late_apps = []
        for _ in range(30):
            app_id = f"APP_{app_counter:06d}"
            app_counter += 1
            s = self.rng.choice(prev_data["students"])
            c = self.rng.choice(prev_data["companies"])
            if s.get("student_id") and c.get("company_id"):
                late_apps.append(
                    {
                        "application_id": app_id,
                        "student_id": s["student_id"],
                        "company_id": c["company_id"],
                        "applied_at": "2024-09-01",  # late arrival
                        "status": "applied",
                    }
                )

        # Combine applications
        all_b2_apps = changed_apps + late_apps

        # Inject Faults in Batch 2
        # Fault: missing company_name in companies
        new_companies = [
            {"company_id": "COMP080", "company_name": "Databricks India", "sector": "Software"},
            {"company_id": "COMP081", "company_name": "Snowflake", "sector": "Software"},
            {"company_id": "COMP082", "company_name": "", "sector": "Analytics"},  # fault
        ]
        faults["MISSING_REQUIRED"] += 1

        # Fault: invalid status in application
        all_b2_apps.append(
            {
                "application_id": f"APP_{app_counter:06d}",
                "student_id": new_students[0]["student_id"],
                "company_id": "COMP080",
                "applied_at": "2025-01-15",
                "status": "AcceptedOffer!!",  # invalid enum
            }
        )
        app_counter += 1
        faults["INVALID_STATUS"] += 1

        # Write Batch 2 files
        self._write_csv(
            out_dir / "students.csv",
            ["student_id", "department", "graduation_year", "cgpa"],
            new_students,
        )
        self._write_csv(out_dir / "companies.csv", ["company_id", "company_name", "sector"], new_companies)
        self._write_csv(
            out_dir / "applications.csv",
            ["application_id", "student_id", "company_id", "applied_at", "status"],
            all_b2_apps,
        )
        self._write_csv(
            out_dir / "offers.csv",
            ["offer_id", "student_id", "company_id", "compensation_lpa", "offer_date"],
            new_offers,
        )

        manifest = {
            "batch_id": "batch_002",
            "total_students": len(new_students),
            "total_companies": len(new_companies),
            "total_applications": len(all_b2_apps),
            "total_offers": len(new_offers),
            "changed_records_count": len(changed_apps),
            "late_arriving_count": len(late_apps),
            "injected_faults": faults,
        }

        return manifest, {"offer_counter": offer_counter, "app_counter": app_counter}

    def _generate_batch_003(self, out_dir: Path, b2_dir: Path, b2_manifest: dict[str, Any]) -> dict[str, Any]:
        """Batch 003 is an exact byte-for-byte replay of Batch 002."""
        out_dir.mkdir(parents=True, exist_ok=True)
        for fname in ["students.csv", "companies.csv", "applications.csv", "offers.csv"]:
            shutil.copy2(b2_dir / fname, out_dir / fname)

        manifest = b2_manifest.copy()
        manifest["batch_id"] = "batch_003"
        manifest["purpose"] = "Idempotency replay of batch_002"
        return manifest

    def _generate_batch_004(self, out_dir: Path) -> dict[str, Any]:
        """Batch 004 demonstrates schema drift (corrupted / missing headers)."""
        out_dir.mkdir(parents=True, exist_ok=True)

        # Normal students
        students = [{"student_id": "STU_99991", "department": "Civil", "graduation_year": 2025, "cgpa": 7.8}]
        self._write_csv(
            out_dir / "students.csv",
            ["student_id", "department", "graduation_year", "cgpa"],
            students,
        )

        # Corrupted applications: missing 'status' column completely
        apps_drift = [{"application_id": "APP_999991", "student_id": "STU_99991", "company_id": "COMP001"}]
        self._write_csv(out_dir / "applications.csv", ["application_id", "student_id", "company_id"], apps_drift)

        return {
            "batch_id": "batch_004",
            "purpose": "Schema drift failure handling demo",
            "injected_faults": {"SCHEMA_MISMATCH": 1},
        }

    @staticmethod
    def _write_csv(filepath: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic CampusFlow placement batches.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--students", type=int, default=1000, help="Base number of students")
    parser.add_argument("--out", type=str, default="data/sample", help="Output directory")

    args = parser.parse_args()
    gen = DataGenerator(seed=args.seed, base_students=args.students)
    manifest = gen.generate_all(Path(args.out))
    print(f"Data generation complete! Manifest written to {args.out}/faults_manifest.json")
    for b_id, b_info in manifest["batches"].items():
        print(f" - {b_id}: {b_info.get('total_applications', 0)} apps, faults: {b_info.get('injected_faults')}")


if __name__ == "__main__":
    main()
