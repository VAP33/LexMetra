import os

import pytest

from openl.resolver import classify_exemption_resolved
from exemption import ExemptionInput, classify_exemption


def _openl_up() -> bool:
    try:
        import httpx
        import config

        url = getattr(config, "OPENL_BASE_URL", "http://localhost:8080").rstrip("/")
        resp = httpx.get(url + "/admin/healthcheck/readiness", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _openl_up(), reason="OpenL RuleServices is not running")
def test_openl_exemption_parity_sample():
    inp = ExemptionInput(
        sale_type="retail",
        product_category="food",
        net_quantity_value=5,
        net_quantity_unit="g",
    )
    old = classify_exemption(inp)
    new = classify_exemption_resolved(inp, force_openl=True)
    assert (old.is_exempt, old.exemption_type, old.rule_id) == (
        new.is_exempt,
        new.exemption_type,
        new.rule_id,
    )
