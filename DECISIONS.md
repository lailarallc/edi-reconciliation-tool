# edi-reconciliation-tool — Decisions Log

Permanent record of choices that should survive session turnover.
If a decision is reversed, strike it through and add the replacement
below — don't delete.

---

## Format

Each entry:
- **Date** — when decided
- **Decision** — one sentence, imperative voice
- **Why** — the reasoning, including what was tried and rejected
- **Scope** — what this applies to (file, chunk, deliverable, or "global")
- **Do not** — explicit anti-instructions, if any

---

## Data Integrity

### 2026-07-13 — Derive all partner invoice numbers from PO number, not ISA counter
- **Why:** ISA counter resets per `generate()` chunk call. With 17–51 chunks per partner, invoice numbers collided — `payment_agg` summed payments across all collisions, inflating `short_pay` from $440K to $17M. The national mass retailer already used PO-derived invoice numbers; distributor A and distributor B now match.
- **Scope:** `corpus/generator/partners/unfi.py`, `corpus/generator/partners/kehe.py`
- **Do not:** Use ISA counter for any identifier that participates in cross-document joins (invoice numbers, PO references). ISA control numbers for X12 envelopes are fine — they're unique within a single interchange.

---

## Architecture & Pipeline

### 2026-06-10 — Use Makefile + Python script for orchestration, not Dagster
- **Why:** Dagster is a full platform (daemon, scheduler, UI) that adds setup complexity without adding value to the portfolio story. The pipeline is linear (generate → parse → stage → match → serve). A Makefile is more transparent for a technical reviewer to follow.
- **Scope:** Global pipeline orchestration
- **Do not:** Add Dagster or any other orchestration platform in v1. If the pipeline grows to need scheduling, that decision gets its own entry.

### 2026-06-10 — Use multi-path key resolution (PO → ASN → Invoice), not a single PO anchor
- **Why:** In real EDI traffic, 820s (and sometimes 810s) arrive without PO references — especially from distributors like UNFI. A PO-only anchor would drop real-world documents. The three-tier fallback (PO Number primary, ASN/BOL secondary, Invoice Number tertiary) mirrors what a real engagement would need and is more defensible to technical evaluators. User confirmed: "in real life it is possible you don't have the PO so you have to look at the docs."
- **Scope:** `int_document_links.sql`, matching key schema globally
- **Do not:** Use bilateral match tables (850↔856, 856↔810 separately) — rejected in favor of the link-table approach.

### 2026-06-10 — Put matching logic in dbt (SQL), not Python
- **Why:** Deliberate portfolio signal — shows platform-integrated data engineering, not just scripting. Python layer handles parsing and loading only. Match logic in SQL is also easier for a technical evaluator to audit.
- **Scope:** U5 and all mart models
- **Do not:** Move match logic into Python for convenience.

### 2026-06-10 — Treat the discrepancy ledger as a first-class deliverable, not a test fixture
- **Why:** The ledger records exactly what was injected into the synthetic corpus, allowing the matching engine to be scored: found / missed / false-positive. This is the equivalent of the trade-spend diagnostic's 59-check pattern. It demonstrates to a potential client how the engine would be validated on their real data.
- **Scope:** U1, U2, U5 validation script
- **Do not:** Treat the ledger as internal-only scaffolding to be discarded after testing.

---

## Data & Schema

### 2026-06-10 — Use Postgres on the Cinderhaven platform, not DuckDB
- **Why:** The Cinderhaven data platform is live and is the SSOT for ~20 projects. Using Postgres keeps the matching models platform-integrated, which is part of the portfolio story. DuckDB was considered only when platform availability was uncertain; that uncertainty was resolved when user confirmed "it is the SSOT datasource for like 20 projects now."
- **Scope:** Database choice globally
- **Do not:** Introduce DuckDB as a "simpler" alternative.

### 2026-06-10 — Generate corpus from Cinderhaven canonical data, not independently random data
- **Why:** Dollar values in the exception mart must tie to canonical Cinderhaven revenue figures to be internally consistent with the platform story. Fully random synthetic data would not serve the Cinderhaven platform coherence narrative.
- **Scope:** Corpus generator (U1, U2)
- **Do not:** Generate documents with arbitrary dollar amounts. Pull from `CINDERHAVEN_CANONICAL.md` and register the new corpus seed there.

