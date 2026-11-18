"""Algoritmos de recorrido, consulta y análisis de criticidad sobre la red."""

from .traversals import TraversalResult, bfs, dfs, topological_sort
from .queries import (
    find_node,
    find_pipe,
    search_entities,
    trace_downstream,
    trace_upstream,
)
from .analysis import (
    UTILIZATION_LEVELS,
    UtilizationCategory,
    CriticalPipeRecord,
    classify_utilization,
    rank_critical_pipes,
)

__all__ = [
    "TraversalResult",
    "bfs",
    "dfs",
    "topological_sort",
    "find_node",
    "find_pipe",
    "search_entities",
    "trace_downstream",
    "trace_upstream",
    "UTILIZATION_LEVELS",
    "UtilizationCategory",
    "CriticalPipeRecord",
    "classify_utilization",
    "rank_critical_pipes",
]
