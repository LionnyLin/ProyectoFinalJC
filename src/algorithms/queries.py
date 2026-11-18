"""Algoritmos de búsqueda y consulta sobre alcantarillas, pozos y tuberías."""

from typing import List, Optional, Tuple
from src.data_structures import DirectedGraph, HashTable, ManholeNode, PipeEdge, Queue


def find_node(graph: DirectedGraph, node_id: str) -> Optional[ManholeNode]:
    """Consulta directa O(1) de un vértice por su identificador."""
    return graph.get_node(node_id.strip())


def find_pipe(graph: DirectedGraph, pipe_id: str) -> Optional[PipeEdge]:
    """Consulta directa O(1) de una tubería por su identificador."""
    return graph.get_pipe(pipe_id.strip())


def search_entities(
    graph: DirectedGraph, query_text: str
) -> Tuple[List[ManholeNode], List[PipeEdge]]:
    """Busca nodos y tuberías cuyo identificador o conexión coincida con `query_text`."""
    q = query_text.strip().upper()
    if not q:
        return graph.nodes(), graph.pipes()

    matching_nodes: List[ManholeNode] = []
    for node in graph.nodes():
        if q in node.node_id.upper() or q in node.label.upper() or q in node.node_type.upper():
            matching_nodes.append(node)

    matching_pipes: List[PipeEdge] = []
    for pipe in graph.pipes():
        if (
            q in pipe.pipe_id.upper()
            or q in pipe.from_node.upper()
            or q in pipe.to_node.upper()
        ):
            matching_pipes.append(pipe)

    return matching_nodes, matching_pipes


def trace_downstream(
    graph: DirectedGraph, start_id: str
) -> Tuple[List[str], List[PipeEdge]]:
    """Retorna todos los nodos y tuberías aguas abajo alcanzables desde `start_id`."""
    if not graph.has_node(start_id):
        raise KeyError(f"Nodo inexistente: {start_id}")

    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable()
    nodes_out: List[str] = []
    pipes_out: List[PipeEdge] = []

    visited.put(start_id, True)
    queue.enqueue(start_id)

    while not queue.is_empty():
        u = queue.dequeue()
        nodes_out.append(u)
        for edge in graph.outgoing_pipes(u):
            pipes_out.append(edge)
            if not visited.contains(edge.to_node):
                visited.put(edge.to_node, True)
                queue.enqueue(edge.to_node)

    return nodes_out, pipes_out


def trace_upstream(
    graph: DirectedGraph, target_id: str
) -> Tuple[List[str], List[PipeEdge]]:
    """Retorna todos los nodos y tuberías aguas arriba que aportan caudal hacia `target_id`."""
    if not graph.has_node(target_id):
        raise KeyError(f"Nodo inexistente: {target_id}")

    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable()
    nodes_out: List[str] = []
    pipes_out: List[PipeEdge] = []

    visited.put(target_id, True)
    queue.enqueue(target_id)

    while not queue.is_empty():
        v = queue.dequeue()
        nodes_out.append(v)
        for edge in graph.incoming_pipes(v):
            pipes_out.append(edge)
            if not visited.contains(edge.from_node):
                visited.put(edge.from_node, True)
                queue.enqueue(edge.from_node)

    return nodes_out, pipes_out