### 2026-06-10 — Store UoM conversion factors as a dbt seed CSV, not hardcoded in SQL or Python
- **Why:** Auditable, version-controlled, easily extended per engagement. A domain expert can open the CSV and verify the values. Hardcoded conversion factors are invisible and brittle.
- **Scope:** `transforms/seeds/uom_conversions.csv`
- **Do not:** Hardcode eaches/cases/inner-pack ratios in Python or SQL.

---

## Visualization

### 2026-06-10 — D3 lifecycle visual is a standalone SVG at LinkedIn dimensions (1200×628px) that also embeds in the dashboard
- **Why:** The visual is the primary distribution mechanism (LinkedIn hook). It must work without the dashboard being live. Embedding in the dashboard is secondary.
- **Scope:** U7, `visuals/po_lifecycle.svg`
- **Do not:** Make the lifecycle visual depend on the dashboard being deployed to share it.

---

## Output Formats

### 2026-06-10 — Dashboard layout: dollar-ranked exceptions above the fold; 997 ACK status as a clearly separated secondary layer labeled "For EDI/Ops Teams"
- **Why:** The portfolio piece is positioned at CFO/controller audiences. Revenue leakage and chargeback risk are the hook. 997 is operational, not revenue-facing; it belongs in a secondary layer so it doesn't dilute the CFO signal. Ordering is non-negotiable.
- **Scope:** U6, dashboard layout
- **Do not:** Merge 997 status into the main exception list. Keep it visually distinct and clearly labeled.

---

## Writing & Voice

### 2026-06-10 — Failure pattern catalog targets EDI coordinators and controllers, not technical implementers
- **Why:** The catalog is a deliverable for the prospect/client audience, not a developer reference. No jargon left unexplained. One sentence on what it is, root cause, detection logic, dollar formula, fix.
- **Scope:** U8, `catalog/failure_patterns.md`

---

## Scope

### 2026-06-10 — Synthetic corpus only in v1; no real-data client upload path
- **Why:** The portfolio piece uses synthetic data to prove the concept and position Lailara to run real-data engagements as paid work. User clarified: "the brief uses synthetic to show/prove the concept so people hire me to work on their real data." Real-data ingestion is built during a paid engagement, not in the portfolio piece.
- **Scope:** Global scope boundary
- **Do not:** Add a file upload UI or real-data ingestion path in v1.

### 2026-06-10 — All five deliverables required in v1; no deadline
- **Why:** User confirmed all five must land: exception dashboard, D3 lifecycle visual, failure pattern catalog, synthetic X12 corpus + generator, matching SQL/dbt models. No prioritization or staged drop. "There is no deadline."
- **Scope:** PLAN.md arc, definition of done
- **Do not:** Ship with any of the five deliverables missing.

### 2026-06-10 — Include 997 acknowledgment tracking in v1
- **Why:** User confirmed: "i want to include it." 997 is part of the complete reconciliation story, even though it is ops-facing rather than CFO-facing.
- **Scope:** R8, U5 (`int_997_match.sql`), dashboard secondary layer

---

## EDI Document Conventions

### 2026-06-13 — Synthetic corpus stores ISA interchange control in AK1 of 997 ACKs, not GS group control
- **Why:** ISA counters start at 1001/2001/3001 per partner; GS counters start at 1. The dbt join in `int_997_match.sql` is `isa_control_number::integer = acknowledged_gs_control`. Storing GS control in AK1 means the values are always ~1000 apart and the join produces zero matches. The X12 standard says AK1 should carry GS group control, but our synthetic corpus avoids maintaining a separate `gs_control_number` staging column by storing ISA control instead. The comment in `int_997_match.sql` documents this deviation. Real-world deployments must store and join on GS control.
- **Scope:** `corpus/generator/partners/walmart.py`, `unfi.py`, `kehe.py`; `transforms/models/marts/int_997_match.sql`
- **Do not:** Store GS group control in `_make_997()` calls in the synthetic generators — they produce zero 997 matches. Do not remove the comment in `int_997_match.sql` that explains the deviation.

