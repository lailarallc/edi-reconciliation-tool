# EDI Reconciliation Tool — Pipeline Orchestration
#
# Run the full pipeline end-to-end:
#   make all
#
# Or step by step:
#   make corpus    — generate synthetic X12 corpus
#   make parse     — parse X12 files into staging tables
#   make transform — run dbt models (staging + marts)
#   make validate  — check matching engine recall vs. discrepancy ledger
#   make serve     — start the FastAPI dashboard

.PHONY: all corpus parse transform validate serve clean help

PYTHON     := python
DBT        := dbt
DBT_DIR    := transforms
CORPUS_OUT := corpus/output

# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

all: corpus parse transform validate
	@echo ""
	@echo "Pipeline complete. Run 'make serve' to start the dashboard."

# ---------------------------------------------------------------------------
# Individual targets
# ---------------------------------------------------------------------------

corpus:
	@echo "==> Generating synthetic X12 corpus..."
	$(PYTHON) -m corpus.generator \
		--output $(CORPUS_OUT) \
		--seed 42
	@echo "    Corpus written to $(CORPUS_OUT)/"

parse:
	@echo "==> Parsing X12 files into Postgres staging tables..."
	$(PYTHON) -m corpus.loader \
		--input $(CORPUS_OUT) \
		--schema edi_staging
	@echo "    Staging tables populated."

transform:
	@echo "==> Running dbt models..."
	$(PYTHON) corpus/prod_guard.py $${POSTGRES_HOST:-localhost}:$${POSTGRES_PORT:-5432}
	cd $(DBT_DIR) && $(DBT) deps
	cd $(DBT_DIR) && $(DBT) seed
	cd $(DBT_DIR) && $(DBT) run
	@echo "    Marts populated."

validate:
	@echo "==> Validating matching engine against discrepancy ledger..."
	$(PYTHON) -m corpus.validate \
		--ledger $(CORPUS_OUT)/discrepancy_ledger.csv \
		--schema edi_marts
	@echo "    Validation complete."

serve:
	@echo "==> Starting EDI Reconciliation Dashboard..."
	uvicorn dashboard.app:app --reload --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

clean:
	@echo "==> Cleaning generated corpus output..."
	rm -rf $(CORPUS_OUT)
	@echo "    Done."

test:
	$(PYTHON) -m pytest tests/ -v

help:
	@echo ""
	@echo "EDI Reconciliation Tool — Available make targets:"
	@echo ""
	@echo "  make all        Run full pipeline (corpus → parse → transform → validate)"
	@echo "  make corpus     Generate synthetic X12 corpus (Walmart, UNFI, KeHE)"
	@echo "  make parse      Parse X12 files into Postgres staging tables"
	@echo "  make transform  Run dbt seed + dbt run (staging and marts)"
	@echo "  make validate   Check matching engine recall vs. discrepancy ledger"
	@echo "  make serve      Start the FastAPI dashboard at http://localhost:8000"
	@echo "  make test       Run pytest test suite"
	@echo "  make clean      Remove corpus/output/ (regenerate with 'make corpus')"
	@echo ""
	@echo "Prerequisites: DATABASE_URL set, Postgres running, dbt profile configured."
	@echo "See .env.example for required environment variables."
	@echo ""
