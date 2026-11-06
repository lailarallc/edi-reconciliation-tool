"""Partner labels and the honest-outage path (no DB required).

db.query (or db._get_conn) is patched at the database boundary: unit tests
have no Postgres, and these tests need a configured-but-answering database
(labels), a configured-but-unreachable one (outage), or a connection that
dies mid-session (retry), none of which exists locally.
"""
from __future__ import annotations

import json
import re

import psycopg2
import pytest
from fastapi.testclient import TestClient

import dashboard.db as db
from dashboard.labels import display_id, display_label
from dashboard.routes.exceptions import _date_where

# Real partner names and the codes the corpus IDs embed (WMT is the ticker).
_REAL_CODES = re.compile(r"\b(KEHE|KeHE|UNFI|WALMARTUS|WALMART|Walmart|WMT)\b")
_DOLLAR = re.compile(r"\$\s?\d")

# The corpus's own ID formats, so a leak through a PO or invoice cell shows up.
_ROWS = [
    ("KEHE", "DPO-KEHE-004127", "KEHE-INV-004127"),
    ("UNFI", "DPO-UNFI-001893", "UNFI-INV-001893"),
    ("WALMARTUS", "PO-ART-002210", "WMT-INV-002210"),
]


@pytest.fixture
def client():
    from dashboard.app import app
    with TestClient(app) as c:
        yield c


def _fake_query(sql, params=()):
    """Answer the partner and exception-row queries with one row per partner."""
    if "distinct partner_id" in sql:
        return [{"partner_id": p} for p, _, _ in _ROWS]
    if "fct_exceptions" in sql and "dollar_impact," in sql:
        return [
            {
                "partner_id": partner, "exception_class": "short_pay",
                "po_number": po, "sku": "CHP-PS-009", "invoice_number": inv,
                "dollar_impact": 1000.0 * (i + 1), "dispute_window_days": 60,
                "dispute_window_expires_at": "2026-12-01", "dispute_urgent": True,
                "match_status": "short_pay", "total_count": len(_ROWS),
            }
            for i, (partner, po, inv) in enumerate(_ROWS)
        ]
    return []


def _rows_with_dollars(markup: str) -> list[str]:
    rows = re.findall(r"<tr\b.*?</tr>", markup, flags=re.S)
    return [re.sub(r"<[^>]+>", " ", r) for r in rows if _DOLLAR.search(r)]


def _assert_no_real_codes_in_dollar_rows(markup: str) -> None:
    rows = _rows_with_dollars(markup)
    assert rows, "expected table rows with dollar figures to check"
    for row in rows:
        leaked = _REAL_CODES.findall(row)
        assert not leaked, f"real partner code {leaked} beside a dollar figure in row: {' '.join(row.split())}"


# --- labels -----------------------------------------------------------------

def test_display_label_maps_each_partner_code_to_its_shared_label():
    assert display_label("WALMARTUS") == "National mass retailer"
    assert display_label("UNFI") == "Distributor A"
    assert display_label("KEHE") == "Distributor B"


def test_display_label_passes_unknown_values_through_unchanged():
    assert display_label("SOMEONE-ELSE") == "SOMEONE-ELSE"


def test_display_id_swaps_the_partner_segment_for_the_label_short_form():
    assert display_id("DPO-KEHE-004127", "KEHE") == "DPO-B-004127"
    assert display_id("DPO-UNFI-001893", "UNFI") == "DPO-A-001893"
    assert display_id("KEHE-INV-004127", "KEHE") == "B-INV-004127"
    assert display_id("UNFI-INV-001893", "UNFI") == "A-INV-001893"
    assert display_id("WMT-INV-002210", "WALMARTUS") == "NMR-INV-002210"


def test_display_id_keeps_code_fragments_that_are_not_names():
    assert display_id("PO-ART-002210", "WALMARTUS") == "PO-ART-002210"
    assert display_id(None, "KEHE") is None


def test_exception_rows_show_no_partner_code_in_any_cell_beside_a_dollar_figure(client, monkeypatch):
    monkeypatch.setattr(db, "is_configured", lambda: True)
    monkeypatch.setattr(db, "query", _fake_query)
    r = client.get("/exceptions")
    assert r.status_code == 200
    for label in ("Distributor A", "Distributor B", "National mass retailer"):
        assert label in r.text, f"expected label {label!r} in the exception rows"
    _assert_no_real_codes_in_dollar_rows(r.text)


def test_drilldown_apis_give_display_ids_for_the_js_tables(client, monkeypatch):
    monkeypatch.setattr(db, "is_configured", lambda: True)
    monkeypatch.setattr(db, "query", _fake_query)
    catalog_rows = client.get("/api/catalog/drilldown", params={"class": "short_pay"}).json()["rows"]
    lifecycle_rows = client.get("/api/lifecycle/drilldown", params={"callout": "0"}).json()["rows"]
    for rows in (catalog_rows, lifecycle_rows):
        shown = [(r["partner_label"], r["po_display"], r["invoice_display"]) for r in rows]
        for cells in shown:
            assert not _REAL_CODES.search(" ".join(cells)), f"real code in displayed cells {cells}"


def test_js_tables_render_the_display_fields_not_the_raw_ids():
    for path in ("dashboard/static/js/lifecycle.js", "dashboard/templates/catalog.html"):
        src = open(path, encoding="utf-8").read()
        for raw in ("partner_id)", "po_number ||", "invoice_number ||"):
            assert f"esc(row.{raw}" not in src and f"esc(r.{raw}" not in src, f"{path} renders raw {raw}"


