"""Public display labels for Cinderhaven trade partners.

Reads the vendored reference/retailer_display_labels.json (synced from the
cinderhaven-data-platform by scripts/refresh_canonical.py). The data keeps the
real partner IDs; every rendered surface that puts a partner beside a
Cinderhaven dollar figure shows the label instead (lailara-website DECISIONS
2026-11-05). Display layer only: IDs, filter values, and queries are untouched.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_LABELS_JSON = Path(__file__).resolve().parent.parent / "reference" / "retailer_display_labels.json"

# This corpus keys partners by their EDI partner codes, not the label map's
# RET-*/DIST-* IDs. The labels themselves still come only from the shared map.
_PARTNER_CODE_TO_MAP_ID = {
    "WALMARTUS": "RET-WALMART",
    "UNFI": "DIST-UNFI",
    "KEHE": "DIST-KEHE",
}


@lru_cache(maxsize=1)
def _lookup() -> dict[str, str]:
    """Map partner codes, map IDs (RET-*, DIST-*) and real names to labels."""
    data = json.loads(_LABELS_JSON.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for group in ("retailers", "distributors"):
        for map_id, entry in data[group].items():
            out[map_id] = entry["label"]
            out[entry["name"]] = entry["label"]
    for code, map_id in _PARTNER_CODE_TO_MAP_ID.items():
        out[code] = out[map_id]
    return out


_warned_unmapped: set[str] = set()


def display_label(partner, capitalize: bool = True) -> str:
    """Return the public label for a partner code, map ID, or real name.

    capitalize=True for table cells, badges and dropdown text; False for
    mid-sentence use. Unknown values pass through unchanged, with one warning
    per value: a new partner code would otherwise render raw beside dollars.
    """
    key = "" if partner is None else str(partner)
    label = _lookup().get(key)
    if label is None:
        if key and key not in _warned_unmapped:
            _warned_unmapped.add(key)
            logger.warning("partner %r has no display label in %s", key, _LABELS_JSON.name)
        label = key
    if capitalize and label:
        return label[0].upper() + label[1:]
    return label


def _short_form(partner) -> str:
    """Short form of a partner's label: "distributor A" -> "A",
    "national mass retailer" -> "NMR". Derived from the map's label."""
    label = display_label(partner, capitalize=False)
    m = re.fullmatch(r"distributor (\w+)", label)
    if m:
        return m.group(1)
    return "".join(word[0] for word in label.split()).upper()


# Order and invoice IDs embed the partner: DPO-KEHE-000123, UNFI-INV-000123,
# WMT-INV-000123 (WMT is the retailer's ticker). Display only: the segment is
# swapped for the label's short form (DPO-B-000123, A-INV-000123,
# NMR-INV-000123), as the deductions tool does for DPO-A-. PO-ART- is a code
# fragment, not a name, and stays (lailara-website DECISIONS 2026-11-05 (d)).
_ID_PATTERNS = (
    re.compile(r"^(DPO-)(?:KEHE|UNFI)(-)"),
    re.compile(r"^()(?:KEHE|UNFI|WMT)(-INV-)"),
)


def display_id(value, partner) -> str:
    """Public form of a PO or invoice number for a row belonging to partner."""
    if not value:
        return value
    text = str(value)
    short = _short_form(partner)
    for pattern in _ID_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}{short}{m.group(2)}", text)
    return text
