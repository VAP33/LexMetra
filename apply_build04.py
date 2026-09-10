from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
REQ = BACKEND / "requirements.txt"


def has_requirement(text, package):
    package = package.lower()
    for row in text.splitlines():
        name = row.strip().split("=", 1)[0].split(">", 1)[0].split("<", 1)[0].strip().lower()
        if name == package:
            return True
    return False


def main():
    for path in (
        BACKEND / "regulatory" / "__init__.py",
        BACKEND / "regulatory" / "models.py",
        BACKEND / "tests" / "test_build04_rag_runtime_integrity.py",
    ):
        if not path.exists():
            raise SystemExit(f"Missing Build 04 file: {path}")

    req = REQ.read_text(encoding="utf-8")
    additions = []
    if not has_requirement(req, "scikit-learn"):
        additions.append("scikit-learn>=1.4,<2.0")
    if not has_requirement(req, "pypdf"):
        additions.append("pypdf>=5.0,<7.0")

    if additions:
        if not req.endswith("\n"):
            req += "\n"
        REQ.write_text(req + "\n".join(additions) + "\n", encoding="utf-8")

    print("Build 04 applied: regulatory compatibility package + RAG dependencies.")


if __name__ == "__main__":
    main()
