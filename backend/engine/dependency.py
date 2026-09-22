"""
Rule dependency resolution (section 17).

Dependencies are resolved with a plain iterative topological sort (DFS,
explicit stack -- no recursion limits to worry about with large rulesets).
A cycle is detected and reported with the actual chain rather than a bare
"circular dependency" message.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .errors import CircularDependencyError
from .rule_model import RuleSet


def _graph(ruleset: RuleSet) -> Dict[str, List[str]]:
    return {r.rule_id: list(r.depends_on) for r in ruleset.rules if r.rule_id}


def find_cycle(ruleset: RuleSet) -> Optional[List[str]]:
    """Return the cycle (as a list of rule_ids) if one exists, else None."""
    graph = _graph(ruleset)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    stack_path: List[str] = []

    def visit(node: str) -> Optional[List[str]]:
        color[node] = GRAY
        stack_path.append(node)
        for dep in graph.get(node, []):
            if dep not in color:
                continue  # unknown dep is a separate validation problem
            if color[dep] == GRAY:
                idx = stack_path.index(dep)
                return stack_path[idx:] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        stack_path.pop()
        color[node] = BLACK
        return None

    for node in list(graph.keys()):
        if color[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


def topological_order(ruleset: RuleSet) -> List[str]:
    """
    Return rule_ids ordered so that every rule appears after all of its
    dependencies. Raises CircularDependencyError if the graph has a cycle.
    Rules with no dependency relationship keep their original relative order
    (stable sort) so evaluation order is deterministic run-to-run.
    """
    cycle = find_cycle(ruleset)
    if cycle:
        raise CircularDependencyError(cycle)

    graph = _graph(ruleset)
    order: List[str] = []
    visited: Dict[str, bool] = {node: False for node in graph}

    def visit(node: str) -> None:
        if visited.get(node):
            return
        visited[node] = True
        for dep in graph.get(node, []):
            if dep in graph:
                visit(dep)
        order.append(node)

    for rule in ruleset.rules:  # preserves original order for independent rules
        visit(rule.rule_id)

    return order
