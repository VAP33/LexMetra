import numpy as np

from product_identity import decode_barcodes, best_barcode


def test_no_barcode_in_blank_image_returns_empty_list_not_crash():
    blank = np.ones((400, 400, 3), dtype="uint8") * 255
    assert decode_barcodes(blank) == []
    assert best_barcode(blank) is None


def test_real_photo_barcode_decodes_correctly():
    """
    Regression check against a real, user-supplied photo (not synthetic):
    dataset/real_photos - a BRU instant coffee jar. The EAN-13 barcode is
    visually confirmable in the photo. This is exactly the kind of
    "measured against a real image" check the master spec requires instead
    of asserting success from synthetic fixtures alone.
    """
    import cv2
    from pathlib import Path

    photo = (
        Path(__file__).parent.parent.parent
        / "dataset" / "real_photos"
        / "Screenshot_2026-09-06-22-06-12-38_92460851df6f172a4592fca41cc2d2e6.jpg"
    )
    if not photo.exists():
        import pytest
        pytest.skip("real photo fixture not present in this checkout")

    img = cv2.imread(str(photo))
    result = best_barcode(img)
    assert result is not None
    assert result.data == "8909106043251"
    assert result.symbology.upper() == "EAN13"
