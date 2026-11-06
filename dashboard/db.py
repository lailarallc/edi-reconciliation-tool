"""Database connection utilities for the dashboard.

Reads DATABASE_URL from the environment. When the variable is absent the
routes render their no-database state. When it is set and the database cannot
be reached, query() raises DataUnavailable, which the app serves as HTTP 503.
"""
from __future__ import annotations

import os
from typing import Any

_conn = None
_active_url: str | None = None

# dbt materializes mart models under this schema (profile target +schema: marts → edi_marts).
# Import in route modules instead of duplicating the literal.
MARTS_SCHEMA: str = "edi_marts"


class DataUnavailable(RuntimeError):
    """The configured database could not be reached (connection-class error).

    Raised instead of returning empty rows: an empty result renders as "no
    mismatches found", which is false when the data simply could not be read.
    The app serves it as HTTP 503. Other query errors (bad SQL, a missing
    table) are not outages and propagate as ordinary 500s.
    """


def is_configured() -> bool:
    """Return True if DATABASE_URL is present in the environment."""
    return bool(os.environ.get("DATABASE_URL"))


def _get_conn():
    """Return (connection, reused). reused is False for a fresh connection."""
    global _conn, _active_url
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    if _conn is None or _conn.closed or url != _active_url:
        import psycopg2  # noqa: PLC0415
        _conn = psycopg2.connect(url, connect_timeout=5)
        _conn.autocommit = True
        _active_url = url
        return _conn, False
    return _conn, True


def _drop_conn() -> None:
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:  # noqa: BLE001 — closing a dead socket may itself fail; it is discarded either way
            pass
    _conn = None


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute a SELECT query and return rows as plain dicts.

    A reused connection that fails with a connection-class error is dropped
    and the query retried once on a fresh one: a Fly machine resumed from
    suspend still holds sockets the database has already closed, so the
    first request after a resume would otherwise fail. Reads only, so the
    retry is safe. A failure on a fresh connection raises DataUnavailable.
    """
    import psycopg2  # noqa: PLC0415
    import psycopg2.extras  # noqa: PLC0415
    for attempt in (1, 2):
        reused = False  # stays False if connecting itself fails: no retry then
        try:
            conn, reused = _get_conn()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            _drop_conn()
            if attempt == 1 and reused:
                continue
            raise DataUnavailable(f"database unavailable: {exc}".strip()) from exc
    raise AssertionError("unreachable")
