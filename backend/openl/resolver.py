"""OpenL RuleSet resolver slice (RULE-01).

Exemption only. Production /inspect and /scan stay on rule_engine.py until
every migrated rule proves differential parity. When LMPC_ENABLE_OPENL is
true, callers may route exemption classification through OpenL with an
automatic fallback to exemption.py.
"""
from __future__ import annotations

from typing import Optional

from exemption import ExemptionInput, ExemptionResult, classify_exemption

try:
    import config as _config
except Exception:  # pragma: no cover
    _config = None


def openl_enabled() -> bool:
    if _config is not None:
        return bool(getattr(_config, "ENABLE_OPENL", False))
    import os

    return os.environ.get("LMPC_ENABLE_OPENL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def classify_exemption_resolved(
    inp: ExemptionInput,
    *,
    force_openl: Optional[bool] = None,
) -> ExemptionResult:
    """Legal decision for Rule 3 / 26(a).

    Default: legacy ``exemption.classify_exemption`` (parity reference).
    OpenL path is opt-in and falls back to the legacy function on any error
    so a down JVM never converts an inspection into a crash or a false FAIL.
    """
    use_openl = openl_enabled() if force_openl is None else force_openl
    if not use_openl:
        return classify_exemption(inp)
    try:
        try:
            from openl.openl_client import OpenLExemptionClient
        except ImportError:  # scripts add backend/openl to path
            from openl_client import OpenLExemptionClient

        return OpenLExemptionClient().classify(inp)
    except Exception:
        return classify_exemption(inp)
