#!/usr/bin/env python3
"""
Minimal pytest-compatible test runner for environments without pytest installed.

WHY THIS EXISTS
---------------
The test suite is written in ordinary pytest style and MUST stay that way, so it
runs unchanged under real pytest in CI and on any developer machine. But this
container has no network access, so `pip install pytest` fails and the suite
would otherwise be unrunnable — which in practice means unrun, which is exactly
how a project ends up claiming "verified" without having tested anything.

This runner installs a small shim under the name `pytest` and then collects and
executes the test modules itself. It implements only the pytest surface the suite
actually uses: `approx`, `fixture` (including `scope=` and generator teardown),
`mark.skipif`, `raises`, and `skip`. It is NOT a pytest replacement; if a future
test needs parametrize, monkeypatch, tmp_path or anything else, the honest fix is
to install pytest, and this runner will fail loudly rather than silently skipping
the test.

If the real pytest IS importable, this script defers to it instead of shimming,
so results here and in CI cannot diverge.

USAGE
-----
    python backend/tools/run_tests.py                    # whole suite
    python backend/tools/run_tests.py test_preprocess    # one module
    python backend/tools/run_tests.py -v                 # per-test lines
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import traceback
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_BACKEND = Path(__file__).resolve().parent.parent
_TESTS = _BACKEND / "tests"

for _p in (str(_BACKEND), str(_TESTS), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("LMPC_DEV_MODE", "true")


# ---------------------------------------------------------------------------
# The shim
# ---------------------------------------------------------------------------


class Skipped(Exception):
    """Raised to skip a test, mirroring pytest.skip()."""


class _Approx:
    """Tolerant float comparison, mirroring pytest.approx() for scalars."""

    def __init__(self, expected: Any, rel: Optional[float] = None,
                 abs: Optional[float] = None) -> None:
        self.expected = expected
        self.rel = 1e-6 if rel is None else rel
        self.abs = 1e-12 if abs is None else abs

    def _close(self, a: float, b: float) -> bool:
        return abs(a - b) <= max(self.abs, self.rel * max(abs(a), abs(b)))

    def __eq__(self, other: Any) -> bool:
        try:
            if isinstance(self.expected, (list, tuple)):
                if len(other) != len(self.expected):
                    return False
                return all(
                    self._close(float(x), float(y))
                    for x, y in zip(other, self.expected)
                )
            return self._close(float(other), float(self.expected))
        except (TypeError, ValueError):
            return NotImplemented

    def __repr__(self) -> str:
        return f"approx({self.expected!r}, rel={self.rel}, abs={self.abs})"


class _Raises:
    """Context manager mirroring pytest.raises()."""

    def __init__(self, expected, match: Optional[str] = None) -> None:
        self.expected = expected
        self.match = match
        self.value: Optional[BaseException] = None

    def __enter__(self) -> "_Raises":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            name = getattr(self.expected, "__name__", str(self.expected))
            raise AssertionError(f"DID NOT RAISE {name}")
        if not issubclass(exc_type, self.expected):
            return False
        if self.match is not None:
            import re

            if not re.search(self.match, str(exc)):
                raise AssertionError(
                    f"exception message {str(exc)!r} does not match {self.match!r}"
                )
        self.value = exc
        return True


#: name -> (function, scope). Populated by the @fixture decorator.
_FIXTURES: Dict[str, Tuple[Callable, str]] = {}


def _fixture(*args, **kwargs):
    scope = kwargs.get("scope", "function")

    def decorate(func: Callable) -> Callable:
        _FIXTURES[func.__name__] = (func, scope)
        return func

    # Support both @fixture and @fixture(...)
    if args and callable(args[0]) and not kwargs:
        return decorate(args[0])
    return decorate


class _Mark:
    @staticmethod
    def skipif(condition: bool, reason: str = "") -> Callable:
        def decorate(func: Callable) -> Callable:
            if condition:
                func.__lmpc_skip__ = reason or "skipif condition was true"
            return func

        return decorate

    def __getattr__(self, name: str) -> Callable:
        # Any other marker is a no-op decorator, matching pytest's behaviour of
        # ignoring unregistered markers rather than failing collection.
        def decorate(*a, **kw):
            if a and callable(a[0]):
                return a[0]
            return lambda f: f

        return decorate


def _skip(reason: str = "") -> None:
    raise Skipped(reason or "skipped")


def _fail(reason: str = "") -> None:
    raise AssertionError(reason or "explicit failure")


def _install_shim() -> types.ModuleType:
    shim = types.ModuleType("pytest")
    shim.approx = _Approx           # type: ignore[attr-defined]
    shim.fixture = _fixture         # type: ignore[attr-defined]
    shim.mark = _Mark()             # type: ignore[attr-defined]
    shim.raises = _Raises           # type: ignore[attr-defined]
    shim.skip = _skip               # type: ignore[attr-defined]
    shim.fail = _fail               # type: ignore[attr-defined]
    shim.Skipped = Skipped          # type: ignore[attr-defined]
    shim.__version__ = "0-lmpc-shim"  # type: ignore[attr-defined]
    sys.modules["pytest"] = shim
    return shim


# ---------------------------------------------------------------------------
# Fixture resolution
# ---------------------------------------------------------------------------


class _FixtureResolver:
    """Resolves fixture arguments, caching session-scoped values."""

    def __init__(self) -> None:
        self._session: Dict[str, Any] = {}
        self._teardowns: List[Any] = []

    def value(self, name: str, stack: Tuple[str, ...] = ()) -> Any:
        if name in stack:
            raise RuntimeError(f"circular fixture dependency: {' -> '.join(stack)}")
        if name in self._session:
            return self._session[name]
        if name not in _FIXTURES:
            raise RuntimeError(
                f"unknown fixture {name!r}. This runner implements only the pytest "
                "surface the suite currently uses; install real pytest if a test "
                "needs more."
            )
        func, scope = _FIXTURES[name]
        kwargs = {
            p: self.value(p, stack + (name,))
            for p in inspect.signature(func).parameters
        }
        produced = func(**kwargs)
        if inspect.isgenerator(produced):
            gen = produced
            result = next(gen)
            self._teardowns.append(gen)
        else:
            result = produced
        if scope in ("session", "module", "package"):
            self._session[name] = result
        return result

    def close(self) -> None:
        for gen in reversed(self._teardowns):
            try:
                next(gen)
            except StopIteration:
                pass
            except Exception:  # teardown failures must not mask test results
                traceback.print_exc()
        self._teardowns.clear()


# ---------------------------------------------------------------------------
# Collection and execution
# ---------------------------------------------------------------------------


def _load(path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def _collect_class_tests(module: types.ModuleType) -> List[Tuple[str, Any]]:
    """
    Collect `Test*` classes' `test_*` methods, the way pytest does.

    WHY THIS MATTERS MORE THAN IT LOOKS. This runner previously collected only
    module-level functions. A class-based test file was not reported as
    skipped or unsupported — it contributed zero tests and the suite still
    printed a green total. `test_declaration_pipeline.py` (8 tests across 4
    classes) was invisible for that reason on top of its import error, so
    "fixing" its import alone would still have run nothing.

    A test runner that silently counts nothing as success is the same failure
    mode this project keeps finding in its own code: a plausible-looking result
    standing in for a missing one. Classes are instantiated per test, matching
    pytest's isolation; a class with an `__init__` is skipped exactly as pytest
    skips it, with a warning rather than in silence.
    """
    collected: List[Tuple[str, Any]] = []
    for class_name in sorted(n for n in dir(module) if n.startswith("Test")):
        cls = getattr(module, class_name)
        if not inspect.isclass(cls):
            continue
        if cls.__init__ is not object.__init__:
            print(
                f"  WARNING: {class_name} defines __init__ and cannot be "
                "collected (pytest refuses these too)."
            )
            continue
        for method_name in sorted(n for n in dir(cls) if n.startswith("test_")):
            method = getattr(cls, method_name)
            if not callable(method):
                continue
            collected.append((
                f"{class_name}::{method_name}",
                _bind_method(cls, method_name),
            ))
    return collected


def _bind_method(cls: Any, method_name: str) -> Any:
    """Return a zero-arg-visible callable that instantiates `cls` per test."""
    def run(**kwargs: Any) -> Any:
        return getattr(cls(), method_name)(**kwargs)

    # The fixture resolver inspects the signature to decide what to inject, so
    # expose the method's parameters minus `self`.
    original = inspect.signature(getattr(cls, method_name))
    run.__signature__ = original.replace(  # type: ignore[attr-defined]
        parameters=[p for n, p in original.parameters.items() if n != "self"]
    )
    run.__name__ = method_name
    return run


def _install_pydantic_if_missing() -> bool:
    """
    Install the strict pydantic stand-in ONLY if real pydantic is unavailable.

    Returns True if the shim was installed. Without this, `schema.py` cannot be
    imported, so `rule_engine.py` cannot be imported, so the deterministic legal
    core — the part that decides PASS/FAIL/UNCERTAIN/EXEMPT — goes completely
    unexecuted. The real dependency stays declared in requirements.txt; see
    `pydantic_shim.py` for why shimming was preferred to rewriting the models.
    """
    try:
        import pydantic  # noqa: F401

        if getattr(pydantic, "__version__", "") != "0-lmpc-shim":
            return False
    except ImportError:
        pass

    import pydantic_shim

    pydantic_shim.install()
    return True


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verbose = "-v" in argv or "--verbose" in argv
    selectors = [a for a in argv if not a.startswith("-")]

    try:
        import pytest as _real  # noqa: F401

        if getattr(_real, "__version__", "") != "0-lmpc-shim":
            print("Real pytest is available; use it instead:")
            print("    python -m pytest backend/tests -q")
            return 0
    except ImportError:
        pass

    _install_shim()
    shimmed_pydantic = _install_pydantic_if_missing()

    files = sorted(_TESTS.glob("test_*.py"))
    if selectors:
        files = [
            f for f in files
            if any(s in f.stem for s in selectors)
        ]
    if not files:
        print("No test modules matched.")
        return 1

    # conftest must be imported first so its fixtures register.
    conftest = _TESTS / "conftest.py"
    if conftest.exists():
        _load(conftest)

    passed = failed = skipped = 0
    failures: List[Tuple[str, str]] = []
    resolver = _FixtureResolver()

    for path in files:
        try:
            module = _load(path)
        except Skipped as exc:
            print(f"{path.stem}: SKIPPED MODULE ({exc})")
            skipped += 1
            continue
        except Exception:
            print(f"{path.stem}: COLLECTION ERROR")
            failures.append((path.stem, traceback.format_exc()))
            failed += 1
            continue

        names = [n for n in dir(module) if n.startswith("test_")]
        tests = [
            (n, getattr(module, n))
            for n in sorted(names)
            if callable(getattr(module, n))
        ]
        tests.extend(_collect_class_tests(module))
        if not tests:
            continue

        mod_pass = mod_fail = mod_skip = 0
        for name, func in tests:
            reason = getattr(func, "__lmpc_skip__", None)
            if reason:
                mod_skip += 1
                if verbose:
                    print(f"  SKIP {path.stem}::{name} ({reason})")
                continue
            try:
                kwargs = {
                    p: resolver.value(p)
                    for p in inspect.signature(func).parameters
                }
                func(**kwargs)
            except Skipped as exc:
                mod_skip += 1
                if verbose:
                    print(f"  SKIP {path.stem}::{name} ({exc})")
            except Exception:
                mod_fail += 1
                failures.append((f"{path.stem}::{name}", traceback.format_exc()))
                if verbose:
                    print(f"  FAIL {path.stem}::{name}")
            else:
                mod_pass += 1
                if verbose:
                    print(f"  ok   {path.stem}::{name}")

        passed += mod_pass
        failed += mod_fail
        skipped += mod_skip
        status = "FAIL" if mod_fail else "ok"
        print(
            f"{path.stem:<28} {mod_pass:>3} passed  {mod_fail:>3} failed  "
            f"{mod_skip:>3} skipped  [{status}]"
        )

    resolver.close()

    if failures:
        print("\n" + "=" * 72)
        for name, tb in failures:
            print(f"FAILED {name}")
            print(tb)
            print("-" * 72)

    print("=" * 72)
    print(f"TOTAL: {passed} passed, {failed} failed, {skipped} skipped")
    print(
        "Runner: bundled pytest shim (no network in this environment). "
        "Run under real pytest before trusting a release."
    )
    if shimmed_pydantic:
        print(
            "pydantic: STRICT TEST SHIM in use (backend/tools/pydantic_shim.py). "
            "The legal core really executed, but required-field, ge/le and "
            "extra=forbid checks are the shim's, not pydantic's. Re-run under real "
            "pydantic before any release or accuracy claim."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
