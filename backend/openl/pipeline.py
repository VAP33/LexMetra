"""Versioned OpenL deploy pipeline (RULE-02).

Generalizes RULE-01's one-off zip into an immutable, effective-dated manifest.
Does not migrate additional legal rules (that remains RULE-01 step 4).
Does not mutate rule_engine.py / exemption.py.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RULES_PATH = REPO / "rules" / "rules.json"
DIST = HERE / "dist"
MANIFEST_PATH = HERE / "manifests" / "deploy_manifest.jsonl"


@dataclass(frozen=True)
class DeployRecord:
    rule_family: str
    rule_ids: list[str]
    rule_version: str
    effective_from: str
    zip_path: str
    zip_sha256: str
    rules_json_sha256: str
    deployed_at: str
    deploy_method: str  # repo-zip | rest-deployer
    module: str = "lmpc"
    notes: str = ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rules_json_hash(path: Path = RULES_PATH) -> str:
    return sha256_file(path)


def record_deploy(
    *,
    rule_family: str,
    rule_ids: list[str],
    zip_path: Path,
    effective_from: str,
    rule_version: str = "from-rules.json",
    deploy_method: str = "repo-zip",
    module: str = "lmpc",
    notes: str = "",
    manifest_path: Path = MANIFEST_PATH,
) -> DeployRecord:
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise FileNotFoundError(f"OpenL zip not found: {zip_path}")
    record = DeployRecord(
        rule_family=rule_family,
        rule_ids=list(rule_ids),
        rule_version=rule_version,
        effective_from=effective_from,
        zip_path=str(zip_path),
        zip_sha256=sha256_file(zip_path),
        rules_json_sha256=rules_json_hash(),
        deployed_at=datetime.now(timezone.utc).isoformat(),
        deploy_method=deploy_method,
        module=module,
        notes=notes,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    return record


def load_manifest(manifest_path: Path = MANIFEST_PATH) -> list[dict[str, Any]]:
    if not manifest_path.is_file():
        return []
    rows = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def resolve_zip_for_date(
    inspection_date: date,
    *,
    module: str = "lmpc",
    rule_family: Optional[str] = None,
    manifest_path: Path = MANIFEST_PATH,
) -> Optional[dict[str, Any]]:
    """Pick the latest immutable zip whose effective_from <= inspection_date.

    A dated request with no resolvable version is None (error for the caller),
    never a silent fallback to 'today'.
    """
    eligible = []
    for row in load_manifest(manifest_path):
        if row.get("module") != module:
            continue
        if rule_family and row.get("rule_family") != rule_family:
            continue
        try:
            start = date.fromisoformat(str(row.get("effective_from")))
        except (TypeError, ValueError):
            continue
        if start <= inspection_date:
            eligible.append((start, row.get("deployed_at") or "", row))
    if not eligible:
        return None
    eligible.sort()
    return eligible[-1][2]


def seed_exemption_record_if_present() -> Optional[DeployRecord]:
    zip_path = DIST / "lmpc-exemption.zip"
    if not zip_path.is_file():
        return None
    existing = load_manifest()
    for row in existing:
        if row.get("rule_family") == "exemption" and row.get("zip_sha256") == sha256_file(zip_path):
            return None
    return record_deploy(
        rule_family="exemption",
        rule_ids=["LMPC-2011-R3-SCOPE", "LMPC-2011-R26-SMALL-PACKS"],
        zip_path=zip_path,
        effective_from="2011-04-01",
        notes="Seeded from RULE-01 lmpc-exemption.zip; zip is immutable.",
    )
