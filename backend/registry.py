"""Registry for independent regulatory modules."""
from __future__ import annotations

from typing import Dict, Iterable

from .module import RegulatoryModule


class RegulatoryModuleRegistry:
    def __init__(self, modules: Iterable[RegulatoryModule] = ()) -> None:
        self._modules: Dict[str, RegulatoryModule] = {}
        for module in modules:
            self.register(module)

    def register(self, module: RegulatoryModule) -> None:
        module_id = module.metadata().id
        if module_id in self._modules:
            raise ValueError(f"Regulatory module already registered: {module_id}")
        self._modules[module_id] = module

    def get(self, module_id: str) -> RegulatoryModule:
        try:
            return self._modules[module_id]
        except KeyError as exc:
            raise KeyError(f"Unknown regulatory module: {module_id}") from exc

    def list(self) -> list[RegulatoryModule]:
        return list(self._modules.values())

    def metadata(self) -> list[dict]:
        return [m.metadata().model_dump(mode="json") for m in self._modules.values()]
