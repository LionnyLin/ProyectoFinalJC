"""Algoritmos obligatorios de recorrido, consulta y clasificación de tuberías."""

from .traversals import TraversalFrame, TraversalResult, bfs, dfs, topological_sort
from .queries import (
    NodeQueryResult,
    PipeQueryResult,
    get_node_details,
    get_pipe_details,
    search_entity,
    trace_downstream,
    trace_upstream,
    trace_upstream_result,
)
from .analysis import (
    OVERLOAD_PERSISTENCE_LEVELS,
    UTILIZATION_LEVELS,
    UTILIZATION_SCALE,
    CriticalPipeRecord,
    UtilizationCategory,
    classify_overload_persistence,
    classify_utilization,
    rank_critical_pipes,
)

__all__ = [
    "TraversalFrame",
    "TraversalResult",
    "bfs",
    "dfs",
    "topological_sort",
    "NodeQueryResult",
    "PipeQueryResult",
    "search_entity",
    "get_node_details",
    "get_pipe_details",
    "trace_downstream",
    "trace_upstream",
    "trace_upstream_result",
    "OVERLOAD_PERSISTENCE_LEVELS",
    "classify_overload_persistence",
    "UTILIZATION_SCALE",
    "UTILIZATION_LEVELS",
    "UtilizationCategory",
    "CriticalPipeRecord",
    "classify_utilization",
    "rank_critical_pipes",
]
