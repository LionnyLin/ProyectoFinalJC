"""Cálculo de cotas hidráulicas z_i, rasante de referencia y malla 10x10 para vista 3D."""

from dataclasses import dataclass, field
import math
import statistics
from typing import Dict, List, Optional, Set, Tuple

from src.data_structures import DirectedGraph


@dataclass(frozen=True)
class TerrainCell:
    """Celda cuadrangular de la malla de rasante de referencia para Z-sorting."""

    row: int
    col: int
    corners: Tuple[
        Tuple[float, float, float],
        Tuple[float, float, float],
        Tuple[float, float, float],
        Tuple[float, float, float],
    ]
    center_x: float
    center_y: float
    center_z: float


@dataclass
class ElevationProfile:
    """Perfil altimétrico inferido de la red y malla subdividida de rasante."""

    node_z: Dict[str, float] = field(default_factory=dict)
    ground_z: Dict[str, float] = field(default_factory=dict)
    node_xy: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    grid_cells: List[TerrainCell] = field(default_factory=list)
    min_z: float = 0.0
    max_z: float = 1.5
    max_node_z: float = 0.0
    grid_n: int = 10
    slope_unit_normalized: bool = False
    resolved_nodes: Set[str] = field(default_factory=set)


def _effective_slopes(
    graph: DirectedGraph, slope_is_percent: Optional[bool]
) -> Tuple[Dict[str, float], bool]:
    """Normaliza pendientes a m/m aplicando la guardia de porcentaje vs fracción."""
    pipes = graph.pipes()
    pos_slopes = [
        float(p.slope)
        for p in pipes
        if math.isfinite(p.slope) and float(p.slope) > 0.0
    ]

    normalized = False
    use_all_percent = False
    if slope_is_percent is True:
        use_all_percent = True
        normalized = bool(pipes)
    elif slope_is_percent is False:
        use_all_percent = False
        normalized = False
    elif pos_slopes:
        med = statistics.median(pos_slopes)
        if med > 0.25:
            use_all_percent = True
            normalized = True

    eff: Dict[str, float] = {}
    for p in pipes:
        raw = float(p.slope) if math.isfinite(p.slope) else 0.0
        raw = max(0.0, raw)
        if use_all_percent:
            eff[p.pipe_id] = raw / 100.0
        elif slope_is_percent is None and raw > 0.25:
            eff[p.pipe_id] = raw / 100.0
            normalized = True
        else:
            eff[p.pipe_id] = raw
    return eff, normalized


def _idw_interpolate(
    qx: float,
    qy: float,
    samples: List[Tuple[str, float, float, float]],
    k: int,
    eps_d2: float,
) -> float:
    """Interpolación IDW determinista sobre los k vecinos más cercanos."""
    if not samples:
        return 0.0
    scored: List[Tuple[float, str, float]] = []
    for nid, sx, sy, sz in samples:
        dx = qx - sx
        dy = qy - sy
        d2 = dx * dx + dy * dy
        scored.append((d2, nid, sz))
    scored.sort(key=lambda item: (item[0], item[1]))
    top_k = scored[: max(1, min(k, len(scored)))]
    num = 0.0
    den = 0.0
    for d2, _nid, sz in top_k:
        w = 1.0 / max(d2, eps_d2)
        num += w * sz
        den += w
    return num / den if den > 0.0 else 0.0


