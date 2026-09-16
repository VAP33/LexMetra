from types import SimpleNamespace

from rule_engine import run_inspection
from schema import FactStatus


def test_sticker_signal_never_fails():
    region = SimpleNamespace(
        bbox=(10, 10, 40, 20),
        confidence=0.8,
        reason="color-boundary 0.4",
        signals={"color_boundary": 0.4, "print_pattern_discontinuity": 0.3},
    )
    result = run_inspection(
        inspection_id="sticker-cap",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},
        sticker_suspects=[region],
    )
    sticker_facts = [f for f in result.facts if f.field == "__possible_alteration__"]
    assert sticker_facts
    assert all(f.status is FactStatus.UNCERTAIN for f in sticker_facts)
    advisory = [f for f in result.findings if f.rule_id == "ADVISORY-CV-STICKER"]
    assert advisory
    assert all(f.status is FactStatus.UNCERTAIN for f in advisory)
    assert all(f.status is not FactStatus.FAIL for f in advisory)


def test_sticker_signals_are_named():
    from sticker_detection import _candidate_score
    import numpy as np

    gray = np.full((80, 80), 180, np.uint8)
    gray[20:50, 20:50] = 40
    score, signals = _candidate_score(gray, (20, 20, 30, 30), 0.8)
    assert "color_boundary" in signals
    assert "print_pattern_discontinuity" in signals
    assert 0.0 <= score <= 1.0
