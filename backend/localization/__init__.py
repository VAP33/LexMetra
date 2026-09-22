"""
Localization package providing evidence localization and polygon extraction
using ported PaddleOCR CV components under strict isolation.
"""

from localization.models import (
    BoundingBoxCanonical,
    LocalizationStatus,
    LocalizationSurface,
    LocalizedEvidence,
)

__all__ = [
    "LocalizationStatus",
    "LocalizationSurface",
    "BoundingBoxCanonical",
    "LocalizedEvidence",
]
