"""Algoritmo de Flujo Máximo (Ford-Fulkerson / Edmonds-Karp) sobre estructuras propias."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from src.data_structures import DirectedGraph, HashTable, LinkedList, PipeEdge, Queue, Stack

SUPER_SOURCE = "__SUPER_SOURCE__"
SUPER_SINK = "__SUPER_SINK__"


@dataclass
class _ResidualEdge:
    """Arista en la red residual con enlace directo a su arista reversa."""

    to_node: str
    cap: float
    orig_cap: float
    pipe_id: Optional[str]
    is_forward: bool
    rev: Optional["_ResidualEdge"] = None


@dataclass(frozen=True)
class AugmentingPathStep:
    """Paso de aumento encontrado en una iteración de Ford-Fulkerson (BFS)."""

    iteration: int
    nodes: List[str]
    pipe_ids: List[str]
    bottleneck_m3s: float
    cumulative_flow_m3s: float


@dataclass(frozen=True)
class MaxFlowResult:
    """Resultado completo del algoritmo Ford-Fulkerson y teorema Flujo Máximo / Corte Mínimo."""

    max_flow_m3s: float
    edge_flows: Dict[str, float]
    edge_capacities: Dict[str, float]
    edge_saturation_pct: Dict[str, float]
    source_flows: Dict[str, float]
    sink_flows: Dict[str, float]
    total_source_capacity_m3s: float
    total_sink_capacity_m3s: float
    min_cut_source_nodes: Set[str]
    min_cut_sink_nodes: Set[str]
    min_cut_pipes: List[str]
    min_cut_capacity_m3s: float
    augmenting_paths: List[AugmentingPathStep]
    iterations: int
    method: str = "Ford-Fulkerson (Edmonds-Karp)"


def _add_residual_pair(
    res_adj: HashTable[str, LinkedList[_ResidualEdge]],
    u: str,
    v: str,
    capacity: float,
    pipe_id: Optional[str],
) -> _ResidualEdge:
    """Agrega un par de aristas (directa y reversa) a las listas de adyacencia residuales."""
    fwd = _ResidualEdge(to_node=v, cap=capacity, orig_cap=capacity, pipe_id=pipe_id, is_forward=True)
    rev = _ResidualEdge(to_node=u, cap=0.0, orig_cap=0.0, pipe_id=pipe_id, is_forward=False, rev=fwd)
    fwd.rev = rev
    res_adj[u].append(fwd)
    res_adj[v].append(rev)
    return fwd


def _find_augmenting_path_bfs(
    res_adj: HashTable[str, LinkedList[_ResidualEdge]],
    eps: float,
) -> tuple[bool, HashTable[str, Optional[str]], HashTable[str, Optional[_ResidualEdge]], HashTable[str, bool]]:
    """Busca el camino aumentante más corto en la red residual usando Queue y HashTable propias."""
    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable()
    parent_node: HashTable[str, Optional[str]] = HashTable()
    parent_edge: HashTable[str, Optional[_ResidualEdge]] = HashTable()

    visited.put(SUPER_SOURCE, True)
    parent_node.put(SUPER_SOURCE, None)
    parent_edge.put(SUPER_SOURCE, None)
    queue.enqueue(SUPER_SOURCE)

    found = False
    while not queue.is_empty():
        u = queue.dequeue()
        if u == SUPER_SINK:
            found = True
            break
        adj_u = res_adj.get(u)
        if adj_u is None:
            continue
        for edge in adj_u:
            if edge.cap > eps and not visited.contains(edge.to_node):
                visited.put(edge.to_node, True)
                parent_node.put(edge.to_node, u)
                parent_edge.put(edge.to_node, edge)
                queue.enqueue(edge.to_node)
                if edge.to_node == SUPER_SINK:
                    found = True
                    break
        if found:
            break

    return found, parent_node, parent_edge, visited


def ford_fulkerson_max_flow(
    graph: DirectedGraph,
    pipe_capacities: Optional[Dict[str, float]] = None,
    source_ids: Optional[List[str]] = None,
    sink_ids: Optional[List[str]] = None,
    source_caps: Optional[Dict[str, float]] = None,
    eps: float = 1e-12,
) -> MaxFlowResult:
    """Calcula el flujo máximo del sistema (m³/s) mediante Ford-Fulkerson (Edmonds-Karp).

    Utiliza únicamente `HashTable`, `LinkedList`, `Queue` y `Stack` propios del proyecto.
    Conecta todas las fuentes activas desde una súper-fuente virtual y todos los sumideros
    hacia un súper-sumidero virtual, preservando aristas paralelas y calculando el corte mínimo.
    """
    sources = [sid for sid in (source_ids if source_ids is not None else graph.source_ids()) if graph.has_node(sid)]
    sinks = [tid for tid in (sink_ids if sink_ids is not None else graph.sink_ids()) if graph.has_node(tid)]
    pipes = graph.pipes()

    eff_cap: Dict[str, float] = {}
    for pipe in pipes:
        raw_c = pipe_capacities.get(pipe.pipe_id, pipe.q_max_m3s) if pipe_capacities is not None else pipe.q_max_m3s
        eff_cap[pipe.pipe_id] = max(0.0, float(raw_c))

    total_src_cap = sum(
        eff_cap[e.pipe_id]
        for sid in sources
        for e in graph.outgoing_pipes(sid)
    )
    total_snk_cap = sum(
        eff_cap[e.pipe_id]
        for tid in sinks
        for e in graph.incoming_pipes(tid)
    )

    if not sources or not sinks or not pipes:
        return MaxFlowResult(
            max_flow_m3s=0.0,
            edge_flows={p.pipe_id: 0.0 for p in pipes},
            edge_capacities=eff_cap,
            edge_saturation_pct={p.pipe_id: 0.0 for p in pipes},
            source_flows={sid: 0.0 for sid in sources},
            sink_flows={tid: 0.0 for tid in sinks},
            total_source_capacity_m3s=total_src_cap,
            total_sink_capacity_m3s=total_snk_cap,
            min_cut_source_nodes=set(sources),
            min_cut_sink_nodes=set(graph.node_ids()) - set(sources),
            min_cut_pipes=[],
            min_cut_capacity_m3s=0.0,
            augmenting_paths=[],
            iterations=0,
        )

    res_adj: HashTable[str, LinkedList[_ResidualEdge]] = HashTable()
    res_adj.put(SUPER_SOURCE, LinkedList())
    res_adj.put(SUPER_SINK, LinkedList())
    for nid in graph.node_ids():
        res_adj.put(nid, LinkedList())

    total_network_cap = sum(eff_cap.values())
    inf_cap = max(1.0, total_network_cap * 2.0 + 10.0)

    src_edges: Dict[str, _ResidualEdge] = {}
    for sid in sources:
        s_cap = max(0.0, float(source_caps[sid])) if (source_caps is not None and sid in source_caps) else inf_cap
        src_edges[sid] = _add_residual_pair(res_adj, SUPER_SOURCE, sid, s_cap, None)

    snk_edges: Dict[str, _ResidualEdge] = {}
    for tid in sinks:
        snk_edges[tid] = _add_residual_pair(res_adj, tid, SUPER_SINK, inf_cap, None)

    pipe_forward_edges: List[tuple[PipeEdge, _ResidualEdge]] = []
    for pipe in pipes:
        fwd = _add_residual_pair(res_adj, pipe.from_node, pipe.to_node, eff_cap[pipe.pipe_id], pipe.pipe_id)
        pipe_forward_edges.append((pipe, fwd))

    max_flow = 0.0
    augmenting_paths: List[AugmentingPathStep] = []
    iterations = 0

    while True:
        found, parent_node, parent_edge, visited = _find_augmenting_path_bfs(res_adj, eps)
        if not found:
            break

        edge_stack: Stack[_ResidualEdge] = Stack()
        node_stack: Stack[str] = Stack()
        curr: Optional[str] = SUPER_SINK
        bottleneck = float("inf")

        while curr is not None and curr != SUPER_SOURCE:
            e = parent_edge.get(curr)
            prev_n = parent_node.get(curr)
            if e is None or prev_n is None:
                bottleneck = 0.0
                break
            if e.cap < bottleneck:
                bottleneck = e.cap
            edge_stack.push(e)
            if curr != SUPER_SINK:
                node_stack.push(curr)
            curr = prev_n

        if bottleneck <= eps or not edge_stack:
            break

        path_nodes: List[str] = []
        while not node_stack.is_empty():
            path_nodes.append(node_stack.pop())

        path_pipes: List[str] = []
        while not edge_stack.is_empty():
            e = edge_stack.pop()
            e.cap -= bottleneck
            if e.rev is not None:
                e.rev.cap += bottleneck
            if e.pipe_id is not None:
                path_pipes.append(e.pipe_id)

        max_flow += bottleneck
        iterations += 1
        augmenting_paths.append(
            AugmentingPathStep(
                iteration=iterations,
                nodes=path_nodes,
                pipe_ids=path_pipes,
                bottleneck_m3s=bottleneck,
                cumulative_flow_m3s=max_flow,
            )
        )

    edge_flows: Dict[str, float] = {}
    edge_saturation_pct: Dict[str, float] = {}
    for pipe, fwd in pipe_forward_edges:
        flow = max(0.0, fwd.orig_cap - fwd.cap)
        if flow <= eps:
            flow = 0.0
        edge_flows[pipe.pipe_id] = flow
        c_val = eff_cap[pipe.pipe_id]
        edge_saturation_pct[pipe.pipe_id] = (flow / c_val) * 100.0 if c_val > eps else 0.0

    source_flows: Dict[str, float] = {}
    for sid, e in src_edges.items():
        f_val = max(0.0, e.orig_cap - e.cap)
        source_flows[sid] = 0.0 if f_val <= eps else f_val

    sink_flows: Dict[str, float] = {}
    for tid, e in snk_edges.items():
        f_val = max(0.0, e.orig_cap - e.cap)
        sink_flows[tid] = 0.0 if f_val <= eps else f_val

    all_nodes = set(graph.node_ids())
    min_cut_source_nodes: Set[str] = {
        nid for nid in all_nodes if visited.contains(nid)
    }
    min_cut_sink_nodes: Set[str] = all_nodes - min_cut_source_nodes
    min_cut_pipes = sorted(
        p.pipe_id
        for p in pipes
        if p.from_node in min_cut_source_nodes
        and p.to_node not in min_cut_source_nodes
        and eff_cap[p.pipe_id] > eps
    )
    min_cut_capacity = sum(eff_cap[pid] for pid in min_cut_pipes)

    return MaxFlowResult(
        max_flow_m3s=max_flow,
        edge_flows=edge_flows,
        edge_capacities=eff_cap,
        edge_saturation_pct=edge_saturation_pct,
        source_flows=source_flows,
        sink_flows=sink_flows,
        total_source_capacity_m3s=total_src_cap,
        total_sink_capacity_m3s=total_snk_cap,
        min_cut_source_nodes=min_cut_source_nodes,
        min_cut_sink_nodes=min_cut_sink_nodes,
        min_cut_pipes=min_cut_pipes,
        min_cut_capacity_m3s=min_cut_capacity,
        augmenting_paths=augmenting_paths,
        iterations=iterations,
    )
