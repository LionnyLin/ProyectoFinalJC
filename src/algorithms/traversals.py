"""Algoritmos obligatorios de recorrido sobre el grafo dirigido propio (BFS, DFS y Kahn)."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from src.data_structures import DirectedGraph, HashTable, PipeEdge, Queue, Stack


@dataclass(slots=True)
class TraversalFrame:
    """Fotograma paso a paso mostrando el estado real de la Queue (BFS) o Stack (DFS)."""

    algorithm: str          # "BFS" | "DFS"
    step_index: int
    total_steps: int
    structure_name: str     # "Queue" | "Stack"
    structure_items: List[str]
    current_node: Optional[str]
    active_edge: Optional[str]
    visited_nodes: Set[str]
    visited_edges: Set[str]
    note: str
    active_nodes: Set[str] = field(default_factory=set)         # Frente activo (rama DFS / onda BFS)
    active_edges: Set[str] = field(default_factory=set)
    backtracked_nodes: Set[str] = field(default_factory=set)    # Visitados fuera de la rama actual (DFS)
    backtracked_edges: Set[str] = field(default_factory=set)


TraversalAnimFrame = TraversalFrame


@dataclass(slots=True)
class TraversalResult:
    """Resultado estructurado de un recorrido BFS o DFS (con fotogramas opcionales)."""

    algorithm: str
    start_node: str
    target_node: Optional[str]
    visited_order: List[str]
    traversed_edges: List[PipeEdge]
    levels: Dict[str, int]
    path_nodes: List[str]
    path_pipes: List[PipeEdge]
    target_reached: bool
    frames: List[TraversalFrame] = field(default_factory=list)


class _State:
    """Estado interno compartido por BFS y DFS usando HashTable propias."""

    __slots__ = (
        "visited", "parent_node", "parent_pipe", "levels",
        "visited_order", "traversed_edges", "frames", "visited_nodes", "visited_edges",
    )

    def __init__(self) -> None:
        self.visited: HashTable[str, bool] = HashTable(64)
        self.parent_node: HashTable[str, Optional[str]] = HashTable(64)
        self.parent_pipe: HashTable[str, Optional[PipeEdge]] = HashTable(64)
        self.levels: HashTable[str, int] = HashTable(64)
        self.visited_order: List[str] = []
        self.traversed_edges: List[PipeEdge] = []
        self.frames: List[TraversalFrame] = []
        self.visited_nodes: Set[str] = set()
        self.visited_edges: Set[str] = set()

    def mark(self, node: str, parent: Optional[str], pipe: Optional[PipeEdge], level: int) -> None:
        self.visited.put(node, True)
        self.parent_node.put(node, parent)
        self.parent_pipe.put(node, pipe)
        self.levels.put(node, level)

    def visit(self, node: str, edge: Optional[PipeEdge], record_frames: bool) -> Optional[str]:
        self.visited_order.append(node)
        active_id = edge.pipe_id if edge is not None else None
        if record_frames:
            self.visited_nodes.add(node)
            if active_id is not None:
                self.visited_edges.add(active_id)
        return active_id


def _validate_nodes(graph: DirectedGraph, start_id: str, target_id: Optional[str]) -> None:
    if not graph.has_node(start_id):
        raise KeyError(f"Nodo inicial no encontrado en el grafo: {start_id}")
    if target_id is not None and not graph.has_node(target_id):
        raise KeyError(f"Nodo destino no encontrado en el grafo: {target_id}")


def _record_frame(
    st: _State, algorithm: str, structure_name: str, structure_items: List[str],
    current_node: Optional[str], active_edge: Optional[str], note: str,
    active_nodes: Optional[Set[str]] = None, active_edges: Optional[Set[str]] = None,
    backtracked_nodes: Optional[Set[str]] = None, backtracked_edges: Optional[Set[str]] = None,
) -> None:
    """Agrega un fotograma del estado actual copiando los conjuntos visitados y el frente activo."""
    st.frames.append(TraversalFrame(
        algorithm, 0, 0, structure_name, structure_items, current_node,
        active_edge, set(st.visited_nodes), set(st.visited_edges), note,
        active_nodes or set(), active_edges or set(), backtracked_nodes or set(), backtracked_edges or set(),
    ))


def _record_dfs_frame(
    st: _State, stack: Stack, current: str, active_edge: Optional[str], start_id: str, note: str,
) -> None:
    """Fotograma DFS: rama actual (inicio → cursor) activa y el resto de visitados como retroceso."""
    branch_nodes, branch_pipes = _reconstruct_path(start_id, current, st.parent_node, st.parent_pipe)
    b_nodes, b_edges = set(branch_nodes), {p.pipe_id for p in branch_pipes}
    _record_frame(
        st, "DFS", "Stack", [i[0] for i in stack], current, active_edge, note,
        b_nodes, b_edges, st.visited_nodes - b_nodes, st.visited_edges - b_edges,
    )


def _reconstruct_path(
    start_id: str, target_id: str,
    parent_node: HashTable[str, Optional[str]], parent_pipe: HashTable[str, Optional[PipeEdge]],
) -> Tuple[List[str], List[PipeEdge]]:
    """Reconstruye el camino desde `start_id` hasta `target_id` usando una Stack propia."""
    if target_id not in parent_node:
        return [], []
    node_stack: Stack[str] = Stack()
    pipe_stack: Stack[PipeEdge] = Stack()
    curr: Optional[str] = target_id
    while curr is not None:
        node_stack.push(curr)
        edge = parent_pipe.get(curr)
        if edge is not None:
            pipe_stack.push(edge)
        if curr == start_id:
            break
        curr = parent_node.get(curr)
    if node_stack.is_empty() or node_stack.peek() != start_id:
        return [], []
    return (
        [node_stack.pop() for _ in range(len(node_stack))],
        [pipe_stack.pop() for _ in range(len(pipe_stack))],
    )


def _build_result(
    st: _State, algorithm: str, structure_name: str,
    start_id: str, target_id: Optional[str], reached: bool, record_frames: bool,
) -> TraversalResult:
    path_nodes, path_pipes = ([], [])
    if target_id is not None and st.visited.contains(target_id):
        reached = True
        path_nodes, path_pipes = _reconstruct_path(start_id, target_id, st.parent_node, st.parent_pipe)
        if record_frames:
            tag = "Ruta óptima" if algorithm == "BFS" else "Ruta DFS"
            last_edge = path_pipes[-1].pipe_id if path_pipes else None
            _record_frame(st, algorithm, structure_name, [], target_id, last_edge,
                          f"{tag} ({len(path_pipes)} tramos): {' -> '.join(path_nodes)}",
                          set(path_nodes), {p.pipe_id for p in path_pipes})
    if record_frames:
        total = len(st.frames)
        for idx, frame in enumerate(st.frames):
            frame.step_index, frame.total_steps = idx, total
    levels = {nid: st.levels[nid] for nid in st.visited_order if st.levels.contains(nid)}
    return TraversalResult(
        algorithm, start_id, target_id, st.visited_order, st.traversed_edges,
        levels, path_nodes, path_pipes, reached, st.frames,
    )


def bfs(
    graph: DirectedGraph, start_id: str, target_id: Optional[str] = None, record_frames: bool = False
) -> TraversalResult:
    """Recorrido en amplitud (BFS) usando Queue y HashTable propias."""
    _validate_nodes(graph, start_id, target_id)
    queue: Queue[str] = Queue()
    st = _State()
    st.mark(start_id, None, None, 0)
    queue.enqueue(start_id)
    if record_frames:
        _record_frame(st, "BFS", "Queue", list(queue), start_id, None, f"Inicio BFS: se encola {start_id}", {start_id}, set())

    reached = target_id is not None and start_id == target_id
    while not queue.is_empty():
        current = queue.dequeue()
        level = st.levels[current]
        active_id = st.visit(current, st.parent_pipe.get(current), record_frames)
        if target_id is not None and current == target_id:
            reached = True
            if record_frames:
                _record_frame(st, "BFS", "Queue", list(queue), current, active_id, f"Destino {target_id} alcanzado en nivel {level}",
                              {current}, set() if active_id is None else {active_id})
            break
        enqueued: List[str] = []
        new_edges: Set[str] = set() if active_id is None else {active_id}
        for edge in graph.outgoing_pipes(current):
            if not st.visited.contains(edge.to_node):
                st.mark(edge.to_node, current, edge, level + 1)
                st.traversed_edges.append(edge)
                queue.enqueue(edge.to_node)
                if record_frames:
                    enqueued.append(edge.to_node)
                    new_edges.add(edge.pipe_id)
        if record_frames:
            desc = f"Encola {', '.join(enqueued)}" if enqueued else "Sin vecinos nuevos por encolar"
            _record_frame(st, "BFS", "Queue", list(queue), current, active_id,
                          f"Desencola {current} (nivel {level}) · {desc}", {current, *enqueued}, new_edges)

    return _build_result(st, "BFS", "Queue", start_id, target_id, reached, record_frames)


def dfs(
    graph: DirectedGraph, start_id: str, target_id: Optional[str] = None, record_frames: bool = False
) -> TraversalResult:
    """Recorrido en profundidad (DFS) iterativo usando Stack y HashTable propias."""
    _validate_nodes(graph, start_id, target_id)
    stack: Stack[Tuple[str, Optional[str], Optional[PipeEdge], int]] = Stack()
    st = _State()
    stack.push((start_id, None, None, 0))
    if record_frames:
        _record_frame(st, "DFS", "Stack", [i[0] for i in stack], start_id, None, f"Inicio DFS: se apila {start_id}", {start_id}, set())

    reached = target_id is not None and start_id == target_id
    while not stack.is_empty():
        current, parent, via_edge, depth = stack.pop()
        if st.visited.contains(current):
            continue
        st.mark(current, parent, via_edge, depth)
        if via_edge is not None:
            st.traversed_edges.append(via_edge)
        active_id = st.visit(current, via_edge, record_frames)
        if target_id is not None and current == target_id:
            reached = True
            if record_frames:
                _record_dfs_frame(st, stack, current, active_id, start_id, f"Destino {target_id} alcanzado en profundidad {depth}")
            break
        pushed: List[str] = []
        for edge in reversed(graph.outgoing_pipes(current).to_list()):
            if not st.visited.contains(edge.to_node):
                stack.push((edge.to_node, current, edge, depth + 1))
                pushed.append(edge.to_node)
        if record_frames:
            desc = f"Apila {', '.join(reversed(pushed))}" if pushed else "Rama agotada (retroceso en pila)"
            _record_dfs_frame(st, stack, current, active_id, start_id, f"Desapila {current} (prof. {depth}) · {desc}")

    return _build_result(st, "DFS", "Stack", start_id, target_id, reached, record_frames)


def bfs_anim_frames(
    graph: DirectedGraph, start_id: str, target_id: Optional[str] = None
) -> Tuple[TraversalResult, List[TraversalFrame]]:
    """BFS con fotogramas de animación; retorna `(resultado, fotogramas)`."""
    result = bfs(graph, start_id, target_id, record_frames=True)
    return result, result.frames


def dfs_anim_frames(
    graph: DirectedGraph, start_id: str, target_id: Optional[str] = None
) -> Tuple[TraversalResult, List[TraversalFrame]]:
    """DFS con fotogramas de sonda profunda y retroceso; retorna `(resultado, fotogramas)`."""
    result = dfs(graph, start_id, target_id, record_frames=True)
    return result, result.frames


def topological_sort(graph: DirectedGraph) -> Tuple[List[str], bool]:
    """Ordenamiento topológico de Kahn usando Queue y HashTable propias."""
    in_deg: HashTable[str, int] = HashTable(64)
    queue: Queue[str] = Queue()
    for nid in graph.node_ids():
        deg = graph.in_degree(nid)
        in_deg.put(nid, deg)
        if deg == 0:
            queue.enqueue(nid)
    order: List[str] = []
    while not queue.is_empty():
        u = queue.dequeue()
        order.append(u)
        for edge in graph.outgoing_pipes(u):
            new_deg = in_deg[edge.to_node] - 1
            in_deg.put(edge.to_node, new_deg)
            if new_deg == 0:
                queue.enqueue(edge.to_node)
    return order, len(order) == graph.num_nodes
