"""Búsqueda O(1) y consultas estructurales sobre el grafo dirigido."""

from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from src.data_structures import DirectedGraph, HashTable, ManholeNode, PipeEdge, Queue, Stack
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
                active_nodes={target_node},
            )
        )

    while not queue.is_empty():
        curr = queue.dequeue()
        nodes_order.append(curr)
        curr_level = levels.get(curr, 0)
        incoming = graph.incoming_pipes(curr)
        enqueued_upstream: List[str] = []
        last_edge_id: Optional[str] = None
        front_edges: set[str] = set()

        for edge in incoming:
            if not seen_pipes.contains(edge.pipe_id):
                seen_pipes.put(edge.pipe_id, True)
                pipes_list.append(edge)
                visited_edges_set.add(edge.pipe_id)
                last_edge_id = edge.pipe_id
            front_edges.add(edge.pipe_id)
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
                    active_nodes={curr, *enqueued_upstream},
                    active_edges=front_edges,
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


def find_node(graph: DirectedGraph, node_id: str) -> Optional[ManholeNode]:
    """Consulta directa O(1) de un vértice por su identificador."""
    return graph.get_node(node_id.strip())


def find_pipe(graph: DirectedGraph, pipe_id: str) -> Optional[PipeEdge]:
    """Consulta directa O(1) de una tubería por su identificador."""
    return graph.get_pipe(pipe_id.strip())


def search_entities(graph: DirectedGraph, query_text: str) -> Tuple[List[ManholeNode], List[PipeEdge]]:
    """Busca por subcadena en id/etiqueta/tipo de nodos y en id/origen/destino de tuberías."""
    q = query_text.strip().upper()
    if not q:
        return graph.nodes(), graph.pipes()
    nodes = [n for n in graph.nodes() if q in n.node_id.upper() or q in n.label.upper() or q in n.node_type.upper()]
    pipes = [p for p in graph.pipes() if q in p.pipe_id.upper() or q in p.from_node.upper() or q in p.to_node.upper()]
    return nodes, pipes


def find_isolated_from_sinks(
    graph: DirectedGraph, blocked_pipe_ids: Set[str], sink_ids: Optional[List[str]] = None,
) -> Tuple[Set[str], Set[str]]:
    """Nodos y tuberías incomunicados de la PTAR ante cierres totales (BFS inverso desde cada sumidero)."""
    if not blocked_pipe_ids:
        return set(), set()
    sinks = [sid for sid in (sink_ids or graph.sink_ids()) if graph.has_node(sid)]
    if not sinks:
        return set(), set()
    queue: Queue[str] = Queue()
    reachable: HashTable[str, bool] = HashTable(64)
    for sid in sinks:
        reachable.put(sid, True)
        queue.enqueue(sid)
    while not queue.is_empty():
        v = queue.dequeue()
        for edge in graph.incoming_pipes(v):
            if edge.pipe_id not in blocked_pipe_ids and not reachable.contains(edge.from_node):
                reachable.put(edge.from_node, True)
                queue.enqueue(edge.from_node)
    iso_nodes = {nid for nid in graph.node_ids() if not reachable.contains(nid)}
    iso_pipes = {
        e.pipe_id for e in graph.pipes()
        if e.pipe_id not in blocked_pipe_ids and (e.from_node in iso_nodes or e.to_node in iso_nodes)
    }
    return iso_nodes, iso_pipes


def _shortest_path_edges(graph: DirectedGraph, start_id: str, target_id: str) -> List[PipeEdge]:
    """Camino dirigido de menos saltos (BFS con Queue/HashTable y reconstrucción con Stack)."""
    if start_id == target_id or not graph.has_node(start_id) or not graph.has_node(target_id):
        return []
    queue: Queue[str] = Queue()
    parent_edge: HashTable[str, Optional[PipeEdge]] = HashTable(64)
    parent_edge.put(start_id, None)
    queue.enqueue(start_id)
    found = False
    while not queue.is_empty():
        u = queue.dequeue()
        if u == target_id:
            found = True
            break
        for edge in graph.outgoing_pipes(u):
            if not parent_edge.contains(edge.to_node):
                parent_edge.put(edge.to_node, edge)
                queue.enqueue(edge.to_node)
    if not found:
        return []
    stack: Stack[PipeEdge] = Stack()
    curr = target_id
    while curr != start_id:
        e = parent_edge.get(curr)
        if e is None:
            break
        stack.push(e)
        curr = e.from_node
    return [stack.pop() for _ in range(len(stack))]


def _nearest_upstream_source_path(graph: DirectedGraph, target_id: str) -> List[PipeEdge]:
    """Camino dirigido desde la fuente más cercana aguas arriba hasta `target_id` (BFS inverso)."""
    node = graph.get_node(target_id)
    if node is None or node.node_type == "source":
        return []
    queue: Queue[str] = Queue()
    child_edge: HashTable[str, Optional[PipeEdge]] = HashTable(64)
    child_edge.put(target_id, None)
    queue.enqueue(target_id)
    found: Optional[str] = None
    while not queue.is_empty():
        v = queue.dequeue()
        n = graph.get_node(v)
        if n is not None and n.node_type == "source":
            found = v
            break
        for edge in graph.incoming_pipes(v):
            if not child_edge.contains(edge.from_node):
                child_edge.put(edge.from_node, edge)
                queue.enqueue(edge.from_node)
    if found is None:
        return []
    path: List[PipeEdge] = []
    curr = found
    while curr != target_id:
        e = child_edge.get(curr)
        if e is None:
            break
        path.append(e)
        curr = e.to_node
    return path


def build_route_to_sink(
    graph: DirectedGraph, pipe_id: Optional[str] = None, node_id: Optional[str] = None, sink_id: str = "31",
) -> List[PipeEdge]:
    """Ruta fuente → punto seleccionado → PTAR (lista de tuberías) para el perfil longitudinal."""
    sinks = graph.sink_ids()
    target = sink_id if graph.has_node(sink_id) else (sinks[0] if sinks else "")
    if not target:
        return []
    if pipe_id is not None:
        edge = graph.get_pipe(pipe_id)
        if edge is None:
            return []
        return _nearest_upstream_source_path(graph, edge.from_node) + [edge] + _shortest_path_edges(graph, edge.to_node, target)
    if node_id is not None and graph.has_node(node_id):
        return _nearest_upstream_source_path(graph, node_id) + _shortest_path_edges(graph, node_id, target)
    return []
