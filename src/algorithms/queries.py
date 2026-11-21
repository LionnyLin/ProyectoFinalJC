"""Búsqueda O(1) y consultas estructurales sobre el grafo dirigido."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.data_structures import DirectedGraph, HashTable, ManholeNode, PipeEdge, Queue
from .traversals import TraversalFrame, TraversalResult, bfs


@dataclass(slots=True)
class NodeQueryResult:
    """Información estructural de un pozo o alcantarilla."""

    node: ManholeNode
    incoming: List[PipeEdge]
    outgoing: List[PipeEdge]
    total_outgoing_capacity_m3s: float
    total_incoming_capacity_m3s: float


@dataclass(slots=True)
class PipeQueryResult:
    """Información estructural e hidráulica de una tubería."""

    pipe: PipeEdge
    from_node: Optional[ManholeNode]
    to_node: Optional[ManholeNode]
    area_m2: float
    velocity_ms: float
    transit_time_s: float
    transit_time_min: float


def search_entity(graph: DirectedGraph, query: str) -> Tuple[Optional[str], Optional[str]]:
    """Busca un nodo o tubería por ID usando la HashTable del grafo.

    Retorna ('node', node_id), ('pipe', pipe_id) o (None, None).
    """
    q = query.strip()
    if not q:
        return None, None
    q_up = q.upper()
    if graph.has_pipe(q):
        return "pipe", q
    if graph.has_pipe(q_up):
        return "pipe", q_up
    if graph.has_node(q):
        return "node", q
    if graph.has_node(q_up):
        return "node", q_up
    return None, None


def get_node_details(graph: DirectedGraph, node_id: str) -> Optional[NodeQueryResult]:
    """Retorna los atributos y conexiones entrantes/salientes de un nodo."""
    node = graph.get_node(node_id)
    if node is None:
        return None
    incoming = graph.incoming_pipes(node_id).to_list()
    outgoing = graph.outgoing_pipes(node_id).to_list()
    return NodeQueryResult(
        node=node,
        incoming=incoming,
        outgoing=outgoing,
        total_outgoing_capacity_m3s=sum(p.q_max_m3s for p in outgoing),
        total_incoming_capacity_m3s=sum(p.q_max_m3s for p in incoming),
    )


def get_pipe_details(graph: DirectedGraph, pipe_id: str) -> Optional[PipeQueryResult]:
    """Retorna atributos geométricos e hidráulicos de una tubería."""
    pipe = graph.get_pipe(pipe_id)
    if pipe is None:
        return None
    return PipeQueryResult(
        pipe=pipe,
        from_node=graph.get_node(pipe.from_node),
        to_node=graph.get_node(pipe.to_node),
        area_m2=pipe.area_m2,
        velocity_ms=pipe.reference_velocity_ms,
        transit_time_s=pipe.transit_time_s,
        transit_time_min=pipe.transit_time_min,
    )


def trace_downstream(
    graph: DirectedGraph,
    start_node: str,
    record_frames: bool = False,
) -> TraversalResult:
    """Traza todos los nodos y tuberías alcanzables aguas abajo mediante BFS."""
    return bfs(graph, start_node, record_frames=record_frames)


def trace_upstream(graph: DirectedGraph, target_node: str) -> Tuple[List[str], List[PipeEdge]]:
    """Traza todos los nodos y tuberías que drenan hacia `target_node` (BFS inverso)."""
    if not graph.has_node(target_node):
        raise KeyError(f"Nodo no encontrado en el grafo: {target_node}")

    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable(64)
    visited.put(target_node, True)
    queue.enqueue(target_node)

    nodes_order: List[str] = []
    pipes_list: List[PipeEdge] = []
    seen_pipes: HashTable[str, bool] = HashTable(128)

    while not queue.is_empty():
        curr = queue.dequeue()
        nodes_order.append(curr)
        for edge in graph.incoming_pipes(curr):
            if not seen_pipes.contains(edge.pipe_id):
                seen_pipes.put(edge.pipe_id, True)
                pipes_list.append(edge)
            if not visited.contains(edge.from_node):
                visited.put(edge.from_node, True)
                queue.enqueue(edge.from_node)

    return nodes_order, pipes_list


def trace_upstream_result(
    graph: DirectedGraph,
    target_node: str,
    record_frames: bool = False,
) -> TraversalResult:
    """Traza aguas arriba desde `target_node` (BFS inverso) y retorna TraversalResult."""
    if not graph.has_node(target_node):
        raise KeyError(f"Nodo no encontrado en el grafo: {target_node}")

    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable(64)
    levels: HashTable[str, int] = HashTable(64)
    seen_pipes: HashTable[str, bool] = HashTable(128)

    visited.put(target_node, True)
    levels.put(target_node, 0)
    queue.enqueue(target_node)

    nodes_order: List[str] = []
    pipes_list: List[PipeEdge] = []
    frames: List[TraversalFrame] = []
    visited_nodes_set = {target_node}
    visited_edges_set: set[str] = set()

    if record_frames:
        frames.append(
            TraversalFrame(
                step_index=0,
                total_steps=0,
                algorithm="UPSTREAM",
                current_node=target_node,
                active_edge=None,
                visited_nodes=set(visited_nodes_set),
                visited_edges=set(visited_edges_set),
                structure_name="Queue",
                structure_items=list(queue),
                note=f"Inicio aguas arriba desde nodo {target_node} (cola inversa)",
            )
        )

    while not queue.is_empty():
        curr = queue.dequeue()
        nodes_order.append(curr)
        curr_level = levels.get(curr, 0)
        incoming = graph.incoming_pipes(curr)
        enqueued_upstream: List[str] = []
        last_edge_id: Optional[str] = None

        for edge in incoming:
            if not seen_pipes.contains(edge.pipe_id):
                seen_pipes.put(edge.pipe_id, True)
                pipes_list.append(edge)
                visited_edges_set.add(edge.pipe_id)
                last_edge_id = edge.pipe_id
            if not visited.contains(edge.from_node):
                visited.put(edge.from_node, True)
                levels.put(edge.from_node, curr_level + 1)
                queue.enqueue(edge.from_node)
                visited_nodes_set.add(edge.from_node)
                enqueued_upstream.append(edge.from_node)

        if record_frames:
            if enqueued_upstream:
                note = f"Desencola nodo {curr} · Aportantes encolados: {', '.join(enqueued_upstream)}"
            elif last_edge_id is not None:
                note = f"Desencola nodo {curr} · Tuberías entrantes ya visitadas"
            else:
                note = f"Sin tuberías entrantes en nodo {curr}"
            frames.append(
                TraversalFrame(
                    step_index=0,
                    total_steps=0,
                    algorithm="UPSTREAM",
                    current_node=curr,
                    active_edge=last_edge_id,
                    visited_nodes=set(visited_nodes_set),
                    visited_edges=set(visited_edges_set),
                    structure_name="Queue",
                    structure_items=list(queue),
                    note=note,
                )
            )

    total = len(frames)
    for idx, frame in enumerate(frames):
        frame.step_index = idx
        frame.total_steps = total

    return TraversalResult(
        algorithm="UPSTREAM",
        start_node=target_node,
        target_node=None,
        visited_order=nodes_order,
        traversed_edges=pipes_list,
        levels=levels,
        path_nodes=[],
        path_pipes=[],
        target_reached=False,
        frames=frames,
    )
