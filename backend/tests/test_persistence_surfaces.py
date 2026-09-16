import pytest
from backend.db.persistence import (
    SURFACE_COLUMNS,
    build_surface_row,
    hydrate_surface_row,
)
from backend.schema import InspectionSurface, SurfaceType


def test_surface_columns_and_builder_agree():
    row = build_surface_row("test-insp", InspectionSurface(surface_id="s1"))
    assert set(row.keys()) == set(SURFACE_COLUMNS)


def test_surface_row_round_trip():
    surface = InspectionSurface(
        surface_id="surf_front_01",
        surface_type=SurfaceType.FRONT,
        priority_score=0.85,
        original_image_path="/path/to/orig.jpg",
        canonical_image_path="/path/to/canon.png",
        transform_matrix=[[1.0, 0.0, 5.0], [0.0, 1.0, 10.0], [0.0, 0.0, 1.0]],
        declaration_density=4.2,
        dimensions={"width": 1200, "height": 1800},
        notes=["Good lighting", "Rectified via letterbox crop"],
    )

    row = build_surface_row("insp_123", surface)
    assert row["inspection_id"] == "insp_123"
    assert row["surface_id"] == "surf_front_01"
    assert row["surface_type"] == "FRONT"
    assert row["priority_score"] == 0.85

    hydrated = hydrate_surface_row(row)
    assert hydrated["surface_id"] == "surf_front_01"
    assert hydrated["surface_type"] == "FRONT"
    assert hydrated["priority_score"] == 0.85
    assert hydrated["transform_matrix"] == [[1.0, 0.0, 5.0], [0.0, 1.0, 10.0], [0.0, 0.0, 1.0]]
    assert hydrated["dimensions"] == {"width": 1200, "height": 1800}
    assert hydrated["notes"] == ["Good lighting", "Rectified via letterbox crop"]
