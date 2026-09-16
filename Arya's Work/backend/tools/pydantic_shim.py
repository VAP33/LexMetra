#!/usr/bin/env python3
"""
A STRICT, TEST-ONLY stand-in for the small slice of pydantic that `schema.py` uses.

WHY THIS EXISTS
---------------
`schema.py` imports pydantic, and `rule_engine.py` imports `schema.py`. This
container has no network access, so pydantic cannot be installed. The consequence
was that the DETERMINISTIC LEGAL RULE ENGINE — the component that actually decides
PASS/FAIL/UNCERTAIN/EXEMPT — could not be imported, let alone executed or tested.
A legal-compliance system whose legal core has never been run is not a system, it
is a hypothesis.

The alternative was to rewrite `schema.py`'s models as plain dataclasses. That was
rejected deliberately: `schema.py` is also imported by `main.py`, `persistence.py`
and `ocr_extraction.py`, none of which can be executed here either, so the
refactor could not have been verified. Rewriting working legal code that cannot be
re-tested is a worse risk than shimming a dependency.

WHY IT IS STRICT, AND WHAT THAT DOES NOT MEAN
---------------------------------------------
A permissive stub would be actively dangerous here. If this shim silently accepted
`confidence=1.7`, or a misspelled field name, then a test could pass under the
shim and fail under real pydantic — and the test would be certifying a legal
guarantee that does not hold in production. So this shim ENFORCES the constraints
`schema.py` actually declares:

  * required fields (a `Field(...)` with no default) must be supplied
  * `ge` / `le` numeric bounds are checked
  * `extra="forbid"` rejects unknown keyword arguments
  * `default_factory` is called per instance, so mutable defaults are not shared
  * nested models and enums are constructed from plain dicts/strings, as pydantic
    would, so round-tripping through `model_dump()` behaves

It does NOT implement full type coercion, `constr`, custom validators, JSON schema
generation, or pydantic's error model. It raises `ValueError` where pydantic would
raise `ValidationError` (aliased so `except ValidationError` still works).

THEREFORE: this shim narrows the gap between "untested" and "tested", it does not
close it. Results obtained under it are real — the legal logic genuinely executes —
but a release must still be validated under real pydantic. The test runner prints
this caveat on every run that uses the shim.

NEVER ON THE PRODUCTION IMPORT PATH
-----------------------------------
This module lives in `backend/tools/` and is installed into `sys.modules` only by
`run_tests.py`, and only after a real `import pydantic` has already failed. It is
never imported by application code. `requirements.txt` continues to declare
pydantic as a genuine dependency.
"""

from __future__ import annotations

import types
import typing
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple, get_args, get_origin

__version__ = "0-lmpc-shim"


class ValidationError(ValueError):
    """Mirrors the name pydantic raises so `except` clauses still match."""


