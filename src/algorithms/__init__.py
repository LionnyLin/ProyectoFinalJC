"""Algoritmos de recorrido, consulta y análisis de criticidad sobre la red."""

from .traversals import (
    TraversalAnimFrame,
    TraversalResult,
    bfs,
    bfs_anim_frames,
    dfs,
    dfs_anim_frames,
    topological_sort,
)
from .queries import (
    build_route_to_sink,
    find_isolated_from_sinks,
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
    "TraversalAnimFrame",
    "bfs",
    "bfs_anim_frames",
    "dfs",
    "dfs_anim_frames",
    "topological_sort",
    "find_node",
    "find_pipe",
    "search_entities",
    "trace_downstream",
    "trace_upstream",
    "find_isolated_from_sinks",
    "build_route_to_sink",
    "UTILIZATION_LEVELS",
    "UtilizationCategory",
    "CriticalPipeRecord",
    "classify_utilization",
    "rank_critical_pipes",
]
