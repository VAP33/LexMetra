from .lmpc import LMPCModule
from .module import RegulatoryModule
from .models import *  # noqa: F401,F403
from .placeholders import default_future_modules
from .registry import RegulatoryModuleRegistry


def default_registry() -> RegulatoryModuleRegistry:
    registry = RegulatoryModuleRegistry([LMPCModule()])
    for module in default_future_modules():
        registry.register(module)
    return registry
from .amendments import AmendmentImpact, calculate_impact, transition_amendment
