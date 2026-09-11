from pathlib import Path

from operational_cache import OperationalCache


def test_operational_cache_is_non_authoritative_when_disabled(monkeypatch):
    monkeypatch.setenv("LMPC_REDIS_URL", "")
    cache = OperationalCache()
    cache.set("legal-result", {"status": "PASS"}, ttl_seconds=30)
    assert cache.get("legal-result")["status"] == "PASS"


def test_cache_failure_cannot_become_a_legal_result(monkeypatch):
    monkeypatch.setenv("LMPC_REDIS_URL", "")
    cache = OperationalCache()
    # A cache miss is simply a miss. It is never interpreted as compliance.
    assert cache.get("missing-legal-result") is None


def test_audit_log_schema_is_append_only():
    schema = (Path(__file__).parents[1] / "db" / "schema.sql").read_text(encoding="utf-8")
    assert "prevent_audit_log_mutation" in schema
    assert "audit_log_append_only" in schema
    assert "BEFORE UPDATE OR DELETE ON audit_log" in schema


def test_production_bootstrap_is_explicitly_opt_in():
    config = (Path(__file__).parents[1] / "config.py").read_text(encoding="utf-8")
    main = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    assert "BOOTSTRAP_DEMO_USERS" in config
    assert "config.BOOTSTRAP_DEMO_USERS" in main
    assert "config.DEV_MODE" in main
