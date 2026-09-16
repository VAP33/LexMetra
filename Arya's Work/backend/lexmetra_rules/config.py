"""
Configuration and Tesseract discovery.

The brief is explicit: the Windows test environment has Tesseract at
``C:\\Program Files\\Tesseract-OCR\\tesseract.exe`` but that path must NOT be
hard-coded as *the* location. This module treats it as one of several
fallback candidates, tried only after explicit configuration and PATH
discovery, and works the same way on Linux/macOS.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


#: Environment variable a caller/deployment can set to pin the exact binary.
TESSERACT_ENV_VAR = "LEXMETRA_TESSERACT_CMD"

#: Environment variable to pin the tessdata directory (language files).
TESSDATA_ENV_VAR = "LEXMETRA_TESSDATA_PREFIX"

#: Fallback install-location candidates, tried only if PATH lookup and the
#: env var both fail. Order matters: more specific / more recent first.
#: These are *candidates*, not requirements — every path here is checked
#: with os.path.exists before use, and none is assumed to exist.
_FALLBACK_CANDIDATES: List[str] = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
]


@dataclass(frozen=True)
class OcrConfig:
    """Resolved OCR configuration for one pipeline run."""

    tesseract_cmd: Optional[str]
    lang: str = "eng"
    dpi: int = 300
    psm: int = 6
    tessdata_dir: Optional[str] = None
    available_langs: List[str] = field(default_factory=list)


class MissingTesseractError(RuntimeError):
    """
    Raised only when OCR is actually required and no usable Tesseract binary
    could be located. Never raised speculatively at import time — a
    text-layer-only run (or a run that never needs OCR fallback) must not be
    blocked by the absence of Tesseract.
    """


def locate_tesseract(explicit_cmd: Optional[str] = None) -> Optional[str]:
    """
    Resolve the Tesseract binary path.

    Resolution order (first hit wins):
      1. ``explicit_cmd`` passed by the caller (e.g. a CLI flag).
      2. ``LEXMETRA_TESSERACT_CMD`` environment variable.
      3. ``tesseract`` on PATH (``shutil.which``).
      4. A short list of common install locations (existence-checked).

    Returns None if nothing usable was found. Does not raise — callers
    decide whether the absence matters yet.
    """
    if explicit_cmd:
        if os.path.isfile(explicit_cmd):
            return explicit_cmd
        return None

    env_cmd = os.environ.get(TESSERACT_ENV_VAR)
    if env_cmd and os.path.isfile(env_cmd):
        return env_cmd

    which_cmd = shutil.which("tesseract")
    if which_cmd:
        return which_cmd

    for candidate in _FALLBACK_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate

    return None


def resolve_ocr_config(
    *,
    lang: str = "eng",
    dpi: int = 300,
    psm: int = 6,
    explicit_tesseract_cmd: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
) -> OcrConfig:
    """
    Build an :class:`OcrConfig` without raising, even if Tesseract is
    missing — the error is deferred until OCR is actually attempted
    (see ``ocr.ocr_page``), so a native-text-only run works with zero
    Tesseract installation.
    """
    cmd = locate_tesseract(explicit_tesseract_cmd)
    tessdata = tessdata_dir or os.environ.get(TESSDATA_ENV_VAR)
    return OcrConfig(
        tesseract_cmd=cmd,
        lang=lang,
        dpi=dpi,
        psm=psm,
        tessdata_dir=tessdata,
    )


def require_tesseract(config: OcrConfig) -> str:
    """Raise MissingTesseractError with a clear, actionable message, or
    return the resolved command path."""
    if config.tesseract_cmd:
        return config.tesseract_cmd
    raise MissingTesseractError(
        "No usable Tesseract OCR binary was found. This page requires OCR "
        "because it has no usable native text layer. To fix this, do one "
        f"of: (1) install Tesseract and ensure it is on PATH, (2) set the "
        f"{TESSERACT_ENV_VAR} environment variable to the full path of "
        f"tesseract(.exe), or (3) pass --tesseract-cmd on the CLI. "
        "This module will not silently continue with empty text."
    )
