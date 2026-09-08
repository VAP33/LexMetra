"""
Centralized configuration loaded from environment variables (.env in dev).

Nothing in this module should contain a real secret. Defaults are
localhost/dev-only and are intentionally weak so they are obviously unsafe to
deploy as-is.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env if present (development convenience only). In production,
# environment variables should be supplied by the deployment platform instead.
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://lmpc_app:lmpc_dev_pw@localhost:5432/lmpc",
)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))

# When true (default in absence of an explicit secret), the API refuses to
# start with the insecure default secret outside of an explicit dev mode.
DEV_MODE = _env_bool("LMPC_DEV_MODE", True)

if not JWT_SECRET_KEY:
    if DEV_MODE:
        # Deterministic-but-obviously-not-production secret so local
        # development and automated tests work without extra setup.
        JWT_SECRET_KEY = "dev-only-insecure-secret-change-me"
    else:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set via environment variable when "
            "LMPC_DEV_MODE is not enabled. Refusing to start with no secret."
        )

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = _env_list(
    "ALLOWED_ORIGINS",
    ["http://localhost:5173", "http://localhost:8000", "http://127.0.0.1:5500"],
)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path(
    os.environ.get(
        "UPLOAD_DIR",
        str(Path(__file__).resolve().parent / "uploads"),
    )
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR",
        str(Path(__file__).resolve().parent / "reports"),
    )
)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Optional external services
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
VLM_VERIFICATION_ENABLED = _env_bool("VLM_VERIFICATION_ENABLED", False) and bool(
    ANTHROPIC_API_KEY
)
