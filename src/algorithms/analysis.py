"""Clasificación de utilización e identificación de tuberías críticas."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from src.data_structures import DirectedGraph, PriorityQueue
from .traversals import topological_sort


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
    demand_ratio_pct: float = 0.0


def rank_critical_pipes(
    graph: DirectedGraph,
    pipe_flows_m3s: Dict[str, float],
    pipe_utilizations_pct: Dict[str, float],
    min_utilization_pct: float = 0.0,
    pipe_qmax_overrides: Optional[Dict[str, float]] = None,
    pipe_demand_ratios_pct: Optional[Dict[str, float]] = None,
    pipe_excess_flows_m3s: Optional[Dict[str, float]] = None,
) -> List[CriticalPipeRecord]:
    """Ordena tuberías de mayor a menor utilización (y demanda como desempate) usando PriorityQueue propia."""
    pq: PriorityQueue[str] = PriorityQueue()
    for pipe in graph.pipes():
        util = pipe_utilizations_pct.get(pipe.pipe_id, 0.0)
        dem = pipe_demand_ratios_pct.get(pipe.pipe_id, util) if pipe_demand_ratios_pct else util
        if util >= min_utilization_pct:
            # Min-heap: prioridad negativa para extraer mayor utilización/demanda primero.
            pq.push(-(util * 1000.0 + dem), pipe.pipe_id)

    ranked: List[CriticalPipeRecord] = []
    rank = 1
    while not pq.is_empty():
        _, pid = pq.pop()
        pipe = graph.get_pipe(pid)
        if pipe is None:
            continue
        flow = pipe_flows_m3s.get(pid, 0.0)
        util = pipe_utilizations_pct.get(pid, 0.0)
        dem = pipe_demand_ratios_pct.get(pid, util) if pipe_demand_ratios_pct else util
        q_max = (
            pipe_qmax_overrides[pid]
            if pipe_qmax_overrides and pid in pipe_qmax_overrides
            else pipe.q_max_m3s
        )
        cat = classify_utilization(util)
        excess = (
            pipe_excess_flows_m3s[pid]
            if pipe_excess_flows_m3s and pid in pipe_excess_flows_m3s
            else max(0.0, flow - q_max)
        )
        ranked.append(
            CriticalPipeRecord(
                rank=rank,
                pipe_id=pid,
                from_node=pipe.from_node,
                to_node=pipe.to_node,
                flow_m3s=flow,
                q_max_m3s=q_max,
                utilization_pct=util,
                category=cat,
                excess_flow_m3s=excess,
                note=pipe.note,
                demand_ratio_pct=dem,
            )
        )
        rank += 1

    return ranked


OVERLOAD_PERSISTENCE_LEVELS: List[Tuple[str, str, str]] = [
    ("0 min", "#22c55e", "Sin sobrecarga"),
    ("≤25% t", "#eab308", "Sobrecarga puntual"),
    (">25–50% t", "#f97316", "Estrés moderado"),
    (">50–75% t", "#ef4444", "Fatiga severa"),
    (">75% t", "#991b1b", "Colapso crónico"),
]


def classify_overload_persistence(
    overloaded_minutes: float, total_duration_min: float
) -> Tuple[int, str, str]:
    """Clasifica minutos acumulados en sobrecarga según la escala de 5 colores de Sección 7."""
    if overloaded_minutes <= 1e-6:
        return (0, "#22c55e", "Sin sobrecarga")
    denom = max(1e-6, float(total_duration_min))
    pct_time = (overloaded_minutes / denom) * 100.0
    if pct_time <= 25.0:
        return (1, "#eab308", "Sobrecarga puntual")
    if pct_time <= 50.0:
        return (2, "#f97316", "Estrés moderado")
    if pct_time <= 75.0:
        return (3, "#ef4444", "Fatiga severa")
    return (4, "#991b1b", "Colapso crónico")


@dataclass(frozen=True)
class SourceAttributionResult:
    """Composición porcentual por fuente aportante (0.0..1.0) para cada nodo y tubería."""

    node_shares: Dict[str, List[Tuple[str, float]]]
    pipe_shares: Dict[str, List[Tuple[str, float]]]


def compute_source_attribution(
    graph: DirectedGraph,
    snapshot: Optional[Any] = None,
    split_rule: str = "proportional",
    pipe_qmax_overrides: Optional[Dict[str, float]] = None,
) -> SourceAttributionResult:
    """Propaga la firma de cada fuente por orden topológico respetando bifurcación y convergencia."""
    topo_order, _is_dag = topological_sort(graph)
    node_mix_raw: Dict[str, Dict[str, float]] = {nid: {} for nid in graph.node_ids()}
    node_struct_q: Dict[str, float] = {nid: 0.0 for nid in graph.node_ids()}

    for sid in graph.source_ids():
        node_mix_raw[sid][sid] = 1.0
        if snapshot is not None and sid in snapshot.node_states:
            in_q = float(snapshot.node_states[sid].inflow_m3s)
            node_struct_q[sid] = in_q if in_q > 1e-12 else 1.0
        else:
            node_struct_q[sid] = 1.0

    node_shares: Dict[str, List[Tuple[str, float]]] = {}
    pipe_shares: Dict[str, List[Tuple[str, float]]] = {}

    def _sorted_norm(mix: Dict[str, float]) -> Tuple[Dict[str, float], List[Tuple[str, float]]]:
        total = sum(v for v in mix.values() if v > 0.0)
        if total <= 1e-15:
            return ({}, [])
        norm = {k: v / total for k, v in mix.items() if v > 0.0}
        ordered = sorted(norm.items(), key=lambda kv: (-kv[1], kv[0]))
        return (norm, ordered)

    for u in topo_order:
        comp_u, ordered_u = _sorted_norm(node_mix_raw.get(u, {}))
        node_shares[u] = ordered_u
        if not comp_u:
            continue

        out_pipes = graph.outgoing_pipes(u)
        if not out_pipes:
            continue

        # Calcular caudal/peso efectivo por cada arista saliente
        pipe_eff_qmax: Dict[str, float] = {}
        active_pipes = []
        for e in out_pipes:
            if pipe_qmax_overrides and e.pipe_id in pipe_qmax_overrides:
                eff_qmax = pipe_qmax_overrides[e.pipe_id]
            elif snapshot is not None and e.pipe_id in snapshot.pipe_states:
                ps = snapshot.pipe_states[e.pipe_id]
                eff_qmax = ps.effective_q_max_m3s if ps.effective_q_max_m3s is not None else e.q_max_m3s
            else:
                eff_qmax = e.q_max_m3s
            pipe_eff_qmax[e.pipe_id] = max(0.0, float(eff_qmax))
            if pipe_eff_qmax[e.pipe_id] > 1e-12:
                active_pipes.append(e)

        live_flows: Dict[str, float] = {}
        if snapshot is not None:
            for e in out_pipes:
                ps = snapshot.pipe_states.get(e.pipe_id)
                if ps is not None:
                    q_val = ps.conveyed_flow_m3s if ps.conveyed_flow_m3s > 1e-12 else ps.flow_m3s
                    if pipe_eff_qmax[e.pipe_id] <= 1e-12:
                        q_val = 0.0
                    live_flows[e.pipe_id] = max(0.0, float(q_val))

        total_live = sum(live_flows.values())
        struct_q_u = node_struct_q.get(u, 0.0)
        if struct_q_u <= 1e-12:
            struct_q_u = 1.0

        sum_qmax_active = sum(pipe_eff_qmax[e.pipe_id] for e in active_pipes)
        for e in out_pipes:
            pipe_shares[e.pipe_id] = list(ordered_u)
            if total_live > 1e-12:
                w_e = live_flows.get(e.pipe_id, 0.0)
            elif e in active_pipes:
                if split_rule == "equal":
                    share = 1.0 / len(active_pipes)
                else:
                    share = (
                        pipe_eff_qmax[e.pipe_id] / sum_qmax_active
                        if sum_qmax_active > 1e-12
                        else 1.0 / len(active_pipes)
                    )
                w_e = struct_q_u * share
            else:
                w_e = 0.0

            if w_e > 1e-15:
                node_struct_q[e.to_node] = node_struct_q.get(e.to_node, 0.0) + w_e
                dst_mix = node_mix_raw[e.to_node]
                for src_id, frac in comp_u.items():
                    dst_mix[src_id] = dst_mix.get(src_id, 0.0) + frac * w_e

    for pipe in graph.pipes():
        pipe_shares.setdefault(pipe.pipe_id, [])

    return SourceAttributionResult(node_shares=node_shares, pipe_shares=pipe_shares)
