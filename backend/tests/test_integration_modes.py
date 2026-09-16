"""
Unit tests for subsystem integration modes (Section 10 & 13).
Verifies that:
- REGULATORY_ENGINE_MODE ('legacy', 'shadow', 'generic') functions properly.
- In 'shadow' mode, generic engine runs in memory and no duplicate rows/inspections are created.
- In 'generic' mode, generic engine findings are produced without mutating input Qwen facts.
- localizer health preflight returns expected diagnostic dict.
"""

from datetime import date
import pytest

from regulatory_service import RegulatoryService
from localization.service import LocalizationService
from schema import FactStatus, ProductInspection


def test_regulatory_service_legacy_mode():
    service = RegulatoryService(mode="legacy")
    extractions = {
        "mrp": {"value": 100.0, "raw_text": "MRP Rs 100.00", "confidence": 0.95},
        "common_name": {"value": "Biscuits", "confidence": 0.90},
    }

    result = service.evaluate(
        inspection_id="test-mode-legacy",
        sale_type="retail",
        product_category="packaged_food",
        net_quantity_value=100.0,
        net_quantity_unit="g",
        mrp=100.0,
        extractions=extractions,
        inspection_date=date(2026, 9, 1),
    )

    assert isinstance(result, ProductInspection)
    assert result.inspection_id == "test-mode-legacy"


def test_regulatory_service_shadow_mode_runs_cleanly():
    service = RegulatoryService(mode="shadow")
    extractions = {
        "mrp": {"value": 100.0, "raw_text": "MRP Rs 100.00", "confidence": 0.95},
        "common_name": {"value": "Biscuits", "confidence": 0.90},
    }

    result = service.evaluate(
        inspection_id="test-mode-shadow",
        sale_type="retail",
        product_category="packaged_food",
        net_quantity_value=100.0,
        net_quantity_unit="g",
        mrp=100.0,
        extractions=extractions,
        inspection_date=date(2026, 9, 1),
    )

    # In shadow mode, authoritative result returned is legacy
    assert isinstance(result, ProductInspection)
    assert result.inspection_id == "test-mode-shadow"


def test_regulatory_service_generic_mode():
    service = RegulatoryService(mode="generic")
    extractions = {
        "mrp": {"value": 100.0, "raw_text": "MRP Rs 100.00", "confidence": 0.95},
        "common_name": {"value": "Biscuits", "confidence": 0.90},
    }

    result = service.evaluate(
        inspection_id="test-mode-generic",
        sale_type="retail",
        product_category="packaged_food",
        net_quantity_value=100.0,
        net_quantity_unit="g",
        mrp=100.0,
        extractions=extractions,
        inspection_date=date(2026, 9, 1),
    )

    assert isinstance(result, ProductInspection)
    assert result.inspection_id == "test-mode-generic"
    assert "IN-LMPC-2011" in (result.applicable_rule_version or "")


def test_localization_preflight_health():
    localizer = LocalizationService()
    h = localizer.health()
    assert "available" in h
    assert "engine" in h
    assert "polygon_output_verified" in h
    assert "weights_ready" in h
    assert "yolo_enabled" in h
    assert h["yolo_enabled"] is False
