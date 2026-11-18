"""Clasificación de utilización e identificación de tuberías críticas."""

from dataclasses import dataclass
from typing import Dict, List, Tuple
from src.data_structures import DirectedGraph, PriorityQueue


UTILIZATION_LEVELS: List[Tuple[float, float, str, str]] = [
    (0.0, 25.0, "#22c55e", "Baja utilización"),
    (25.0, 50.0, "#eab308", "Utilización moderada"),
    (50.0, 75.0, "#f97316", "Utilización alta"),
    (75.0, 100.0, "#ef4444", "Cercana a la capacidad máxima"),
    (100.0, float("inf"), "#7f1d1d", "Capacidad excedida"),
]


@dataclass(frozen=True)
class UtilizationCategory:
    """Categoría de color y estado para un porcentaje de utilización."""

    label: str
    color_hex: str
    tier_index: int  # 0..4
    is_overloaded: bool
    is_critical: bool  # >= 75%


def classify_utilization(utilization_pct: float) -> UtilizationCategory:
    """Clasifica el porcentaje de utilización O_i(t) según la escala de colores de la guía."""
    if utilization_pct <= 25.0:
        return UtilizationCategory("Baja utilización", "#22c55e", 0, False, False)
    if utilization_pct <= 50.0:
        return UtilizationCategory("Utilización moderada", "#eab308", 1, False, False)
    if utilization_pct <= 75.0:
        return UtilizationCategory("Utilización alta", "#f97316", 2, False, False)
    if utilization_pct <= 100.0:
        return UtilizationCategory("Cercana a la capacidad máxima", "#ef4444", 3, False, True)
    return UtilizationCategory("Capacidad excedida", "#7f1d1d", 4, True, True)


@dataclass
class CriticalPipeRecord:
    """Registro resumido de criticidad de una tubería."""

    rank: int
    pipe_id: str
    from_node: str
    to_node: str
    flow_m3s: float
    q_max_m3s: float
    utilization_pct: float
    category: UtilizationCategory
    excess_flow_m3s: float
    note: str = ""


def rank_critical_pipes(
    graph: DirectedGraph,
    pipe_flows_m3s: Dict[str, float],
    pipe_utilizations_pct: Dict[str, float],
    min_utilization_pct: float = 0.0,
) -> List[CriticalPipeRecord]:
    """Ordena tuberías de mayor a menor utilización usando una PriorityQueue propia."""
    pq: PriorityQueue[str] = PriorityQueue()
    for pipe in graph.pipes():
        util = pipe_utilizations_pct.get(pipe.pipe_id, 0.0)
        if util >= min_utilization_pct:
            # Min-heap: prioridad negativa para extraer mayor utilización primero.
            pq.push(-util, pipe.pipe_id)

    ranked: List[CriticalPipeRecord] = []
    rank = 1
    while not pq.is_empty():
        _, pid = pq.pop()
        pipe = graph.get_pipe(pid)
        if pipe is None:
            continue
        flow = pipe_flows_m3s.get(pid, 0.0)
        util = pipe_utilizations_pct.get(pid, 0.0)
        cat = classify_utilization(util)
        excess = max(0.0, flow - pipe.q_max_m3s)
        ranked.append(
            CriticalPipeRecord(
                rank=rank,
                pipe_id=pid,
                from_node=pipe.from_node,
                to_node=pipe.to_node,
                flow_m3s=flow,
                q_max_m3s=pipe.q_max_m3s,
                utilization_pct=util,
                category=cat,
                excess_flow_m3s=excess,
                note=pipe.note,
            )
        )
        rank += 1

    return ranked
