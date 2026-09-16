from ocr_extraction import OcrLine, _tesseract_lang_flag
import ocr_engine as oe
import region_detection as rd
from orientation import Orientation
from region_detection import DetectionResult


def test_language_flag_default_is_english():
    assert "eng" in _tesseract_lang_flag()


def test_ocr_line_carries_source_engine():
    line = OcrLine("MRP Rs 10", (0, 0, 10, 10), 0.9, source_engine="tesseract")
    assert line.source_engine == "tesseract"


def test_fusion_adapter_sets_source_engine():
    obs = oe.OcrObservation(
        text="NET QUANTITY 100 g",
        bbox=(10, 10, 180, 22),
        confidence=0.95,
        engine=oe.OcrEngineName.TESSERACT,
        orientation=Orientation.DEG_0,
        variant_name="v0",
        variant_recipe=("synthetic",),
        region_id="r0",
        region_type=rd.RegionType.TEXT,
        region_bbox=(0, 0, 400, 200),
        fusion_state=oe.FusionState.SINGLE_SOURCE,
    )
    reading = oe.ImageReading(
        observations=[obs],
        region_readings=[],
        detection=DetectionResult(image_width=400, image_height=200),
        engines_used=(oe.OcrEngineName.TESSERACT,),
    )
    lines = reading.lines
    assert lines
    assert lines[0].source_engine == "tesseract"
