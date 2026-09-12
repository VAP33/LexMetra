from pathlib import Path

PATCH = Path(__file__).resolve().parent / "amendments_patch.diff"
ROOT = Path(__file__).resolve().parent


def main():
    required = [
        ROOT / "backend" / "regulatory" / "versions.py",
        ROOT / "backend" / "tests" / "test_build05_rule_versioning.py",
        ROOT / "BUILD_05.md",
        PATCH,
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit("Missing Build 05 files: " + ", ".join(missing))

    print("Build 05 files are present.")
    print("Apply amendments_patch.diff manually with git apply --check first.")
    print("No source file is modified automatically by this script.")


if __name__ == "__main__":
    main()