---

## Corpus Generator Conventions

### 2026-06-10 — CASE_PACK dict in x12_utils.py is a maintained copy of the FROZEN seed_config.py block
- **Why:** Generators can't cross-import from cinderhaven-data-platform. The FROZEN block in seed_config is stable by definition (editing it re-baselines the entire portfolio). Copying it into x12_utils.py is safe; drift risk is low. If the FROZEN block ever changes, x12_utils.CASE_PACK must be updated in the same PR.
- **Scope:** `corpus/generator/x12_utils.py`, all partner generators
- **Do not:** Import seed_config.py from across repos. Do not derive case_pack_qty from the Postgres schema — it's not guaranteed to be present on all partners' order_lines tables.

### 2026-06-13 — Cascade-aware validation contract (Option A): preserve single-status mart semantics; express expected-surface map in corpus/validate.py
- **Why:** Finding #16 identified five structural causes of ledger↔mart divergence. Option A keeps the matching engine's single-status CASE semantics (a line failing an earlier check never reaches later checks — this mirrors real four-way match triage and is honest). The expected-surface map in `corpus/validate.py` documents explicitly which ledger classes surface as which mart classes (e.g., shipped_not_invoiced injection beyond tolerance → qty_mismatch in mart; mapping_drift → ordered_not_asnd). Option B (multi-status mart) would double-count dollar impact and require rewriting every mart consumer. Option C (weaker injector) would make the recall claim circular. Option D (document-only) leaves `make validate` broken.
- **Scope:** `corpus/validate.py`, `corpus/generator/injector.py`, `transforms/models/marts/` (unchanged), dashboard footnotes
- **Do not:** Replace the CASE precedence in `int_four_way_match.sql` with multi-status rows (Option B) without a new DECISIONS.md entry and a dashboard aggregation rewrite.

### 2026-06-10 — Generators produce clean documents (empty ledger); Injector owns all discrepancy injection
- **Why:** Separating generation from injection keeps the generators deterministic and testable in isolation. Structural partner quirks (Walmart CA→EA UoM, UNFI missing PRF on 820, KeHE multi-HL) are built into the generators as realistic document patterns but do NOT themselves write to the ledger. The Injector applies genuine mismatches (off-by-1 quantities, short payments, removed ASNs) and records them. This means the ground truth is entirely controlled by the Injector, not scattered across generators.
- **Scope:** `corpus/generator/partners/*.py`, `corpus/generator/injector.py`
- **Do not:** Have generators write to the ledger. Do not treat generator structural quirks as discrepancies — they are expected behavior that the matching engine's UoM conversion and key resolution must handle, not find as exceptions.

---

## Python Conventions

### 2026-06-10 — Use TYPE_CHECKING guards in package __init__.py; callers import from submodules directly
- **Why:** Eager imports from submodules in `__init__.py` cause a RuntimeWarning in Python 3.12+ when running a submodule as `__main__` (e.g., `python -m corpus.generator.base`). The parent package is imported first, which imports the submodule, which then can't be set as `__main__`. Moving submodule imports under `TYPE_CHECKING` eliminates the warning. Callers import directly from the submodule path (`from corpus.generator.base import CanonicalOrder`), which is more explicit anyway.
- **Scope:** All `__init__.py` files in this project
- **Do not:** Import from sibling submodules at the top level of an `__init__.py`. Define Protocols, dataclasses, and type aliases inline; reference submodule types in `TYPE_CHECKING` blocks only.

### 2026-06-10 — Starlette 1.0+: request is first arg to TemplateResponse, not a context dict key
- **Why:** Starlette 1.0.0 changed `TemplateResponse(name, context)` to `TemplateResponse(request, name, context)`. The old signature silently passes the context dict as the template name to Jinja2, which raises `TypeError: unhashable type: 'dict'` in the LRU cache at request time (not import time — the app starts fine). All five dashboard route handlers were updated. Starlette 1.0+ automatically injects `request` into the template context from the first arg.
- **Scope:** All `templates.TemplateResponse(...)` calls in `dashboard/app.py` and any future route files.
- **Do not:** Put `request` inside the context dict. Pass it as the first positional argument: `templates.TemplateResponse(request, "template.html", {...})`.