class _Unset:
    """Sentinel distinguishing "no default" from "default is None"."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<unset>"


UNSET = _Unset()


class FieldInfo:
    """What `Field(...)` returns: a default plus the constraints declared on it."""

    __slots__ = ("default", "default_factory", "ge", "le", "gt", "lt", "extra")

    def __init__(
        self,
        default: Any = UNSET,
        *,
        default_factory: Optional[Any] = None,
        ge: Optional[float] = None,
        le: Optional[float] = None,
        gt: Optional[float] = None,
        lt: Optional[float] = None,
        **extra: Any,
    ) -> None:
        self.default = default
        self.default_factory = default_factory
        self.ge = ge
        self.le = le
        self.gt = gt
        self.lt = lt
        self.extra = extra

    def has_default(self) -> bool:
        return self.default is not UNSET or self.default_factory is not None

    def make_default(self) -> Any:
        if self.default_factory is not None:
            return self.default_factory()
        return self.default


def Field(default: Any = UNSET, **kwargs: Any) -> FieldInfo:  # noqa: N802
    """
    `Field()` as `schema.py` uses it.

    Note the pydantic convention this preserves: `Field(ge=0.0, le=1.0)` with NO
    default means the field is REQUIRED. `confidence: float = Field(ge=0.0, le=1.0)`
    in `ExtractedFact` relies on exactly that, so a shim that treated it as
    optional would let a fact carry no confidence at all.
    """
    return FieldInfo(default, **kwargs)


def ConfigDict(**kwargs: Any) -> Dict[str, Any]:  # noqa: N802
    return dict(kwargs)


def _is_optional(annotation: Any) -> bool:
    return get_origin(annotation) is Optional or (
        get_origin(annotation) in (types.UnionType, __import__("typing").Union)
        and type(None) in get_args(annotation)
    )


def _non_none_arg(annotation: Any) -> Any:
    """For `Optional[X]` (i.e. `Union[X, None]`) return `X`; otherwise return
    the annotation unchanged. Must NOT unwrap other single-argument generics
    such as `List[X]` -- doing so previously discarded the `list` origin
    entirely, silently disabling nested-model construction for every
    `List[SomeModel]` field in the codebase."""
    if not _is_optional(annotation):
        return annotation
    args = [a for a in get_args(annotation) if a is not type(None)]  # noqa: E721
    return args[0] if len(args) == 1 else annotation


class _ModelMeta(type):
    """Collects annotations and field defaults down the class hierarchy."""

    @property
    def model_fields(cls) -> Dict[str, Any]:  # noqa: N805 - matches pydantic v2's ClassVar-like property
        """Real pydantic v2 exposes `Model.model_fields` (and, on an
        instance, `instance.model_fields`) as a dict keyed by field name.
        Callers here only ever use it as a set-like collection of field
        names (`set(Model.model_fields)`), so field names are the keys and
        the stored FieldInfo objects are the values -- enough to support
        that usage faithfully."""
        return dict(getattr(cls, "__lmpc_fields__", {}))

    def __new__(mcls, name, bases, ns, **kwargs):
        cls = super().__new__(mcls, name, bases, ns, **kwargs)

        fields: Dict[str, Tuple[Any, FieldInfo]] = {}
        for base in reversed(cls.__mro__[1:]):
            fields.update(getattr(base, "__lmpc_fields__", {}) or {})

        raw_annotations = ns.get("__annotations__", {}) or {}
        # Under `from __future__ import annotations` (used throughout this
        # codebase), every annotation in `ns["__annotations__"]` is a bare
        # STRING (e.g. "List[RuleVersion]"), not a real type object. Without
        # resolving these, get_origin()/get_args() below always see a str
        # and never recognise List[...]/Optional[...]/a nested BaseModel,
        # silently disabling nested-model construction, enum coercion, and
        # list-item conversion for every module written this way. Resolve
        # them properly via typing.get_type_hints, which evaluates the
        # strings against the defining module's namespace -- exactly what
        # real pydantic does internally.
        try:
            resolved = typing.get_type_hints(cls, include_extras=True)
        except Exception:
            resolved = {}

        for fname in raw_annotations:
            if fname.startswith("_") or fname == "model_config":
                continue
            annotation = resolved.get(fname, raw_annotations[fname])
            raw = ns.get(fname, UNSET)
            info = raw if isinstance(raw, FieldInfo) else FieldInfo(raw)
            fields[fname] = (annotation, info)

        cls.__lmpc_fields__ = fields  # type: ignore[attr-defined]
        return cls


class BaseModel(metaclass=_ModelMeta):
    """Keyword-constructed model with the constraint checks `schema.py` declares."""

    model_config: Dict[str, Any] = {}

    @property
    def model_fields(self) -> Dict[str, Any]:
        return dict(type(self).__lmpc_fields__)

    def __init__(self, **data: Any) -> None:
        fields: Dict[str, Tuple[Any, FieldInfo]] = type(self).__lmpc_fields__

        if self.model_config.get("extra") == "forbid":
            unknown = sorted(set(data) - set(fields))
            if unknown:
                raise ValidationError(
                    f"{type(self).__name__} forbids extra fields; got {unknown}. "
                    "This is a real pydantic guarantee, enforced here so a "
                    "misspelled field cannot silently vanish."
                )

        for fname, (annotation, info) in fields.items():
            if fname in data:
                value = self._convert(fname, annotation, data[fname])
            elif info.has_default():
                value = info.make_default()
            elif _is_optional(annotation):
                value = None
            else:
                raise ValidationError(
                    f"{type(self).__name__}.{fname} is required and was not supplied"
                )
            self._check_bounds(fname, info, value)
            object.__setattr__(self, fname, value)

    # -- construction helpers ------------------------------------------------

    def _convert(self, fname: str, annotation: Any, value: Any) -> Any:
        """Build nested models and enums from plain data, as pydantic does."""
        target = _non_none_arg(annotation)

        if value is None:
            return None

        origin = get_origin(target)
        if origin in (list, tuple, set):
            (inner,) = (get_args(target) or (Any,))[:1] or (Any,)
            seq = [self._convert(fname, inner, v) for v in value]
            return seq if origin is list else origin(seq)
        if origin is dict:
            return dict(value)

        if isinstance(target, type):
            if issubclass(target, BaseModel) and isinstance(value, dict):
                return target(**value)
            if issubclass(target, Enum) and not isinstance(value, target):
                return target(value)
            if target is float and isinstance(value, int) and not isinstance(value, bool):
                return float(value)
        return value

    @staticmethod
    def _check_bounds(fname: str, info: FieldInfo, value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        if not isinstance(value, (int, float)):
            return
        for bound, op, symbol in (
            (info.ge, lambda a, b: a >= b, ">="),
            (info.le, lambda a, b: a <= b, "<="),
            (info.gt, lambda a, b: a > b, ">"),
            (info.lt, lambda a, b: a < b, "<"),
        ):
            if bound is not None and not op(value, bound):
                raise ValidationError(
                    f"{fname}={value} violates {symbol} {bound}. Enforced because a "
                    "confidence outside [0,1] leaking into a legal finding is a "
                    "correctness failure, not a formatting one."
                )

    # -- pydantic v2 surface used by the codebase ----------------------------

    def model_dump(self, *, mode: str = "python", **_: Any) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for fname in type(self).__lmpc_fields__:
            out[fname] = self._dump_value(getattr(self, fname), mode)
        return out

    def model_dump_json(self, **kwargs: Any) -> str:
        import json as _json

        def _default(o: Any) -> Any:
            if isinstance(o, (date, datetime)):
                return o.isoformat()
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

        return _json.dumps(self.model_dump(mode="json"), default=_default)

    @classmethod
    def _dump_value(cls, value: Any, mode: str) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode=mode)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (list, tuple)):
            return [cls._dump_value(v, mode) for v in value]
        if isinstance(value, dict):
            return {k: cls._dump_value(v, mode) for k, v in value.items()}
        if mode == "json" and isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    #: pydantic v1 alias, still used in a few places.
    def dict(self, **kwargs: Any) -> Dict[str, Any]:  # noqa: A003
        return self.model_dump(**kwargs)

    @classmethod
    def model_validate(cls, data: Any) -> "BaseModel":
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            raise ValidationError(f"{cls.__name__}.model_validate needs a mapping")
        return cls(**data)

    @classmethod
    def parse_obj(cls, data: Any) -> "BaseModel":
        return cls.model_validate(data)

    @classmethod
    def model_validate_json(cls, json_str: str) -> "BaseModel":
        import json as _json

        return cls.model_validate(_json.loads(json_str))

    def model_copy(self, *, update: Optional[Dict[str, Any]] = None, deep: bool = False) -> "BaseModel":
        import copy as _copy

        data = {f: getattr(self, f) for f in type(self).__lmpc_fields__}
        if deep:
            data = {k: _copy.deepcopy(v) for k, v in data.items()}
        data.update(update or {})
        return type(self)(**data)

    def copy(self, **kwargs: Any) -> "BaseModel":
        return self.model_copy(**kwargs)

    # -- ergonomics ---------------------------------------------------------

    def __eq__(self, other: Any) -> bool:
        if type(other) is not type(self):
            return NotImplemented
        return all(
            getattr(self, f) == getattr(other, f) for f in type(self).__lmpc_fields__
        )

    def __repr__(self) -> str:
        inner = ", ".join(
            f"{f}={getattr(self, f)!r}" for f in type(self).__lmpc_fields__
        )
        return f"{type(self).__name__}({inner})"


def install() -> types.ModuleType:
    """
    Register this shim as `pydantic` in `sys.modules`.

    Callers MUST have already attempted a real `import pydantic` and failed.
    """
    import sys

    module = types.ModuleType("pydantic")
    module.BaseModel = BaseModel            # type: ignore[attr-defined]
    module.Field = Field                    # type: ignore[attr-defined]
    module.ConfigDict = ConfigDict          # type: ignore[attr-defined]
    module.ValidationError = ValidationError  # type: ignore[attr-defined]
    module.__version__ = __version__        # type: ignore[attr-defined]
    sys.modules["pydantic"] = module
    return module
