"""
Shared pytest fixtures.

Tests that need the database expect a running PostgreSQL instance reachable
via DATABASE_URL (see backend/.env.example). Import-level/unit tests for the
rule engine, exemption classifier, and auth hashing do not need a database
and will run anywhere.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("LMPC_DEV_MODE", "true")


def _db_available() -> bool:
    try:
        import config  # noqa
        import psycopg2

        conn = psycopg2.connect(config.DATABASE_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE, reason="PostgreSQL is not reachable via DATABASE_URL"
)


@pytest.fixture(scope="session")
def db_ready():
    if not DB_AVAILABLE:
        pytest.skip("PostgreSQL is not reachable via DATABASE_URL")
    from db import persistence as db

    db.init_schema()
    # Automated test runs assume a disposable dev/test database and start
    # from a clean slate so results do not depend on data left over from
    # manual curl/API exploration in the same DATABASE_URL. Never point this
    # test suite at a database containing real inspection records.
    if os.environ.get("LMPC_TEST_RESET_DB", "true").strip().lower() not in {"0", "false", "no"}:
        db.truncate_all_data()
    return db


@pytest.fixture(scope="session")
def api_client(db_ready):
    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app) as client:
        yield client


@pytest.fixture(scope="session")
def bootstrap_admin_token(api_client, db_ready):
    """
    Create (or reuse) the very first admin account for this test database.

    The API only allows one unauthenticated bootstrap registration per
    database. Every other test-created account goes through the admin-only
    endpoint using this token, so tests remain independent of run order.
    """
    import uuid

    username = f"bootstrap_admin_{uuid.uuid4().hex[:8]}"
    password = "testpassword123"
    resp = api_client.post(
        "/auth/register",
        json={"username": username, "password": password, "role": "admin"},
    )
    if resp.status_code == 200:
        login = api_client.post(
            "/auth/login", data={"username": username, "password": password}
        )
        assert login.status_code == 200, login.text
        return login.json()["access_token"]

    pytest.skip(
        "A user already exists in this database and no known admin "
        "credentials were provided; run against a clean test database to "
        "exercise the auth-dependent test suite."
    )


@pytest.fixture()
def admin_token(api_client, bootstrap_admin_token):
    """A fresh admin account per test, created via the bootstrap admin."""
    import uuid

    username = f"test_admin_{uuid.uuid4().hex[:8]}"
    password = "testpassword123"
    resp = api_client.post(
        "/auth/register/admin",
        json={"username": username, "password": password, "role": "admin"},
        headers={"Authorization": f"Bearer {bootstrap_admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    login = api_client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


@pytest.fixture()
def inspector_token(api_client, bootstrap_admin_token):
    """A fresh inspector-role account per test."""
    import uuid

    username = f"test_inspector_{uuid.uuid4().hex[:8]}"
    password = "testpassword123"
    resp = api_client.post(
        "/auth/register/admin",
        json={"username": username, "password": password, "role": "inspector"},
        headers={"Authorization": f"Bearer {bootstrap_admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    login = api_client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]
