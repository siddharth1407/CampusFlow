.PHONY: help setup up down generate run report test lint format demo clean dashboard benchmark

PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest
RUFF ?= .venv/bin/ruff
BATCH ?= batch_001

help: ## Show this help message
	@echo "CampusFlow - Campus Placement Data Platform"
	@echo "Usage: make [target]"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Create virtualenv and install dependencies
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env; fi

up: ## Start PostgreSQL via Docker and initialize database schemas
	docker compose up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@until docker compose exec postgres pg_isready -U campusflow -d campusflow_db > /dev/null 2>&1; do \
		sleep 1; \
	done
	@echo "PostgreSQL is ready! Applying schema migrations..."
	$(PYTHON) -c "from src.db import init_db; init_db()"

down: ## Stop Docker containers and clean volumes
	docker compose down -v

generate: ## Generate synthetic batches with reproducible seed
	$(PYTHON) -m src.generate_data --seed 42 --students 1000 --out data/sample

run: ## Run pipeline for a specific batch (e.g. make run BATCH=batch_001)
	$(PYTHON) -m src.pipeline --batch $(BATCH)

report: ## Print analytics reporting views and pipeline health summary
	$(PYTHON) -m src.report

dashboard: ## Launch interactive Streamlit web dashboard
	$(PYTHON) -m streamlit run src/dashboard.py --server.port 8501

benchmark: ## Run ingestion scale benchmark and EXPLAIN ANALYZE profiling
	$(PYTHON) -m src.benchmark

test: ## Run unit and integration tests with coverage

	$(PYTEST) tests/

lint: ## Run ruff linter
	$(RUFF) check src/ config/ tests/

format: ## Autoformat code with ruff
	$(RUFF) format src/ config/ tests/

clean: ## Clean cache files and artifacts
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +

demo: ## One-command complete end-to-end demonstration
	@echo "\n========================================================"
	@echo "           CAMPUSFLOW END-TO-END DEMO"
	@echo "========================================================"
	@make up
	@make generate
	@echo "\n>>> 1. Processing Batch 001 (Baseline Full Ingestion & Quarantine)..."
	@make run BATCH=batch_001
	@echo "\n>>> 2. Processing Batch 002 (Incremental Updates, Late Arrivals & New Records)..."
	@make run BATCH=batch_002
	@echo "\n>>> 3. Processing Batch 003 (Exact Replay Proving Idempotency: Zero Net Changes)..."
	@make run BATCH=batch_003
	@echo "\n>>> 4. Running Automated Pytest Verification Suite..."
	@make test
	@echo "\n>>> 5. Generating Analytics & Pipeline Health Summary Report..."
	@make report
	@echo "\n========================================================"
	@echo "           DEMO COMPLETED SUCCESSFULLY!"
	@echo "========================================================\n"

