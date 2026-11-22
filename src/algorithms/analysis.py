"""Clasificación de utilización (Sección 7) y ranking de tuberías críticas con PriorityQueue."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.data_structures import DirectedGraph, PriorityQueue


UTILIZATION_SCALE: List[Tuple[float, float, str, str]] = [
    (0.0, 25.0, "#22c55e", "Baja utilización"),
    (25.0, 50.0, "#eab308", "Utilización moderada"),
    (50.0, 75.0, "#f97316", "Utilización alta"),
    (75.0, 100.0, "#ef4444", "Cercana a capacidad máxima"),
    (100.0, float("inf"), "#991b1b", "Capacidad excedida"),
]
UTILIZATION_LEVELS = UTILIZATION_SCALE


@dataclass(frozen=True, slots=True)
class UtilizationCategory:
    """Categoría oficial de color y estado para un porcentaje de utilización."""

    label: str
    color_hex: str
    tier_index: int  # 0..4
    is_overloaded: bool
    is_critical: bool  # > 75 %


_CATEGORIES: Tuple[UtilizationCategory, ...] = tuple(
    UtilizationCategory(label, color, idx, idx >= 4, idx >= 3)
    for idx, (_, _, color, label) in enumerate(UTILIZATION_SCALE)
)


def classify_utilization(utilization_pct: float) -> UtilizationCategory:
    """Clasifica O_i(t) según la escala de 5 colores de la Sección 7 del proyecto."""
    if utilization_pct <= 25.0:
        return _CATEGORIES[0]
    if utilization_pct <= 50.0:
        return _CATEGORIES[1]
    if utilization_pct <= 75.0:
        return _CATEGORIES[2]
    if utilization_pct <= 100.0:
        return _CATEGORIES[3]
    return _CATEGORIES[4]


@dataclass(slots=True)
class CriticalPipeRecord:
    """Registro ordenado de criticidad de una tubería."""

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
    max_utilization_pct: Optional[float] = None,
    exclusive_min: bool = False,
) -> List[CriticalPipeRecord]:
    """Ordena tuberías de mayor a menor utilización usando PriorityQueue propia."""
    pq: PriorityQueue[str] = PriorityQueue()
    for pipe in graph.pipes():
        util = pipe_utilizations_pct.get(pipe.pipe_id, 0.0)
        passes_min = (util > min_utilization_pct) if exclusive_min else (util >= min_utilization_pct)
        passes_max = (util <= max_utilization_pct) if max_utilization_pct is not None else True
        if passes_min and passes_max:
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
        excess = max(0.0, (util / 100.0 - 1.0) * pipe.q_max_m3s) if pipe.q_max_m3s > 0.0 else 0.0
        ranked.append(CriticalPipeRecord(
            rank=rank, pipe_id=pid, from_node=pipe.from_node, to_node=pipe.to_node,
            flow_m3s=flow, q_max_m3s=pipe.q_max_m3s, utilization_pct=util,
            category=classify_utilization(util), excess_flow_m3s=excess, note=pipe.note,
        ))
        rank += 1
    return ranked


OVERLOAD_PERSISTENCE_LEVELS: List[Tuple[str, str, str]] = [
    ("0 min", "#22c55e", "Sin sobrecarga"),
    ("≤25% t", "#eab308", "Sobrecarga puntual"),
    (">25–50% t", "#f97316", "Estrés moderado"),
    (">50–75% t", "#ef4444", "Fatiga severa"),
    (">75% t", "#991b1b", "Colapso crónico"),
]


def classify_overload_persistence(overloaded_minutes: float, total_duration_min: float) -> Tuple[int, str, str]:
    """Clasifica minutos acumulados en sobrecarga (> 100 %) con la escala de 5 colores de la Sección 7.

    Retorna `(tier_index, color_hex, etiqueta)` según el porcentaje de la duración total en sobrecarga.
    """
    if overloaded_minutes <= 1e-6:
        return (0, "#22c55e", "Sin sobrecarga")
    pct_time = (overloaded_minutes / max(1e-6, float(total_duration_min))) * 100.0
    if pct_time <= 25.0:
        return (1, "#eab308", "Sobrecarga puntual")
    if pct_time <= 50.0:
        return (2, "#f97316", "Estrés moderado")
    if pct_time <= 75.0:
        return (3, "#ef4444", "Fatiga severa")
    return (4, "#991b1b", "Colapso crónico")
