"""Failure pattern catalog — static definitions for all 7 exception classes."""
from __future__ import annotations

from dashboard.labels import display_id, display_label

# Worked examples sit beside dollar figures, so partners (and the invoice
# numbers that embed them) show their public labels.
_RETAILER = display_label("WALMARTUS", capitalize=False)
_DIST_B = display_label("KEHE", capitalize=False)
_RETAILER_INVOICE = display_id("WMT-INV-055", "WALMARTUS")

_PATTERNS = [
    {
        "key":            "ordered_not_asnd",
        "label":          "Ordered, Not ASN'd",
        "tier":           "revenue",
        "documents":      "850 → (missing 856)",
        "impact_formula": "ordered_qty × unit_price",
        "dispute_window": "60 days from PO date",
        "dispute_days":   60,
        "short":          (
            "A PO line has no matching 856 ASN. "
            "Supplier did not ship — or shipped without sending an ASN. "
            "Triggers OTIF chargeback for the full line value."
        ),
        "why":            (
            "Retail OTIF programs penalize suppliers when an ASN is absent before "
            "the delivery window closes. The retailer's WMS cannot receive the shipment "
            "without an ASN, converting a potential revenue event into a chargeback."
        ),
        "partners": [
            ("Walmart",  "ASN required before 10am on ship date; any miss is an immediate OTIF trigger"),
            ("UNFI",     "ASN optional on promo lines but breaks inventory visibility when absent"),
            ("KeHE",     "Multi-stop 856 with O-level HL loops; key resolution falls back to BOL"),
        ],
        "example": (
            f"PO 850-2024-001 ({_RETAILER}) — 24 cases SKU-GRANOLA-6PK @ $47.50 = $1,140\n"
            "No 856 found within the match window → ordered_not_asnd: $1,140 at risk"
        ),
    },
    {
        "key":            "shipped_not_invoiced",
        "label":          "Shipped, Not Invoiced",
        "tier":           "revenue",
        "documents":      "856 ASN ↔ 810 Invoice",
        "impact_formula": "abs(shipped_qty − invoiced_qty) × unit_price",
        "dispute_window": "60 days from invoice date",
        "dispute_days":   60,
        "short":          (
            "The 856 ASN shows more units shipped than the 810 invoice covers. "
            "Revenue left uncollected — goods delivered but not billed."
        ),
        "why":            (
            "Systematic underbilling compounds into material revenue leakage. "
            "After the 60-day window, the retailer has little obligation to reconcile "
            "the gap, turning an accounting error into a permanent write-off."
        ),
        "partners": [
            ("KeHE",  "REF*IA (internal account) on 810; missing it orphans the invoice from the PO"),
            ("UNFI",  "Credit + rebill on 3rd order creates a temporary shipped_not_invoiced gap"),
        ],
        "example": (
            f"PO 856-2024-012 ({_DIST_B}) — 24 cases shipped\n"
            "810 invoice covers 20 cases → shipped_not_invoiced: 4 cases × $47.50 = $190 unbilled"
        ),
    },
    {
        "key":            "short_pay",
        "label":          "Short Pay",
        "tier":           "revenue",
        "documents":      "810 Invoice ↔ 820 Remittance",
        "impact_formula": "abs(invoice_amount − paid_amount)",
        "dispute_window": "30 days from payment date",
        "dispute_days":   30,
        "short":          (
            "The 820 remittance shows a payment lower than the 810 invoice. "
            "Retailer deducted from the invoice — earned or unauthorized. "
            "Shortest dispute window of any exception class."
        ),
        "why":            (
            "Short pays are the most time-sensitive exception. At 30 days from the 820 "
            "date, the dispute window is half of most chargeback windows. Unauthorized "
            "deductions not disputed within the window become permanent write-offs."
        ),
        "partners": [
            ("UNFI",     "Every 3rd 820 omits REF*PO — invoice number is the only match key"),
            ("Walmart",  "High deduction volume; reason codes in REF segments must be decoded before disputing"),
        ],
        "example": (
            f"810 invoice {_RETAILER_INVOICE}: $1,140.00 for 24 cases\n"
            "820 remittance: $898.50 paid\n"
            "→ short_pay: $241.50 deducted, 30-day dispute window"
        ),
    },
    {
        "key":            "uom_mismatch",
        "label":          "UoM Mismatch",
        "tier":           "revenue",
        "documents":      "850 ↔ 856 ↔ 810 (unit divergence)",
        "impact_formula": "abs(ordered_vs_shipped_delta) × unit_price",
        "dispute_window": "60 days",
        "dispute_days":   60,
        "short":          (
            "The unit of measure in the PO (850 PO1) does not match the ASN (856 IT1) "
            "and normalization cannot resolve the divergence. "
            "The document counts look plausible — the units don't."
        ),
        "why":            (
            "UoM mismatches are stealth errors. Both documents may say '24' but one "
            "means cases and the other means eaches. A 12-count case pack means the "
            "retailer ordered 288 units but received 24 — a 12× gap invisible without "
            "unit normalization."
        ),
        "partners": [
            ("Walmart",  "850 PO1 in CA (cases); 856 IT1 in EA (eaches) — Walmart eaches quirk"),
            ("UNFI",     "SLN promo segment uses different UoM than the line item PO1"),
        ],
        "example": (
            "850 PO: 24 CA (cases) SKU-GRANOLA-6PK (case_pack = 6)\n"
            "856 IT1: 24 EA (eaches)\n"
            "Normalized: 24 cases ordered vs 4 cases shipped\n"
            "→ uom_mismatch: 20-case delta × $47.50 = $950 exposure"
        ),
    },
    {
        "key":            "qty_mismatch",
        "label":          "Quantity Mismatch",
        "tier":           "revenue",
        "documents":      "850 ↔ 856 (after UoM normalization)",
        "impact_formula": "abs(ordered_qty − shipped_qty_normalized) × unit_price",
        "dispute_window": "60 days",
        "dispute_days":   60,
        "short":          (
            "After UoM normalization, ordered and shipped quantities diverge beyond tolerance. "
            "Units agree; the supplier simply shipped a different quantity than ordered."
        ),
        "why":            (
            "Short-ships create OTIF exposure and may trigger vendor compliance chargebacks. "
            "Overshipments can result in unauthorized deductions or warehouse refusal. "
            "Distinguished from uom_mismatch: here the units agree, the quantities don't."
        ),
        "partners": [],
        "example": (
            "850 PO: 48 cases SKU-OAT-BARS-12CT\n"
            "856 ASN: 36 cases shipped (short-ship)\n"
            "→ qty_mismatch: 12-case variance × $47.50 = $570 chargeback exposure"
        ),
    },
    {
        "key":            "852_discrepancy",
        "label":          "852 Sell-Through Gap",
        "tier":           "revenue",
        "documents":      "852 Product Activity ↔ 856 shipped (period)",
        "impact_formula": "abs(sell_through_qty − shipped_qty) × avg(unit_price)",
        "dispute_window": "None — velocity signal",
        "dispute_days":   None,
        "short":          (
            "Distributor sell-through (852) does not reconcile with quantities shipped "
            "in the same period. Either a forecasting problem (stockout) or a reporting "
            "problem (stale 852 data)."
        ),
        "why":            (
            "For brands selling through UNFI or KeHE, the 852 is the only visibility into "
            "what is actually moving off distributor shelves. A systematic sell-through gap "
            "signals inventory building, stockouts, or corrupted reporting — none visible "
            "without this reconciliation."
        ),
        "partners": [
            ("UNFI",  "852 sent weekly; ASNs are event-driven — week-boundary effects"),
            ("KeHE",  "852 aggregates multi-DC inventory; per-DC ASNs can create apparent gaps"),
        ],
        "example": (
            f"{display_label('UNFI')} 852 (week of 2024-02-05): 96 cases SKU-GRANOLA-6PK sold\n"
            "856 ASNs in same period: 120 cases shipped\n"
            "→ 852_discrepancy: 24-case gap (destock or return risk)"
        ),
    },
    {
        "key":            "missing_997_ack",
        "label":          "Missing 997 ACK",
        "tier":           "ops",
        "documents":      "Outbound transaction → (missing 997)",
        "impact_formula": "$0 — operational only",
        "dispute_window": "None",
        "dispute_days":   None,
        "short":          (
            "An outbound document (856 ASN, 810 invoice) was transmitted but no 997 "
            "functional acknowledgment was received within 48 hours. "
            "The document may have been dropped, rejected, or failed to reach the VAN."
        ),
        "why":            (
            "Without a 997 ACK, the supplier cannot confirm the trading partner received "
            "the document. A dropped 856 means the retailer's WMS will refuse the physical "
            "shipment at dock. A dropped 810 means the payment cycle never starts."
        ),
        "partners": [
            ("Walmart",  "997 SLA is 24 hours; any delay triggers AS2 retransmission requirement"),
            ("UNFI",     "997 sometimes omitted for test ISA envelopes — filter by ISA11 qualifier"),
        ],
        "example": (
            f"856 ASN sent to {_DIST_B} — ISA control 000000042\n"
            "No 997 received within 48 hours\n"
            "→ missing_997_ack (operational, $0 dollar impact)\n"
            "   Check VAN delivery logs; retransmit if no delivery confirmation"
        ),
    },
]


def get_patterns() -> list[dict]:
    return _PATTERNS
