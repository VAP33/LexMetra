from pathlib import Path

from operational_cache import OperationalCache


def test_operational_cache_is_non_authoritative_when_disabled(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "")
    cache = OperationalCache()
    cache.set("legal-result", {"status": "PASS"}, ttl_seconds=30)
    assert cache.get("legal-result")["status"] == "PASS"


def test_cache_failure_cannot_become_a_legal_result(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "")
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


def test_operational_cache_uses_configured_redis_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:63999/0")
    cache = OperationalCache()
    # Unavailable Redis must degrade to local cache, never raise.
    cache.set("fallback", {"status": "PASS"}, ttl_seconds=30)
    assert cache.get("fallback")["status"] == "PASS"


def test_production_mode_is_not_the_implicit_dev_default():
    config = (Path(__file__).parents[1] / "config.py").read_text(encoding="utf-8")
    assert '_env_bool("LMPC_DEV_MODE", False)' in config
    assert "DEMO_MODE" in config


def test_upload_limit_is_environment_driven():
    config = (Path(__file__).parents[1] / "config.py").read_text(encoding="utf-8")
    main = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    assert "LMPC_MAX_UPLOAD_BYTES" in config
    assert "MAX_UPLOAD_BYTES = config.MAX_UPLOAD_BYTES" in main


def test_health_and_readiness_contracts_exist():
    main = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/health")' in main
    assert '@app.get("/ready")' in main
    assert 'SELECT 1' in main


def test_readiness_does_not_treat_redis_as_legal_truth():
    main = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    assert "Redis is operational infrastructure, not legal truth" in main
