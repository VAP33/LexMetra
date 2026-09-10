import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from backend.ocr_engine import (
    FusionState,
    OcrEngineName,
    OcrObservation,
    PaddleOcrEngine,
    fuse_observations,
    read_regions,
)
from backend.orientation import Orientation
from backend.region_detection import DetectedRegion, DetectionMethod, RegionType
from backend.rule_engine import FactStatus, run_inspection
from backend.runtime_hardening import (
    CachePolicy,
    CircuitOpenError,
    EngineStatus,
    FailureCircuit,
    TTLCache,
    stable_cache_key,
)


def test_cache_expires_and_is_bounded():
    cache = TTLCache(CachePolicy(ttl_seconds=1, max_items=2))
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert len(cache._items) == 2
    assert cache.get("a") is None
    assert cache.get("c") == 3


def test_cache_key_is_stable_and_namespaced():
    assert stable_cache_key("rag", "rule6", "2026-01-01") == stable_cache_key("rag", "rule6", "2026-01-01")
    assert stable_cache_key("rag", "x") != stable_cache_key("inspection", "x")


def test_circuit_opens_only_after_threshold_and_recovers():
    circuit = FailureCircuit(failure_threshold=2, cooldown_seconds=1)
    assert circuit.allow()
    circuit.failure()
    assert circuit.allow()
    circuit.failure()
    assert not circuit.allow()
    time.sleep(1.02)
    assert circuit.allow()
    circuit.success()
    assert circuit.allow()


def test_circuit_run_never_returns_fake_value_on_failure():
    circuit = FailureCircuit(failure_threshold=1)
    def boom():
        raise RuntimeError("provider failed")
    try:
        circuit.run(boom)
    except RuntimeError:
        pass
    else:
        raise AssertionError("provider failure was swallowed")
    try:
        circuit.run(lambda: "must not run")
    except CircuitOpenError:
        pass
    else:
        raise AssertionError("open circuit executed provider")


# ---------------------------------------------------------------------------
# Build 10 Hardening Correction: PaddleOCR Native Runtime Isolation Tests
# ---------------------------------------------------------------------------


def test_engine_discovery_is_safe_and_does_not_eagerly_import_native_deps():
    """Test A: Calling active_engines() must not eagerly load PaddleOCR or Torch native libraries."""
    code = (
        "import sys\n"
        "import ocr_engine as oe\n"
        "engines, notes = oe.active_engines()\n"
        "assert any(getattr(e, 'name', '') == oe.OcrEngineName.PADDLEOCR for e in engines), 'PaddleOCR must be in active engines'\n"
        "assert 'paddleocr' not in sys.modules, f'paddleocr was eagerly imported: {list(sys.modules)}'\n"
        "assert 'torch' not in sys.modules, f'torch was eagerly imported: {list(sys.modules)}'\n"
        "print('SAFE_DISCOVERY_OK')\n"
    )
    backend_dir = str(Path(__file__).resolve().parent.parent)
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{backend_dir}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else backend_dir
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert "SAFE_DISCOVERY_OK" in res.stdout


def test_paddle_worker_crash_is_contained_and_marks_degraded():
    """Test B: A crashed/terminated PaddleOCR worker process does not terminate parent and degrades gracefully."""
    import backend.ocr_engine as oe
    orig_status = oe._PADDLE.status
    orig_worker = oe._PADDLE._worker
    try:
        assert oe._PADDLE.available()

        # Start worker and simulate an abnormal process termination/crash
        assert oe._PADDLE._start_worker()
        worker_proc = oe._PADDLE._worker
        assert worker_proc is not None
        worker_proc.kill()
        worker_proc.wait(timeout=3)

        # Calling read on the crashed engine must not raise an unhandled exception or kill the process
        test_img = np.full((100, 100, 3), 255, dtype=np.uint8)
        lines = oe._PADDLE.read(test_img)

        assert lines == []
        assert oe._PADDLE.status == EngineStatus.DEGRADED
        assert not oe._PADDLE.available()
        assert "terminated unexpectedly" in oe._PADDLE.error or "communication failed" in oe._PADDLE.error

        # active_engines() must now omit PaddleOCR and report its degradation note
        engs, notes = oe.active_engines()
        assert not any(getattr(e, "name", "") == oe.OcrEngineName.PADDLEOCR for e in engs)
        assert any("paddle" in n.lower() for n in notes)

        # read_regions must continue and fall back cleanly to Tesseract
        region = DetectedRegion(
            region_type=RegionType.TEXT,
            bbox=(10, 10, 80, 40),
            confidence=0.9,
            method=DetectionMethod.MORPH_TEXT_BLOCKS,
        )
        readings, calls = read_regions(test_img, [region])
        assert len(readings) == 1
        assert readings[0].region.region_type == RegionType.TEXT
    finally:
        oe._PADDLE.status = orig_status
        oe._PADDLE._worker = orig_worker


def test_paddle_tesseract_corroboration_and_conflict_handling():
    """Test C: Compatible evidence is corroborated; incompatible evidence is marked conflicting."""
    # Corroborating readings from Tesseract and PaddleOCR
    tess_obs = OcrObservation(
        text="NET QUANTITY 100 g",
        bbox=(10, 10, 150, 30),
        confidence=0.85,
        engine=OcrEngineName.TESSERACT,
        orientation=Orientation.DEG_0,
        variant_name="original",
        variant_recipe=(),
        region_id="r0",
        region_type=RegionType.TEXT,
        region_bbox=(0, 0, 200, 100),
    )
    paddle_obs = OcrObservation(
        text="NET QUANTITY 100 g",
        bbox=(12, 11, 148, 29),
        confidence=0.90,
        engine=OcrEngineName.PADDLEOCR,
        orientation=Orientation.DEG_0,
        variant_name="original",
        variant_recipe=(),
        region_id="r0",
        region_type=RegionType.TEXT,
        region_bbox=(0, 0, 200, 100),
    )

    fused, conflicts = fuse_observations([tess_obs, paddle_obs])
    assert len(fused) == 1
    assert fused[0].fusion_state == FusionState.CORROBORATED
    assert fused[0].confidence > 0.90
    assert len(conflicts) == 0

    # Conflicting readings (numeric clash between 100 g and 700 g)
    clashing_paddle_obs = OcrObservation(
        text="NET QUANTITY 700 g",
        bbox=(12, 11, 148, 29),
        confidence=0.90,
        engine=OcrEngineName.PADDLEOCR,
        orientation=Orientation.DEG_0,
        variant_name="original",
        variant_recipe=(),
        region_id="r0",
        region_type=RegionType.TEXT,
        region_bbox=(0, 0, 200, 100),
    )

    fused_clash, conflicts_clash = fuse_observations([tess_obs, clashing_paddle_obs])
    assert len(fused_clash) == 1
    assert fused_clash[0].fusion_state == FusionState.CONFLICTING
    assert len(conflicts_clash) == 1
    assert conflicts_clash[0]["numeric_disagreement"] is True
    assert conflicts_clash[0]["resolution"] == "CONFLICT_REVIEW"


def test_ocr_failure_cannot_produce_legal_failure():
    """Test D: Missing OCR evidence due to degradation or failure is NOT_OBSERVED, never a direct legal FAIL."""
    # When OCR fails or is degraded and provides no observations for a package inspection
    result = run_inspection(
        inspection_id="t-ocr-degraded-nocaptures",
        sale_type="retail",
        product_category="household",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},
        captures=None,
    )
    # OCR absence/failure must never directly produce legal non-compliance
    assert FactStatus.FAIL not in [f.status for f in result.facts]
    assert result.overall_status == FactStatus.UNCERTAIN

