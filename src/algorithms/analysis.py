"""Clasificación de utilización (Sección 7) y ranking de tuberías críticas con PriorityQueue."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.data_structures import DirectedGraph, PriorityQueue
from .traversals import topological_sort


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
    demand_ratio_pct: float = 0.0


def rank_critical_pipes(
    graph: DirectedGraph,
    pipe_flows_m3s: Dict[str, float],
    pipe_utilizations_pct: Dict[str, float],
    min_utilization_pct: float = 0.0,
    max_utilization_pct: Optional[float] = None,
    exclusive_min: bool = False,
    pipe_qmax_overrides: Optional[Dict[str, float]] = None,
    pipe_demand_ratios_pct: Optional[Dict[str, float]] = None,
    pipe_excess_flows_m3s: Optional[Dict[str, float]] = None,
) -> List[CriticalPipeRecord]:
    """Ordena tuberías por utilización (y razón de demanda como desempate) usando PriorityQueue propia."""
    pq: PriorityQueue[str] = PriorityQueue()
    for pipe in graph.pipes():
        util = pipe_utilizations_pct.get(pipe.pipe_id, 0.0)
        dem = pipe_demand_ratios_pct.get(pipe.pipe_id, util) if pipe_demand_ratios_pct else util
        passes_min = (util > min_utilization_pct) if exclusive_min else (util >= min_utilization_pct)
        passes_max = (util <= max_utilization_pct) if max_utilization_pct is not None else True
        if passes_min and passes_max:
            pq.push((-util, -dem), pipe.pipe_id)

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
        q_max = pipe_qmax_overrides[pid] if pipe_qmax_overrides and pid in pipe_qmax_overrides else pipe.q_max_m3s
        if pipe_excess_flows_m3s and pid in pipe_excess_flows_m3s:
            excess = pipe_excess_flows_m3s[pid]
        else:
            excess = max(0.0, (util / 100.0 - 1.0) * q_max if q_max > 0.0 else 0.0, flow - q_max)
        ranked.append(CriticalPipeRecord(
            rank=rank, pipe_id=pid, from_node=pipe.from_node, to_node=pipe.to_node,
            flow_m3s=flow, q_max_m3s=q_max, utilization_pct=util,
            category=classify_utilization(util), excess_flow_m3s=excess, note=pipe.note, demand_ratio_pct=dem,
        ))
        rank += 1
    return ranked


@dataclass(frozen=True, slots=True)
class SourceAttributionResult:
    """Composición porcentual por fuente aportante (0.0..1.0) para cada nodo y tubería."""

    node_shares: Dict[str, List[Tuple[str, float]]]
    pipe_shares: Dict[str, List[Tuple[str, float]]]


def compute_source_attribution(
    graph: DirectedGraph,
    snapshot: Optional[Any] = None,
    split_rule: str = "proportional",
    pipe_qmax_overrides: Optional[Dict[str, float]] = None,
    source_distribution: str = "capacity",
) -> SourceAttributionResult:
    """Propaga la firma de cada fuente por orden topológico respetando bifurcación y convergencia."""
    topo_order, _ = topological_sort(graph)
    mix_raw: Dict[str, Dict[str, float]] = {nid: {} for nid in graph.node_ids()}
    struct_q: Dict[str, float] = {nid: 0.0 for nid in graph.node_ids()}

    sources = graph.source_ids()
    default_q = {sid: 1.0 for sid in sources}
    if source_distribution != "equal":
        caps = {sid: sum(e.q_max_m3s for e in graph.outgoing_pipes(sid)) for sid in sources}
        total_cap = sum(caps.values())
        if total_cap > 1e-12:
            default_q = {sid: caps[sid] / total_cap for sid in sources}
    for sid in sources:
        mix_raw[sid][sid] = 1.0
        in_q = float(snapshot.node_states[sid].inflow_m3s) if snapshot is not None and sid in snapshot.node_states else 0.0
        struct_q[sid] = in_q if in_q > 1e-12 else default_q[sid]

    node_shares: Dict[str, List[Tuple[str, float]]] = {}
    pipe_shares: Dict[str, List[Tuple[str, float]]] = {}
    for u in topo_order:
        total = sum(v for v in mix_raw[u].values() if v > 0.0)
        comp_u = {k: v / total for k, v in mix_raw[u].items() if v > 0.0} if total > 1e-15 else {}
        ordered_u = sorted(comp_u.items(), key=lambda kv: (-kv[1], kv[0]))
        node_shares[u] = ordered_u
        out_pipes = graph.outgoing_pipes(u).to_list()
        if not comp_u or not out_pipes:
            continue

        eff_q: Dict[str, float] = {}
        for e in out_pipes:
            if pipe_qmax_overrides and e.pipe_id in pipe_qmax_overrides:
                q = pipe_qmax_overrides[e.pipe_id]
            elif snapshot is not None and e.pipe_id in snapshot.pipe_states:
                ps = snapshot.pipe_states[e.pipe_id]
                q = ps.effective_q_max_m3s if ps.effective_q_max_m3s is not None else e.q_max_m3s
            else:
                q = e.q_max_m3s
            eff_q[e.pipe_id] = max(0.0, float(q))
        active = [e for e in out_pipes if eff_q[e.pipe_id] > 1e-12]

        live: Dict[str, float] = {}
        if snapshot is not None:
            for e in out_pipes:
                ps = snapshot.pipe_states.get(e.pipe_id)
                if ps is not None:
                    live[e.pipe_id] = max(0.0, float(ps.conveyed_flow_m3s)) if eff_q[e.pipe_id] > 1e-12 else 0.0
        total_live = sum(live.values())
        base_q = struct_q[u] if struct_q[u] > 1e-12 else 1.0
        sum_active = sum(eff_q[e.pipe_id] for e in active)

        for e in out_pipes:
            if eff_q[e.pipe_id] <= 1e-12:
                pipe_shares[e.pipe_id] = []
                continue
            pipe_shares[e.pipe_id] = list(ordered_u)
            if total_live > 1e-12:
                w_e = live.get(e.pipe_id, 0.0)
            elif split_rule == "equal":
                w_e = base_q / len(active)
            else:
                w_e = base_q * (eff_q[e.pipe_id] / sum_active if sum_active > 1e-12 else 1.0 / len(active))
            if w_e > 1e-15:
                struct_q[e.to_node] += w_e
                dst = mix_raw[e.to_node]
                for src_id, frac in comp_u.items():
                    dst[src_id] = dst.get(src_id, 0.0) + frac * w_e

    for pipe in graph.pipes():
        pipe_shares.setdefault(pipe.pipe_id, [])
    return SourceAttributionResult(node_shares=node_shares, pipe_shares=pipe_shares)


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
