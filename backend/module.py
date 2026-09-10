"""Pluggable regulatory-module contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .models import (
    EvidenceRequirement,
    RegulatoryContext,
    RegulatoryFinding,
    RegulatoryModuleMetadata,
)


class RegulatoryModule(ABC):
    """One regulatory domain behind a stable platform interface."""

    @abstractmethod
    def metadata(self) -> RegulatoryModuleMetadata: ...

    @abstractmethod
    def supported_context(self) -> Dict[str, Any]: ...

    @abstractmethod
    def applicability(self, context: RegulatoryContext) -> Dict[str, Any]: ...

    @abstractmethod
    def required_evidence(self, context: RegulatoryContext) -> List[EvidenceRequirement]: ...

    @abstractmethod
    def evaluate(self, context: RegulatoryContext, evidence: Dict[str, Any]) -> List[RegulatoryFinding]: ...

    @abstractmethod
    def explain(self, finding: RegulatoryFinding) -> Dict[str, Any]: ...

    @abstractmethod
    def sources(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def versions(self) -> List[Dict[str, Any]]: ...
