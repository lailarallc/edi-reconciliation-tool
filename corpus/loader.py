"""Corpus loader — parse X12 strings and write raw rows to Postgres.

Reads a GenerateResult produced by the U2 corpus generators, calls
parse_document() on each string, expands each parsed object to one row
per line item, and upserts into the edi_raw.* tables in Postgres.

All expand_* helpers are pure functions (no DB dependency) and are unit-
testable without a live database. The load_corpus() function requires
DATABASE_URL or the individual POSTGRES_* env vars.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from corpus import prod_guard
from corpus.generator import GenerateResult
from parser.x12_parser import parse_document
from parser.models import (
    FuncAck,
    Invoice,
    ProductActivity,
    PurchaseOrder,
    Remittance,
    ShipNotice,
    X12ParseError,
)

# ---------------------------------------------------------------------------
# Schema and table constants
# ---------------------------------------------------------------------------

RAW_SCHEMA = "edi_raw"

_TABLES = {
    "850": "edi_850_pos_lines",
    "856": "edi_856_asn_items",
    "810": "edi_810_invoice_lines",
    "820": "edi_820_remittance_lines",
    "852": "edi_852_activity_lines",
    "997": "edi_997_acks",
}

_DDL = {
    "850": f"""
        CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.edi_850_pos_lines (
            isa_control_number  TEXT,
            partner_id          TEXT,
            po_number           TEXT,
            po_date             TEXT,
            line_number         TEXT,
            sku                 TEXT,
            quantity            NUMERIC,
            unit_of_measure     TEXT,
            unit_price          NUMERIC,
            promo_allowance     NUMERIC,
            loaded_at           TIMESTAMPTZ
        )
    """,
    "856": f"""
        CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.edi_856_asn_items (
            isa_control_number  TEXT,
            partner_id          TEXT,
            shipment_id         TEXT,
            ship_date           TEXT,
            bol_number          TEXT,
            header_po_number    TEXT,
            line_number         TEXT,
            sku                 TEXT,
            quantity            NUMERIC,
            unit_of_measure     TEXT,
            hl_id               TEXT,
            item_po_number      TEXT,
            loaded_at           TIMESTAMPTZ
        )
    """,
    "810": f"""
        CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.edi_810_invoice_lines (
            isa_control_number          TEXT,
            partner_id                  TEXT,
            invoice_number              TEXT,
            invoice_date                TEXT,
            po_number                   TEXT,
            total_amount                NUMERIC,
            is_credit                   BOOLEAN,
            original_invoice_number     TEXT,
            distributor_invoice_number  TEXT,
            line_number                 TEXT,
            sku                         TEXT,
            quantity                    NUMERIC,
            unit_of_measure             TEXT,
            unit_price                  NUMERIC,
            loaded_at                   TIMESTAMPTZ
        )
    """,
    "820": f"""
        CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.edi_820_remittance_lines (
            isa_control_number    TEXT,
            partner_id            TEXT,
            payment_amount        NUMERIC,
            payment_date          TEXT,
            header_invoice_number TEXT,
            po_number             TEXT,
            rmr_invoice_number    TEXT,
            rmr_amount            NUMERIC,
            loaded_at             TIMESTAMPTZ
        )
    """,
    "852": f"""
        CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.edi_852_activity_lines (
            isa_control_number  TEXT,
            partner_id          TEXT,
            report_id           TEXT,
            report_date         TEXT,
            line_number         TEXT,
            sku                 TEXT,
            quantity            NUMERIC,
            unit_of_measure     TEXT,
            period_start        TEXT,
            period_end          TEXT,
            loaded_at           TIMESTAMPTZ
        )
    """,
    "997": f"""
        CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.edi_997_acks (
            isa_control_number           TEXT,
            partner_id                   TEXT,
            ack_date                     TEXT,
            acknowledged_functional_id   TEXT,
            acknowledged_gs_control      TEXT,
            acceptance_code              TEXT,
            loaded_at                    TIMESTAMPTZ
        )
    """,
}

# ---------------------------------------------------------------------------
# Pure expansion helpers (no DB dependency)
# ---------------------------------------------------------------------------

def expand_850(doc: PurchaseOrder, loaded_at: datetime) -> list[dict[str, Any]]:
    """One row per PO line."""
    rows = []
    for line in doc.lines:
        rows.append({
            "isa_control_number": doc.isa_control_number,
            "partner_id": doc.partner_id,
            "po_number": doc.po_number,
            "po_date": doc.po_date,
            "line_number": line.line_number,
            "sku": line.sku,
            "quantity": line.quantity,
            "unit_of_measure": line.unit_of_measure,
            "unit_price": line.unit_price,
            "promo_allowance": line.promo_allowance,
            "loaded_at": loaded_at,
        })
    return rows


def expand_856(doc: ShipNotice, loaded_at: datetime) -> list[dict[str, Any]]:
    """One row per ASN item. item_po_number from HL/PRF (multi-stop aware)."""
    rows = []
    for item in doc.items:
        rows.append({
            "isa_control_number": doc.isa_control_number,
            "partner_id": doc.partner_id,
            "shipment_id": doc.shipment_id,
            "ship_date": doc.ship_date,
            "bol_number": doc.bol_number,
            "header_po_number": doc.po_number,
            "line_number": item.line_number,
            "sku": item.sku,
            "quantity": item.quantity,
            "unit_of_measure": item.unit_of_measure,
            "hl_id": item.hl_id,
            "item_po_number": item.po_number,
            "loaded_at": loaded_at,
        })
    return rows


def expand_810(doc: Invoice, loaded_at: datetime) -> list[dict[str, Any]]:
    """One row per invoice line. Header fields duplicated on each row."""
    rows = []
    for line in doc.lines:
        rows.append({
            "isa_control_number": doc.isa_control_number,
            "partner_id": doc.partner_id,
            "invoice_number": doc.invoice_number,
            "invoice_date": doc.invoice_date,
            "po_number": doc.po_number,
            "total_amount": doc.total_amount,
            "is_credit": doc.is_credit,
            "original_invoice_number": doc.original_invoice_number,
            "distributor_invoice_number": doc.distributor_invoice_number,
            "line_number": line.line_number,
            "sku": line.sku,
            "quantity": line.quantity,
            "unit_of_measure": line.unit_of_measure,
            "unit_price": line.unit_price,
            "loaded_at": loaded_at,
        })
    return rows


def expand_820(doc: Remittance, loaded_at: datetime) -> list[dict[str, Any]]:
    """One row per RMR line. Falls back to one header row if no RMR lines."""
    rows = []
    if doc.lines:
        for line in doc.lines:
            rows.append({
                "isa_control_number": doc.isa_control_number,
                "partner_id": doc.partner_id,
                "payment_amount": doc.payment_amount,
                "payment_date": doc.payment_date,
                "header_invoice_number": doc.invoice_number,
                "po_number": doc.po_number,
                "rmr_invoice_number": line.invoice_number,
                "rmr_amount": line.amount,
                "loaded_at": loaded_at,
            })
    else:
        rows.append({
            "isa_control_number": doc.isa_control_number,
            "partner_id": doc.partner_id,
            "payment_amount": doc.payment_amount,
            "payment_date": doc.payment_date,
            "header_invoice_number": doc.invoice_number,
            "po_number": doc.po_number,
            "rmr_invoice_number": doc.invoice_number,
            "rmr_amount": doc.payment_amount,
            "loaded_at": loaded_at,
        })
    return rows


def expand_852(doc: ProductActivity, loaded_at: datetime) -> list[dict[str, Any]]:
    """One row per activity line."""
    rows = []
    for line in doc.lines:
        rows.append({
            "isa_control_number": doc.isa_control_number,
            "partner_id": doc.partner_id,
            "report_id": doc.report_id,
            "report_date": doc.report_date,
            "line_number": line.line_number,
            "sku": line.sku,
            "quantity": line.quantity,
            "unit_of_measure": line.unit_of_measure,
            "period_start": line.period_start,
            "period_end": line.period_end,
            "loaded_at": loaded_at,
        })
    return rows


def expand_997(doc: FuncAck, loaded_at: datetime) -> list[dict[str, Any]]:
    """One row per ACK (no sub-lines)."""
    return [{
        "isa_control_number": doc.isa_control_number,
        "partner_id": doc.partner_id,
        "ack_date": doc.ack_date,
        "acknowledged_functional_id": doc.acknowledged_functional_id,
        "acknowledged_gs_control": doc.acknowledged_gs_control,
        "acceptance_code": doc.acceptance_code,
        "loaded_at": loaded_at,
    }]


_EXPANDERS = {
    "850": (PurchaseOrder, expand_850),
    "856": (ShipNotice, expand_856),
    "810": (Invoice, expand_810),
    "820": (Remittance, expand_820),
    "852": (ProductActivity, expand_852),
    "997": (FuncAck, expand_997),
}


# ---------------------------------------------------------------------------
# DB write
# ---------------------------------------------------------------------------

def _connect():
    """Connect to Postgres using DATABASE_URL or POSTGRES_* env vars."""
    import psycopg2
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        prod_guard.check(database_url)  # refuses a fly tunnel to production
        return psycopg2.connect(database_url)
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    prod_guard.check(host=host, port=port)  # refuses a fly tunnel to production
    return psycopg2.connect(
        host=host,
        port=port,
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        dbname=os.environ.get("POSTGRES_DB", "cinderhaven"),
    )


def _ensure_schema(cursor) -> None:
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}")


def _ensure_tables(cursor) -> None:
    for ddl in _DDL.values():
        cursor.execute(ddl)


def _truncate_tables(cursor) -> None:
    for table in _TABLES.values():
        cursor.execute(f"TRUNCATE TABLE {RAW_SCHEMA}.{table}")


def _insert_rows(cursor, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    from psycopg2.extras import execute_values
    cols = list(rows[0].keys())
    col_list = ", ".join(cols)
    values = [[row[c] for c in cols] for row in rows]
    sql = f"INSERT INTO {RAW_SCHEMA}.{table} ({col_list}) VALUES %s"
    execute_values(cursor, sql, values, page_size=500)


def load_corpus(result: GenerateResult, truncate: bool = True) -> dict[str, int]:
    """Parse all documents in a GenerateResult and load them into Postgres.

    Returns a dict of doc_type → row_count for each document type written.
    Skips documents that fail parsing with a warning (not a hard failure) so
    a single bad document doesn't abort the full load.
    """
    loaded_at = datetime.now(tz=timezone.utc)
    row_counts: dict[str, int] = {k: 0 for k in _TABLES}
    all_rows: dict[str, list[dict[str, Any]]] = {k: [] for k in _TABLES}

    for doc_type, raw_docs in result.documents.items():
        if doc_type not in _EXPANDERS:
            continue
        expected_cls, expander = _EXPANDERS[doc_type]
        for raw in raw_docs:
            try:
                parsed = parse_document(raw)
            except X12ParseError as exc:
                print(f"[loader] WARN: {doc_type} parse error — {exc}")
                continue
            if not isinstance(parsed, expected_cls):
                continue
            all_rows[doc_type].extend(expander(parsed, loaded_at))

    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                _ensure_schema(cur)
                _ensure_tables(cur)
                if truncate:
                    _truncate_tables(cur)
                for doc_type, rows in all_rows.items():
                    table = _TABLES[doc_type]
                    _insert_rows(cur, table, rows)
                    row_counts[doc_type] = len(rows)
    finally:
        conn.close()

    return row_counts
