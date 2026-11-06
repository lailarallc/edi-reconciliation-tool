"""Exception dashboard routes.

Queries fct_exceptions and int_997_match from the edi_marts schema.
All routes degrade gracefully when the database is not configured. When a
configured database cannot be reached, db.query raises db.DataUnavailable
(HTTP 503); helpers log and re-raise rather than return empty rows.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import dashboard.db as db
from dashboard.labels import display_label

logger = logging.getLogger(__name__)

_SCHEMA = db.MARTS_SCHEMA

# Hero card order — row 1 then row 2 of the 4×2 grid
_HERO_ORDER = [
    "ordered_not_asnd",
    "shipped_not_invoiced",
    "short_pay",
    "qty_mismatch",
    "852_discrepancy",
    "uom_mismatch",
    "missing_997_ack",
]

# Classes included in Total Exposure sum (dollar-denominated, recoverable).
# 852_discrepancy is excluded: it is a lifetime, no-tolerance timing signal
# (shipped vs. reported sell-through), not a recoverable billing gap.
_EXPOSURE_CLASSES = frozenset({
    "ordered_not_asnd",
    "shipped_not_invoiced",
    "short_pay",
    "qty_mismatch",
})

_CLASS_LABELS = {
    "ordered_not_asnd":      "Ordered, Not ASN'd",
    "shipped_not_invoiced":  "Shipped, Not Invoiced",
    "short_pay":             "Short Pay",
    "uom_mismatch":          "UoM Mismatch",
    "qty_mismatch":          "Quantity Mismatch",
    "852_discrepancy":       "852 Sell-Through Gap",
    "missing_997_ack":       "Missing 997 ACK",
}

_NO_DISPUTE_CLOCK = frozenset({"852_discrepancy", "missing_997_ack"})


def _fmt_dollar(amount: float | None) -> str:
    if amount is None:
        return "—"
    if amount == 0:
        return "$0"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:,.2f}"


def get_date_range_bounds() -> dict[str, Any] | None:
    """Return min/max dispute_date_anchor from fct_exceptions as ISO strings."""
    if not db.is_configured():
        return None
    try:
        # dollar_impact is signed for shipped_not_invoiced (positive =
        # under-billed, negative = over-invoiced credit risk). Exposure sums
        # magnitudes so the two directions cannot net against each other.
        rows = db.query(f"""
            select min(dispute_date_anchor) as min_date,
                   max(dispute_date_anchor) as max_date
            from {_SCHEMA}.fct_exceptions
            where dispute_date_anchor is not null
        """)
        if not rows or rows[0]["min_date"] is None:
            return None
        return {
            "min_date": rows[0]["min_date"],
            "max_date": rows[0]["max_date"],
            "min_iso": rows[0]["min_date"].isoformat(),
            "max_iso": rows[0]["max_date"].isoformat(),
            "min_fmt": rows[0]["min_date"].strftime("%b %d, %Y"),
            "max_fmt": rows[0]["max_date"].strftime("%b %d, %Y"),
        }
    except Exception:
        logger.exception("get_date_range_bounds query failed")
        raise


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True


def _date_where(date_start: str, date_end: str) -> tuple[str, list]:
    """Build a WHERE clause fragment for date filtering on dispute_date_anchor.

    852 rows always pass through: the class is a lifetime (partner, sku)
    aggregate with no per-period dates, so a date range cannot apply to it —
    the card is labeled "full corpus" in the template when a range is active.
    997 rows pass through only while their anchor is NULL (pre-migration
    data); once fct_exceptions carries doc_date anchors they filter normally.
    Returns (sql_fragment, params_list). A value that is not an ISO date
    (?date_start=notadate) is ignored, as if absent, rather than sent to SQL.
    """
    date_start = date_start if _is_iso_date(date_start) else ""
    date_end = date_end if _is_iso_date(date_end) else ""
    if not date_start and not date_end:
        return "", []
    conditions = []
    params: list[Any] = []
    if date_start:
        conditions.append("dispute_date_anchor >= %s")
        params.append(date_start)
    if date_end:
        conditions.append("dispute_date_anchor <= %s")
        params.append(date_end)
    date_filter = " and ".join(conditions)
    return (
        f"(({date_filter})"
        " or exception_class = '852_discrepancy'"
        " or (exception_class = 'missing_997_ack'"
        " and dispute_date_anchor is null))"
    ), params


def get_exception_summary(
    date_start: str = "",
    date_end: str = "",
) -> tuple[list[dict[str, Any]], float]:
    """Summary card data for the 4x2 hero grid, plus Total Exposure."""
    if not db.is_configured():
        return [], 0.0
    try:
        date_clause, date_params = _date_where(date_start, date_end)
        where = f"where {date_clause}" if date_clause else ""

        # dollar_impact is signed for shipped_not_invoiced (positive =
        # under-billed, negative = over-invoiced credit risk). Exposure sums
        # magnitudes so the two directions cannot net against each other.
        rows = db.query(f"""
            select
                exception_class,
                count(*)                as exception_count,
                coalesce(sum(abs(dollar_impact)), 0) as total_dollar_impact,
                bool_or(dispute_urgent) as any_urgent
            from {_SCHEMA}.fct_exceptions
            {where}
            group by exception_class
            order by total_dollar_impact desc
        """, tuple(date_params))

        by_class = {r["exception_class"]: r for r in rows}
        result = []
        for cls in _HERO_ORDER:
            if cls in by_class:
                row = by_class[cls]
                result.append({
                    "exception_class": cls,
                    "label": _CLASS_LABELS[cls],
                    "total_dollar_impact": float(row["total_dollar_impact"]),
                    "total_fmt": _fmt_dollar(float(row["total_dollar_impact"])),
                    "exception_count": int(row["exception_count"]),
                    "any_urgent": bool(row["any_urgent"]),
                    "ops_only": cls == "missing_997_ack",
                    "no_dispute_clock": cls in _NO_DISPUTE_CLOCK,
                })
            else:
                result.append({
                    "exception_class": cls,
                    "label": _CLASS_LABELS[cls],
                    "total_dollar_impact": 0.0,
                    "total_fmt": "$0",
                    "exception_count": 0,
                    "any_urgent": False,
                    "ops_only": cls == "missing_997_ack",
                    "no_dispute_clock": cls in _NO_DISPUTE_CLOCK,
                })

        total_exposure = sum(
            c["total_dollar_impact"]
            for c in result
            if c["exception_class"] in _EXPOSURE_CLASSES
        )
        return result, total_exposure
    except Exception:
        logger.exception("get_exception_summary query failed")
        raise


def get_exceptions(
    partner: str = "",
    exception_class: str = "",
    date_start: str = "",
    date_end: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Detail rows for the exception table."""
    if not db.is_configured():
        return []
    try:
        conditions = ["exception_class != 'missing_997_ack'"]
        params: list[Any] = []
        if partner:
            conditions.append("partner_id = %s")
            params.append(partner)
        if exception_class:
            conditions.append("exception_class = %s")
            params.append(exception_class)
        date_clause, date_params = _date_where(date_start, date_end)
        if date_clause:
            conditions.append(date_clause)
            params.extend(date_params)
        where = " and ".join(conditions)
        params.append(limit)
        # dollar_impact is signed for shipped_not_invoiced (positive =
        # under-billed, negative = over-invoiced credit risk). Exposure sums
        # magnitudes so the two directions cannot net against each other.
        rows = db.query(f"""
            select
                partner_id,
                exception_class,
                po_number,
                sku,
                invoice_number,
                dollar_impact,
                dispute_window_days,
                dispute_window_expires_at,
                dispute_urgent,
                match_status
            from {_SCHEMA}.fct_exceptions
            where {where}
            order by dollar_impact desc nulls last
            limit %s
        """, tuple(params))
        for row in rows:
            row["dollar_fmt"] = _fmt_dollar(float(row["dollar_impact"] or 0))
            row["class_label"] = _CLASS_LABELS.get(row["exception_class"], row["exception_class"])
        return rows
    except Exception:
        logger.exception("get_exceptions query failed")
        raise


