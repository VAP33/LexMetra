#!/usr/bin/env python3
"""
Minimal dependency-free test runner for backend/engine/tests/.

This project's sandbox has no network access and pytest is not preinstalled,
so this script provides an equivalent (though less featureful) way to run
the same plain-`assert`-based test functions. In any environment that DOES
have pytest available (e.g. `pip install -r backend/requirements.txt`),
these same files run unmodified under ``pytest backend/engine/tests``.

Usage:
    python3 backend/engine/tests/run_tests.py
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent


def discover_test_files():
    return sorted(p for p in THIS_DIR.glob("test_*.py"))


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def run() -> int:
    total = 0
    failures = []
    for path in discover_test_files():
        module = load_module(path)
        test_funcs = [
            (name, obj) for name, obj in vars(module).items()
            if name.startswith("test_") and callable(obj)
        ]
        for name, func in test_funcs:
            total += 1
            try:
                func()
                print(f"PASS  {path.name}::{name}")
            except Exception as exc:  # noqa: BLE001
                failures.append((path.name, name, exc, traceback.format_exc()))
                print(f"FAIL  {path.name}::{name}  -- {exc}")

    print()
    print(f"Ran {total} tests, {len(failures)} failed, {total - len(failures)} passed.")
    if failures:
        print("\n--- Failure details ---")
        for fname, tname, exc, tb in failures:
            print(f"\n{fname}::{tname}")
            print(tb)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