def test_partner_filter_shows_labels_in_label_order_and_keeps_ids_as_values(client, monkeypatch):
    monkeypatch.setattr(db, "is_configured", lambda: True)
    monkeypatch.setattr(db, "query", _fake_query)
    r = client.get("/catalog")
    options = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', r.text)
    partner_options = [(v, t.strip()) for v, t in options if v]
    assert partner_options[:3] == [
        ("UNFI", "Distributor A"),
        ("KEHE", "Distributor B"),
        ("WALMARTUS", "National mass retailer"),
    ], f"got {partner_options[:3]}"


def test_catalog_examples_with_dollar_figures_use_labels(client):
    r = client.get("/catalog")
    for line in r.text.splitlines():
        if _DOLLAR.search(line):
            assert not _REAL_CODES.search(line), f"real partner code beside a dollar figure: {line.strip()}"


def test_lifecycle_chart_footer_labels_come_from_the_server(client, monkeypatch):
    import dashboard.app as app_module
    monkeypatch.setattr(app_module, "get_lifecycle_stats", lambda partner="": {"ordered": 10, "shipped": 9, "invoiced": 9, "paid": 8})
    monkeypatch.setattr(app_module, "get_callout_stats", lambda partner="": [])
    monkeypatch.setattr(app_module, "get_lifecycle_partners", lambda: ["UNFI", "KEHE", "WALMARTUS"])
    r = client.get("/lifecycle")
    blob = re.search(r'<script id="lifecycle-data" type="application/json">(.*?)</script>', r.text, re.S).group(1)
    assert json.loads(blob)["partner_labels"] == ["distributor A", "distributor B", "national mass retailer"]
    assert "lifecycle.js?v=" in r.text, "lifecycle.js needs a version query so cached copies refresh"


# --- outage -----------------------------------------------------------------

def _unreachable(sql, params=()):
    raise db.DataUnavailable("database unavailable: could not connect to server")


def test_dashboard_returns_503_not_an_empty_result_when_the_database_is_unreachable(client, monkeypatch):
    monkeypatch.setattr(db, "is_configured", lambda: True)
    monkeypatch.setattr(db, "query", _unreachable)
    r = client.get("/")
    assert r.status_code == 503, f"expected 503, got {r.status_code}"
    assert r.headers.get("retry-after") == "60"
    assert "Data temporarily unavailable" in r.text
    assert "No exceptions found" not in r.text
    assert "no content-level mismatches" not in r.text


def test_api_returns_503_json_when_the_database_is_unreachable(client, monkeypatch):
    monkeypatch.setattr(db, "is_configured", lambda: True)
    monkeypatch.setattr(db, "query", _unreachable)
    r = client.get("/api/catalog/drilldown", params={"class": "short_pay"})
    assert r.status_code == 503, f"expected 503, got {r.status_code}"
    assert r.json() == {"error": "data temporarily unavailable"}
    r = client.get("/api/lifecycle/drilldown", params={"callout": "0"})
    assert r.status_code == 503, f"expected 503, got {r.status_code}"


def test_catalog_keeps_its_static_patterns_and_says_order_data_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(db, "is_configured", lambda: True)
    monkeypatch.setattr(db, "query", _unreachable)
    r = client.get("/catalog")
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    assert "ordered_not_asnd" in r.text
    assert "Order data is temporarily unavailable" in r.text


def test_healthz_answers_without_touching_the_database(client, monkeypatch):
    monkeypatch.setattr(db, "is_configured", lambda: True)
    monkeypatch.setattr(db, "query", _unreachable)
    r = client.get("/healthz")
    assert r.status_code == 200 and r.text == "ok"


def test_a_query_bug_is_a_500_not_a_reported_outage(monkeypatch):
    from dashboard.app import app

    def _bad_sql(sql, params=()):
        raise psycopg2.ProgrammingError('relation "edi_marts.fct_exceptions" does not exist')

    monkeypatch.setattr(db, "is_configured", lambda: True)
    monkeypatch.setattr(db, "query", _bad_sql)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/")
    assert r.status_code == 500, f"expected 500, got {r.status_code}"
    assert "Data temporarily unavailable" not in r.text


def test_an_invalid_date_filter_is_ignored_rather_than_sent_to_sql():
    assert _date_where("notadate", "") == ("", [])
    fragment, params = _date_where("2025-01-01", "also-bad")
    assert params == ["2025-01-01"] and "<=" not in fragment


# --- connection handling ----------------------------------------------------

class _Cursor:
    def __init__(self, fail):
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        if self.fail:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")

    def fetchall(self):
        return [{"ok": 1}]


class _Conn:
    def __init__(self, fail):
        self.fail, self.closed = fail, 0

    def cursor(self, cursor_factory=None):
        return _Cursor(self.fail)

    def close(self):
        self.closed = 1


def test_a_dead_reused_connection_is_replaced_and_the_query_retried_once(monkeypatch):
    conns = iter([(_Conn(fail=True), True), (_Conn(fail=False), False)])
    monkeypatch.setattr(db, "_get_conn", lambda: next(conns))
    assert db.query("select 1") == [{"ok": 1}]


def test_a_failing_fresh_connection_raises_data_unavailable_without_retrying(monkeypatch):
    calls = []

    def _fresh_dead():
        calls.append(1)
        return _Conn(fail=True), False

    monkeypatch.setattr(db, "_get_conn", _fresh_dead)
    with pytest.raises(db.DataUnavailable):
        db.query("select 1")
    assert len(calls) == 1, f"a fresh connection should not be retried; tried {len(calls)} times"


def test_a_connect_failure_raises_data_unavailable(monkeypatch):
    def _refused():
        raise psycopg2.OperationalError("connection refused")

    monkeypatch.setattr(db, "_get_conn", _refused)
    with pytest.raises(db.DataUnavailable):
        db.query("select 1")
