"""Lifecycle visual data — four-way match funnel stats for the D3 embed."""
from __future__ import annotations

import logging
from typing import Any

import dashboard.db as db
from dashboard.labels import display_id, display_label

logger = logging.getLogger(__name__)

_SCHEMA = db.MARTS_SCHEMA

_CALLOUT_CLASS_MAP = {
    "0": "ordered_not_asnd",
    "1": "shipped_not_invoiced",
    "2": "short_pay",
}

_CALLOUT_CLASSES = ["ordered_not_asnd", "shipped_not_invoiced", "short_pay"]


def get_lifecycle_partners() -> list[str]:
    """Distinct partner IDs from the four-way match."""
    if not db.is_configured():
        return []
    try:
        rows = db.query(
            f"select distinct partner_id from {_SCHEMA}.int_four_way_match"
        )
        # Sort by public label: real-ID alphabetical order would leak the mapping.
        return sorted((r["partner_id"] for r in rows), key=display_label)
    except Exception:
        logger.exception("get_lifecycle_partners query failed")
        raise


def get_lifecycle_stats(partner: str = "") -> dict[str, Any] | None:
    """Aggregate funnel stats from int_four_way_match for the PO lifecycle visual.

    Returns None when the database is not configured or the query fails.
    """
    if not db.is_configured():
        return None
    try:
        partner_clause = "where partner_id = %s" if partner else ""
        partner_params = (partner,) if partner else ()
        dedup_clause = (
            "where invoice_number is not null and partner_id = %s"
            if partner
            else "where invoice_number is not null"
        )
        dedup_params = (partner,) if partner else ()

        rows = db.query(f"""
            with
            qty_totals as (
                select
                    coalesce(sum(ordered_qty),             0) as total_ordered,
                    coalesce(sum(shipped_qty_normalized),  0) as total_shipped,
                    coalesce(sum(invoiced_qty_normalized), 0) as total_invoiced
                from {_SCHEMA}.int_four_way_match
                {partner_clause}
            ),
            dollar_totals as (
                select
                    coalesce(sum(invoice_amount), 0) as total_invoiced_dollars,
                    coalesce(sum(paid_amount),    0) as total_paid_dollars
                from (
                    select distinct on (partner_id, invoice_number)
                        invoice_amount, paid_amount
                    from {_SCHEMA}.int_four_way_match
                    {dedup_clause}
                ) deduped
            )
            select q.*, d.*
            from qty_totals q
            cross join dollar_totals d
        """, partner_params + dedup_params)
        if not rows:
            return None

        r = rows[0]
        total_ordered          = float(r["total_ordered"])
        total_shipped          = float(r["total_shipped"])
        total_invoiced         = float(r["total_invoiced"])
        total_invoiced_dollars = float(r["total_invoiced_dollars"])
        total_paid_dollars_raw = float(r["total_paid_dollars"])

        total_paid_dollars = min(total_paid_dollars_raw, total_invoiced_dollars)

        avg_unit_price = (
            total_invoiced_dollars / total_invoiced if total_invoiced > 0 else 0
        )
        cases_paid_equiv = (
            total_paid_dollars / avg_unit_price if avg_unit_price > 0 else 0
        )

        ordered  = int(round(total_ordered))
        shipped  = int(round(total_shipped))
        invoiced = int(round(total_invoiced))
        paid     = int(round(cases_paid_equiv))

        if paid > invoiced:
            paid = invoiced

        return {
            "ordered":  ordered,
            "shipped":  shipped,
            "invoiced": invoiced,
            "paid":     paid,
            "source":   "live",
        }
    except Exception:
        logger.exception("get_lifecycle_stats query failed")
        raise


def get_callout_stats(partner: str = "") -> list[dict[str, Any]]:
    """Count and dollar sum per callout class from the exception mart.

    Returns a 3-element list aligned with _CALLOUT_CLASSES, each with
    {count, dollars}. Falls back to zeros when DB is unavailable.
    """
    empty = [{"count": 0, "dollars": 0.0} for _ in _CALLOUT_CLASSES]
    if not db.is_configured():
        return empty
    try:
        conditions = ["exception_class = any(%s)"]
        params: list[Any] = [_CALLOUT_CLASSES]
        if partner:
            conditions.append("partner_id = %s")
            params.append(partner)
        where = " and ".join(conditions)
        rows = db.query(f"""
            select
                exception_class,
                count(*) as cnt,
                coalesce(sum(dollar_impact), 0) as dollars
            from {_SCHEMA}.fct_exceptions
            where {where}
            group by exception_class
        """, tuple(params))
        lookup = {r["exception_class"]: r for r in rows}
        return [
            {
                "count": int(lookup[cls]["cnt"]) if cls in lookup else 0,
                "dollars": float(lookup[cls]["dollars"]) if cls in lookup else 0.0,
            }
            for cls in _CALLOUT_CLASSES
        ]
    except Exception:
        logger.exception("get_callout_stats query failed")
        raise


def get_lifecycle_drilldown(
    callout_index: str,
    partner: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return a page of exception rows matching a lifecycle callout gap.

    Returns {"total": <full match count>, "rows": [...]}. The total is the
    count across the whole filtered set (not just this page) so the client
    can show "showing N of TOTAL" and offer to load the next page.
    """
    empty: dict[str, Any] = {"total": 0, "rows": []}
    if not db.is_configured():
        return empty
    exc_class = _CALLOUT_CLASS_MAP.get(callout_index)
    if not exc_class:
        return empty
    try:
        conditions = ["exception_class = %s"]
        params: list[Any] = [exc_class]
        if partner:
            conditions.append("partner_id = %s")
            params.append(partner)
        where = " and ".join(conditions)
        params.extend([limit, offset])
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
                count(*) over () as total_count
            from {_SCHEMA}.fct_exceptions
            where {where}
            order by dollar_impact desc nulls last
            limit %s offset %s
        """, tuple(params))
        total = int(rows[0]["total_count"]) if rows else 0
        from dashboard.routes.exceptions import _fmt_dollar, _CLASS_LABELS
        for row in rows:
            row.pop("total_count", None)
            row["partner_label"] = display_label(row["partner_id"])
            row["po_display"] = display_id(row["po_number"], row["partner_id"])
            row["invoice_display"] = display_id(row["invoice_number"], row["partner_id"])
            row["dollar_fmt"] = _fmt_dollar(float(row["dollar_impact"] or 0))
            row["class_label"] = _CLASS_LABELS.get(
                row["exception_class"], row["exception_class"]
            )
            if row["dispute_window_expires_at"]:
                row["dispute_window_expires_at"] = str(
                    row["dispute_window_expires_at"]
                )
        return {"total": total, "rows": rows}
    except Exception:
        logger.exception("get_lifecycle_drilldown query failed")
        raise