def compute_network_elevations(
    graph: DirectedGraph,
    grid_n: int = 10,
    slope_is_percent: Optional[bool] = None,
) -> ElevationProfile:
    """Calcula cotas hidráulicas z_i, rasante de referencia y malla grid_n x grid_n."""
    nodes = graph.nodes()
    pipes = graph.pipes()
    grid_n = max(1, int(grid_n))

    if not nodes:
        return ElevationProfile(grid_n=grid_n)

    eff_slopes, slope_normalized = _effective_slopes(graph, slope_is_percent)

    # 1. Bellman-Ford inverso multi-sumidero (seguro ante ciclos en grafos externos)
    node_z: Dict[str, float] = {}
    resolved: Set[str] = set()
    for sid in graph.sink_ids():
        if graph.has_node(sid):
            node_z[sid] = 0.0
            resolved.add(sid)

    max_passes = max(1, graph.num_nodes - 1)
    for _ in range(max_passes):
        changed = False
        for edge in pipes:
            if edge.to_node not in resolved:
                continue
            s_eff = eff_slopes.get(edge.pipe_id, 0.0)
            length = max(0.0, float(edge.length_m)) if math.isfinite(edge.length_m) else 0.0
            cand = node_z[edge.to_node] + s_eff * length
            if edge.from_node not in resolved or cand > node_z[edge.from_node] + 1e-12:
                node_z[edge.from_node] = cand
                resolved.add(edge.from_node)
                changed = True
        if not changed:
            break

    # 2. Nodos desconectados por IDW espacial (k = 3)
    resolved_samples_raw: List[Tuple[str, float, float, float]] = [
        (n.node_id, float(n.x), float(n.y), node_z[n.node_id])
        for n in nodes
        if n.node_id in resolved
    ]
    for n in nodes:
        if n.node_id not in resolved:
            if resolved_samples_raw:
                node_z[n.node_id] = _idw_interpolate(
                    float(n.x), float(n.y), resolved_samples_raw, k=3, eps_d2=1e-6
                )
            else:
                node_z[n.node_id] = 0.0

    # 3. Cota de rasante de referencia z_suelo_i
    ground_z: Dict[str, float] = {}
    for n in nodes:
        d_max = 0.0
        for e in graph.incoming_pipes(n.node_id):
            if math.isfinite(e.diameter_m) and e.diameter_m > d_max:
                d_max = float(e.diameter_m)
        for e in graph.outgoing_pipes(n.node_id):
            if math.isfinite(e.diameter_m) and e.diameter_m > d_max:
                d_max = float(e.diameter_m)
        if d_max <= 0.0:
            d_max = 0.30
        ground_z[n.node_id] = node_z[n.node_id] + max(1.5, 1.5 * d_max)

    # 4. Coordenadas centradas preservando relación de aspecto en [-0.9, 0.9]
    xs = [float(n.x) for n in nodes]
    ys = [float(n.y) for n in nodes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    cx = 0.5 * (min_x + max_x)
    cy = 0.5 * (min_y + max_y)
    half_span = 0.5 * max(max_x - min_x, max_y - min_y, 1e-3)

    node_xy: Dict[str, Tuple[float, float]] = {}
    wx_list: List[float] = []
    wy_list: List[float] = []
    ground_samples_world: List[Tuple[str, float, float, float]] = []
    for n in nodes:
        wx = ((float(n.x) - cx) / half_span) * 0.90
        wy = ((float(n.y) - cy) / half_span) * 0.90
        node_xy[n.node_id] = (wx, wy)
        wx_list.append(wx)
        wy_list.append(wy)
        ground_samples_world.append((n.node_id, wx, wy, ground_z[n.node_id]))

    # 5. Malla subdividida grid_n x grid_n sobre bounding box ampliado
    margin = 0.12
    gx0 = min(wx_list) - margin
    gx1 = max(wx_list) + margin
    gy0 = min(wy_list) - margin
    gy1 = max(wy_list) + margin
    dx_cell = (gx1 - gx0) / float(grid_n)
    dy_cell = (gy1 - gy0) / float(grid_n)

    verts: List[List[Tuple[float, float, float]]] = []
    for r in range(grid_n + 1):
        vy = gy0 + r * dy_cell
        row_v: List[Tuple[float, float, float]] = []
        for c in range(grid_n + 1):
            vx = gx0 + c * dx_cell
            vz = _idw_interpolate(vx, vy, ground_samples_world, k=4, eps_d2=1e-4)
            row_v.append((vx, vy, vz))
        verts.append(row_v)

    grid_cells: List[TerrainCell] = []
    for r in range(grid_n):
        for c in range(grid_n):
            c00 = verts[r][c]
            c10 = verts[r][c + 1]
            c11 = verts[r + 1][c + 1]
            c01 = verts[r + 1][c]
            grid_cells.append(
                TerrainCell(
                    row=r,
                    col=c,
                    corners=(c00, c10, c11, c01),
                    center_x=0.25 * (c00[0] + c10[0] + c11[0] + c01[0]),
                    center_y=0.25 * (c00[1] + c10[1] + c11[1] + c01[1]),
                    center_z=0.25 * (c00[2] + c10[2] + c11[2] + c01[2]),
                )
            )

    min_z = min(node_z.values(), default=0.0)
    max_node_z = max(node_z.values(), default=0.0)
    max_z = max(ground_z.values(), default=1.5)

    return ElevationProfile(
        node_z=node_z,
        ground_z=ground_z,
        node_xy=node_xy,
        grid_cells=grid_cells,
        min_z=min_z,
        max_z=max_z,
        max_node_z=max_node_z,
        grid_n=grid_n,
        slope_unit_normalized=slope_normalized,
        resolved_nodes=resolved,
    )
