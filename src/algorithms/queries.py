"""Algoritmos de búsqueda y consulta sobre alcantarillas, pozos y tuberías."""

from typing import List, Optional, Set, Tuple
from src.data_structures import DirectedGraph, HashTable, ManholeNode, PipeEdge, Queue, Stack


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


def find_isolated_from_sinks(
    graph: DirectedGraph,
    blocked_pipe_ids: Set[str],
    sink_ids: Optional[List[str]] = None,
) -> Tuple[Set[str], Set[str]]:
    """Determina qué nodos y tuberías quedan incomunicados de la PTAR ante cierres al 100%.

    Usa Queue y HashTable propias en sentido inverso desde cada sumidero activo.
    Retorna `(isolated_node_ids, isolated_pipe_ids)`.
    """
    if not blocked_pipe_ids:
        return set(), set()

    sinks = [sid for sid in (sink_ids or graph.sink_ids()) if graph.has_node(sid)]
    if not sinks:
        return set(), set()

    queue: Queue[str] = Queue()
    reachable: HashTable[str, bool] = HashTable()

    for sid in sinks:
        reachable.put(sid, True)
        queue.enqueue(sid)

    while not queue.is_empty():
        v = queue.dequeue()
        for edge in graph.incoming_pipes(v):
            if edge.pipe_id in blocked_pipe_ids:
                continue
            if not reachable.contains(edge.from_node):
                reachable.put(edge.from_node, True)
                queue.enqueue(edge.from_node)

    isolated_nodes: Set[str] = {
        nid for nid in graph.node_ids() if not reachable.contains(nid)
    }
    isolated_pipes: Set[str] = {
        edge.pipe_id
        for edge in graph.pipes()
        if edge.pipe_id not in blocked_pipe_ids
        and (edge.from_node in isolated_nodes or edge.to_node in isolated_nodes)
    }
    return isolated_nodes, isolated_pipes


def _shortest_path_edges(
    graph: DirectedGraph, start_id: str, target_id: str
) -> List[PipeEdge]:
    """Camino dirigido más corto en número de saltos usando Queue, HashTable y Stack."""
    if start_id == target_id or not graph.has_node(start_id) or not graph.has_node(target_id):
        return []

    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable()
    parent_edge: HashTable[str, Optional[PipeEdge]] = HashTable()
    visited.put(start_id, True)
    parent_edge.put(start_id, None)
    queue.enqueue(start_id)

    found = False
    while not queue.is_empty():
        u = queue.dequeue()
        if u == target_id:
            found = True
            break
        for edge in graph.outgoing_pipes(u):
            if not visited.contains(edge.to_node):
                visited.put(edge.to_node, True)
                parent_edge.put(edge.to_node, edge)
                queue.enqueue(edge.to_node)

    if not found:
        return []

    stack: Stack[PipeEdge] = Stack()
    curr: Optional[str] = target_id
    while curr is not None and curr != start_id:
        e = parent_edge.get(curr)
        if e is None:
            break
        stack.push(e)
        curr = e.from_node

    out: List[PipeEdge] = []
    while not stack.is_empty():
        out.append(stack.pop())
    return out


def _nearest_upstream_source_path(graph: DirectedGraph, target_id: str) -> List[PipeEdge]:
    """Encuentra el camino dirigido desde la fuente más cercana aguas arriba hasta `target_id`."""
    if not graph.has_node(target_id):
        return []
    target_node = graph.get_node(target_id)
    if target_node is not None and target_node.node_type == "source":
        return []

    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable()
    child_edge: HashTable[str, Optional[PipeEdge]] = HashTable()
    visited.put(target_id, True)
    child_edge.put(target_id, None)
    queue.enqueue(target_id)

    found_source: Optional[str] = None
    while not queue.is_empty():
        v = queue.dequeue()
        node_v = graph.get_node(v)
        if node_v is not None and node_v.node_type == "source":
            found_source = v
            break
        for edge in graph.incoming_pipes(v):
            if not visited.contains(edge.from_node):
                visited.put(edge.from_node, True)
                child_edge.put(edge.from_node, edge)
                queue.enqueue(edge.from_node)

    if found_source is None:
        return []

    path: List[PipeEdge] = []
    curr: Optional[str] = found_source
    while curr is not None and curr != target_id:
        e = child_edge.get(curr)
        if e is None:
            break
        path.append(e)
        curr = e.to_node
    return path


def build_route_to_sink(
    graph: DirectedGraph,
    pipe_id: Optional[str] = None,
    node_id: Optional[str] = None,
    sink_id: str = "31",
) -> List[PipeEdge]:
    """Construye una ruta completa fuente → punto seleccionado → PTAR para perfil longitudinal."""
    target_sink = sink_id if graph.has_node(sink_id) else (graph.sink_ids()[0] if graph.sink_ids() else "")
    if not target_sink:
        return []

    if pipe_id is not None:
        edge = graph.get_pipe(pipe_id)
        if edge is None:
            return []
        prefix = _nearest_upstream_source_path(graph, edge.from_node)
        suffix = _shortest_path_edges(graph, edge.to_node, target_sink)
        return prefix + [edge] + suffix

    if node_id is not None and graph.has_node(node_id):
        prefix = _nearest_upstream_source_path(graph, node_id)
        suffix = _shortest_path_edges(graph, node_id, target_sink)
        return prefix + suffix

    return []