---

## Deployment

### 2026-06-11 — Use flycast internal hostname + manual secret for cross-app Postgres on Fly.io; skip `fly postgres attach`
- **Why:** `fly postgres attach` authenticates as the Postgres superuser, which requires the cluster's internal superuser password — not the app-user credentials. On cinderhaven-db, these differ. `fly secrets set DATABASE_URL="postgresql://user:pass@<app>.flycast:5432/db"` achieves the same result without superuser auth. The `.flycast` hostname is Fly's internal DNS — only reachable within the same Fly org's private network, so credentials aren't exposed publicly.
- **Scope:** Any future Fly.io deployment that connects to cinderhaven-db or another shared Fly Postgres cluster
- **Do not:** Use `fly postgres attach` on cinderhaven-db — it will fail. Do not use the public `.fly.dev` hostname in DATABASE_URL — it routes through the public internet and would require TLS configuration.

---

### 2026-06-16 — No pricing text in any web-served file
- **Why:** `dashboard/static/po_lifecycle.svg` contained "$18K–$30K engagement for specialty food brands" and was publicly accessible at `/static/po_lifecycle.svg`. Pricing is private-only — it belongs in internal briefs, not on the live site. Found and removed during round 2 review.
- **Scope:** All files under `dashboard/static/`, `dashboard/templates/`, and any other directory served by FastAPI
- **Do not:** Put engagement pricing, rate cards, or fee ranges in any file that the web server can serve. Keep pricing in project briefs and planning docs only.

---

## Dashboard Conventions

### 2026-06-16 — Two-layer sanity guard for lifecycle visual: server-side dollar cap + client-side validation fallback
- **Why:** The 820 corpus generator inflates PAID because RMR segments are at line-item grain (documented in `docs/finding-820-rmr-grain.md`). Rather than wait for the generator fix, the dashboard defends itself: (1) `lifecycle.py` caps `total_paid_dollars` at `total_invoiced_dollars` before computing case-equiv, and (2) `lifecycle.js` runs `isValid()` — if PAID > INVOICED after server processing, falls back to canonical data with `source: "validation-fallback"` subtitle. This pattern is correct even after the generator is fixed — PAID > INVOICED is structurally impossible in a real four-way match, so the guard catches any future data issue.
- **Scope:** `dashboard/routes/lifecycle.py`, `dashboard/static/js/lifecycle.js`
- **Do not:** Remove the server-side cap or client-side guard after fixing the 820 generator — they protect against any future data integrity issue, not just this one bug.

---

## Credentials

### 2026-07-20 — SU_PASSWORD in cinderhaven-data-platform/.env is the authoritative credential for the postgres role on cinderhaven-db
- **Why:** POSTGRES_PASSWORD drifted from the live password (spinrate went down with 503). SU_PASSWORD is what Fly uses to set the superuser password — it's always current. POSTGRES_PASSWORD, OPERATOR_PASSWORD, and DATABASE_URL must be manually synced to match SU_PASSWORD whenever it changes.
- **Scope:** All repos and Fly apps that connect to cinderhaven-db as the postgres user
- **Do not:** Trust POSTGRES_PASSWORD as authoritative without verifying it matches SU_PASSWORD. When rotating credentials, update SU_PASSWORD first, then sync the others.

---

## Reversed / Superseded

When a decision is overturned:
1. Strike through the original entry above (don't delete)
2. Add a new entry below with the replacement decision
3. Note the link in both directions

This preserves the history of why something is the way it is.

---

### 2026-06-17 — Short-pay gap is dollar-denominated, not case-denominated
- **Why:** The `paid` case count is reverse-engineered from `total_paid_dollars / avg_unit_price`. SKU price variation means the case-equivalent can round to equal invoiced even when the dollar shortfall is real. Displaying cases for this gap is misleading.
- **Scope:** PO lifecycle visual, any future display of the invoiced→paid gap
- **Do not:** Revert to case-count delta for the short-pay callout pill
