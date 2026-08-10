# Client Engagement Runbook — EDI Reconciliation

How to stand up the EDI reconciliation pipeline against a **client's** EDI corpus
and Postgres warehouse. Client mode here is a runbook + a client dbt profile —
the matching models are the same; only the connection and the source schema
change.

Client data lives only in the client's warehouse and in `client-data/` /
`client-output/` locally (gitignored) — never committed, never in this repo.

---

## 1. Client dbt profile

Add a client target to `~/.dbt/profiles.yml` (never commit credentials — use
env vars):

```yaml
edi_reconciliation:
  target: client            # select with `dbt run --target client`
  outputs:
    client:
      type: postgres
      host: "{{ env_var('CLIENT_PG_HOST') }}"
      port: "{{ env_var('CLIENT_PG_PORT') | as_number }}"
      user: "{{ env_var('CLIENT_PG_USER') }}"
      password: "{{ env_var('CLIENT_PG_PASSWORD') }}"
      dbname: "{{ env_var('CLIENT_PG_DB') }}"
      schema: "{{ env_var('CLIENT_EDI_SCHEMA', 'edi') }}"   # target schema for the marts
      threads: 4
```

The raw source schema (the client's landed 850/856/810/820/852/997 documents) is
set in `transforms/models/sources.yml` via `CLIENT_RAW_SCHEMA` — point it at the
client's raw EDI tables. No source table names are hardcoded to Cinderhaven.

## 2. Load the client corpus

Land the client's X12 documents into the raw schema (`corpus/loader.py` handles
the demo corpus; a client feed replaces it). Confirm counts per document type
before running dbt.

## 3. Run the pipeline

```bash
dbt deps --target client
dbt run  --target client
dbt test --target client        # schema + data tests must pass before delivery
```

---

## 4. MANDATORY post-deploy verification — the missing-997 NULL-anchor probe

**A committed fix that was never run on the target database is not a fix.** The
07-31 audit (finding A5) is explicit: the missing-997 exception anchors its date
filtering on `doc_date` (`fct_exceptions.sql` → `exc_997`,
`dispute_date_anchor = doc_date`). If that anchor comes back NULL on the client's
data — a source column mapped wrong, a stale mart, a partial run — then any
date-windowed "unacknowledged 997" count silently returns **zero**, and the
client is told they have no missing acknowledgements when they may have many.

**This probe is a required delivery gate. Run it on the TARGET database after
every deploy, before handing anything to the client.**

```sql
-- Probe: date-filtered unacknowledged-997 counts, run on the CLIENT database.
-- Replace :window_start / :window_end with the engagement reporting window and
-- {schema} with the client target schema (CLIENT_EDI_SCHEMA).
SELECT
    partner_id,
    count(*)                                                   AS unacked_997,
    count(*) FILTER (WHERE dispute_date_anchor IS NULL)        AS null_anchor_rows,
    min(dispute_date_anchor)                                   AS earliest_anchor,
    max(dispute_date_anchor)                                   AS latest_anchor
FROM   {schema}.fct_exceptions
WHERE  exception_class = 'missing_997_ack'
  AND  dispute_date_anchor >= :window_start   -- the filter that breaks if the anchor is NULL
  AND  dispute_date_anchor <  :window_end
GROUP  BY partner_id
ORDER  BY unacked_997 DESC;
```

### Acceptance criteria (all must hold, or STOP — do not deliver)

1. **`null_anchor_rows` = 0 for every partner.** A non-zero value means a
   missing-997 row reached the mart with a NULL anchor — the NULL-anchor fix is
   not live on this database. Do not deliver; re-check the source `doc_date`
   mapping (`int_997_match.sql`: `ship_date`/`invoice_date → doc_date`) and
   re-run `dbt run`.
2. **`unacked_997` > 0 for at least one partner** *when the corpus is known to
   contain unacknowledged documents* (confirm against the raw 997 feed:
   outbound docs with no matching 997 within 48 hours). A zero here while raw
   unacked docs exist is the exact silent failure this probe guards — it means
   the date filter on the anchor is excluding real rows.
3. **`earliest_anchor` / `latest_anchor` fall inside the engagement window.** An
   anchor outside `[window_start, window_end)` means the window or the anchor
   column is wrong.

Record the probe output (partner counts + the two anchor bounds) in the
engagement log as the post-deploy sign-off. Re-run it after any re-deploy of the
`fct_exceptions` mart.

---

## 5. Deliverables

The dashboard (`uvicorn dashboard.app:app`) and the exception export read
`fct_exceptions` in the client schema. Every dollar-ranked exception carries its
class and partner; the missing-997 class is operational (0 dollar impact) but is
the leading indicator of chargeback exposure, which is why the probe above is a
hard gate.
