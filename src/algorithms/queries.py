"""Búsqueda O(1) y consultas estructurales sobre el grafo dirigido."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.data_structures import DirectedGraph, HashTable, ManholeNode, PipeEdge, Queue
from .traversals import TraversalResult, bfs


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


def trace_downstream(graph: DirectedGraph, start_node: str) -> TraversalResult:
    """Traza todos los nodos y tuberías alcanzables aguas abajo mediante BFS."""
    return bfs(graph, start_node)


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
