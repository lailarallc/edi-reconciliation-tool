"""The prod guard sits in front of every write path to Postgres.

`corpus.loader._connect()` feeds TRUNCATE/INSERT and `make transform` runs dbt
seed/run, both at localhost:5432 by default -- a `fly proxy` tunnel to
production when one is open. These tests fake a flyctl listener and assert
nothing connects.
"""

import pathlib
import re

import pytest

from corpus import loader, prod_guard

ROOT = pathlib.Path(__file__).parent.parent

_DB_ENV = ("DATABASE_URL", "POSTGRES_HOST", "POSTGRES_PORT", "PGHOST", "PGPORT")


@pytest.fixture
def fly_tunnel(monkeypatch):
    for var in _DB_ENV + ("ALLOW_PROD_DB",):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(prod_guard, "_listener", lambda port: "flyctl")
    psycopg2 = pytest.importorskip("psycopg2")
    monkeypatch.setattr(psycopg2, "connect", lambda *a, **kw: pytest.fail("connected"))


def test_connect_refuses_fly_tunnel_on_default_port(fly_tunnel):
    with pytest.raises(prod_guard.ProdDatabaseError):
        loader._connect()


def test_connect_refuses_fly_tunnel_via_database_url(fly_tunnel, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/cinderhaven")
    with pytest.raises(prod_guard.ProdDatabaseError):
        loader._connect()


def test_connect_guards_the_configured_port(fly_tunnel, monkeypatch):
    seen = []
    monkeypatch.setenv("POSTGRES_PORT", "15432")
    monkeypatch.setattr(prod_guard, "_listener", lambda port: seen.append(port) or "flyctl")
    with pytest.raises(prod_guard.ProdDatabaseError):
        loader._connect()
    assert seen == [15432]


def test_make_transform_guards_before_dbt():
    recipe = re.search(r"^transform:\n((?:\t.*\n)+)", (ROOT / "Makefile").read_text(), re.M)
    assert recipe, "transform target not found"
    lines = [ln.strip() for ln in recipe.group(1).splitlines() if not ln.strip().startswith("@echo")]
    assert "prod_guard.py" in lines[0], "guard must run before any dbt command"
    assert "${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}" in lines[0].replace("$$", "$")


def test_guard_cli_blocks_fly_tunnel(fly_tunnel):
    assert prod_guard.main(["prod_guard.py", "localhost:5432"]) == 1