def get_corpus_date_range() -> str | None:
    """Return a formatted date range string for the corpus, e.g. 'Jan 2023 – Jan 2026'."""
    if not db.is_configured():
        return None
    try:
        # dollar_impact is signed for shipped_not_invoiced (positive =
        # under-billed, negative = over-invoiced credit risk). Exposure sums
        # magnitudes so the two directions cannot net against each other.
        rows = db.query(f"""
            select min(dispute_date_anchor) as min_date,
                   max(dispute_date_anchor) as max_date
            from {_SCHEMA}.fct_exceptions
            where dispute_date_anchor is not null
        """)
        if not rows or rows[0]["min_date"] is None:
            return None
        mn = rows[0]["min_date"]
        mx = rows[0]["max_date"]
        return f"{mn.strftime('%b %Y')} – {mx.strftime('%b %Y')}"
    except Exception:
        logger.exception("get_corpus_date_range query failed")
        raise


def get_partners() -> list[str]:
    """Distinct partner IDs for the filter dropdown."""
    if not db.is_configured():
        return []
    try:
        rows = db.query(f"select distinct partner_id from {_SCHEMA}.fct_exceptions")
        # Sort by public label: real-ID alphabetical order would leak the mapping.
        return sorted((r["partner_id"] for r in rows), key=display_label)
    except Exception:
        logger.exception("get_partners query failed")
        raise


def get_997_status() -> list[dict[str, Any]]:
    """Rows for the 997 ACK status section (ops layer)."""
    if not db.is_configured():
        return []
    try:
        # dollar_impact is signed for shipped_not_invoiced (positive =
        # under-billed, negative = over-invoiced credit risk). Exposure sums
        # magnitudes so the two directions cannot net against each other.
        rows = db.query(f"""
            select
                partner_id,
                document_type,
                isa_control_number,
                doc_date,
                ack_status,
                ack_date,
                ack_missing_or_late
            from {_SCHEMA}.int_997_match
            where ack_missing_or_late or ack_status in ('rejected', 'accepted_with_errors')
            order by ack_status, partner_id, doc_date desc
            limit 100
        """)
        return rows
    except Exception:
        logger.exception("get_997_status query failed")
        raise
