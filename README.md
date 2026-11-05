# EDI Reconciliation Tool

Content-level reconciliation of EDI documents across the full PO lifecycle — every mismatch surfaced as a dollar-ranked exception.

**Live:** https://reconcile.lailarallc.com

## What it does

EDI acknowledgments confirm that documents arrived; nobody checks that their contents agree. This pipeline reconciles what the documents actually say — quantities, prices, item identity — across the 850/856/810/820 lifecycle and ranks every discrepancy by dollar impact.

- Generates a synthetic X12 corpus for three trading partners (Walmart, UNFI, KeHE) from Cinderhaven canonical orders, injects controlled discrepancies, and records each injection in a ledger
- Parses 850/856/810/820/852/997 documents into Postgres staging tables
- Matches documents across the PO lifecycle via multi-path key resolution in dbt, then surfaces content mismatches as dollar-ranked exceptions
- Validates matching-engine recall against the injected-discrepancy ledger — the pipeline proves it catches what it planted
- Serves a FastAPI dashboard: exception queue, 997 acknowledgment status, D3 PO lifecycle visual, and a failure-pattern catalog covering 7 exception classes

![Exception Dashboard](screenshots/Exception_Dashboard.png)

## Why it matters

For a specialty food brand trading EDI with three or more partners, content-level mismatches leak revenue and accumulate chargebacks silently: a 997 says "received," while the invoice underneath disagrees with the PO by a case count or a unit price. Dollar-ranking the exception queue means the team works the highest-impact discrepancies first instead of triaging by document age. The built-in recall validation matters for trust — the tool measures itself against a known ledger of planted errors rather than asserting accuracy.

### Cinderhaven context

Built on the Cinderhaven synthetic dataset — a ~$25M specialty food brand, 50 SKUs across 5 product lines and 6 contracted retailers. Data is synthetic; methodology and deliverables are real. Canonical baseline: 50 SKUs · 5 product lines (AS·PS·SC·DG·SB) · 6 retailers (national mass retailer · club retailer · natural grocer · regional natural grocer · conventional grocer · Regional Group) · 10 channels (6 retail + distributor A · distributor B · distributor C + DTC). Scoped to the three EDI trading partners (national mass retailer, distributor A, distributor B).

## Quick start

```
git clone https://github.com/MsShawnP/edi-reconciliation-tool.git
cd edi-reconciliation-tool
pip install -r requirements-dev.txt   # runtime-only: requirements.txt
cp .env.example .env                  # set DATABASE_URL

make all     # corpus -> parse -> transform -> validate
make serve   # dashboard at http://localhost:8000
make test    # pytest suite
```

Individual pipeline stages: `make corpus`, `make parse`, `make transform` (dbt deps/seed/run), `make validate`, `make clean`. Requires a running Postgres with the Cinderhaven canonical schema — see the cinderhaven-data-platform Docker setup.

## Tech stack

- Python 3.13 — corpus generator, X12 parsing, loader, validation
- Postgres (psycopg2) — staging and mart schemas
- dbt (dbt-postgres) — matching models, staging + marts
- FastAPI + Jinja2 + uvicorn — dashboard
- D3.js — PO lifecycle visual
- pytest — unit tests plus integration tests (integration requires `DATABASE_URL`)
- Docker / Fly.io — deployment

## Project structure

```
corpus/      Synthetic X12 generator, loader, recall validation
parser/      X12 parsing (models.py, x12_parser.py)
transforms/  dbt project — staging models, marts, seeds
dashboard/   FastAPI app, routes, templates, static assets
tests/       pytest suite (parser, generator, loader, matching, dashboard, validate)
screenshots/ Dashboard, failure-pattern catalog, PO lifecycle visuals
docs/        Findings and plans
```

## License

MIT

---

Built by [Lailara LLC](https://lailarallc.com) — data hygiene and analytics consulting for specialty food brands scaling into national retail.
