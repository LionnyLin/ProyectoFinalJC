"""Algoritmos obligatorios de recorrido sobre el grafo dirigido propio."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from src.data_structures import DirectedGraph, HashTable, PipeEdge, Queue, Stack


@dataclass
class TraversalResult:
    """Resultado estructurado de un recorrido BFS o DFS."""

    algorithm: str
    start_node: str
    target_node: Optional[str]
    visited_order: List[str]
    traversed_edges: List[PipeEdge]
    levels: Dict[str, int]
    path_nodes: List[str]
    path_pipes: List[PipeEdge]
    target_reached: bool


@dataclass
class TraversalAnimFrame:
    """Fotograma paso a paso de la frontera y estructura propia (Queue / Stack)."""

    algorithm: str          # "BFS" | "DFS"
    step_index: int
    total_steps: int
    structure_name: str     # "Queue" | "Stack"
    structure_items: List[str]
    active_nodes: Set[str]
    active_edges: Set[str]
    visited_nodes: Set[str]
    visited_edges: Set[str]
    backtracked_nodes: Set[str]
    backtracked_edges: Set[str]
    cursor_node: Optional[str]
    note: str


def _reconstruct_path(
    start_id: str,
    target_id: str,
    parent_node: HashTable[str, Optional[str]],
    parent_pipe: HashTable[str, Optional[PipeEdge]],
) -> tuple[List[str], List[PipeEdge]]:
    """Reconstruye el camino desde `start_id` hasta `target_id` usando una Pila (Stack)."""
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

    nodes: List[str] = []
    while not node_stack.is_empty():
        nodes.append(node_stack.pop())

    pipes: List[PipeEdge] = []
    while not pipe_stack.is_empty():
        pipes.append(pipe_stack.pop())

    return nodes, pipes


def bfs(
    graph: DirectedGraph,
    start_id: str,
    target_id: Optional[str] = None,
) -> TraversalResult:
    """Recorrido en amplitud (BFS) implementado con Cola (Queue) y Tabla Hash propias."""
    if not graph.has_node(start_id):
        raise KeyError(f"Nodo inicial no encontrado en el grafo: {start_id}")
    if target_id is not None and not graph.has_node(target_id):
        raise KeyError(f"Nodo destino no encontrado en el grafo: {target_id}")

    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable()
    parent_node: HashTable[str, Optional[str]] = HashTable()
    parent_pipe: HashTable[str, Optional[PipeEdge]] = HashTable()
    levels_table: HashTable[str, int] = HashTable()

    visited_order: List[str] = []
    traversed_edges: List[PipeEdge] = []

    visited.put(start_id, True)
    parent_node.put(start_id, None)
    parent_pipe.put(start_id, None)
    levels_table.put(start_id, 0)
    queue.enqueue(start_id)

    reached = start_id == target_id

    while not queue.is_empty():
        current = queue.dequeue()
        visited_order.append(current)
        current_level = levels_table[current]

        if target_id is not None and current == target_id:
            reached = True
            break

        for edge in graph.outgoing_pipes(current):
            neighbor = edge.to_node
            if not visited.contains(neighbor):
                visited.put(neighbor, True)
                parent_node.put(neighbor, current)
                parent_pipe.put(neighbor, edge)
                levels_table.put(neighbor, current_level + 1)
                traversed_edges.append(edge)
                queue.enqueue(neighbor)

    path_nodes: List[str] = []
    path_pipes: List[PipeEdge] = []
    if target_id is not None and visited.contains(target_id):
        reached = True
        path_nodes, path_pipes = _reconstruct_path(
            start_id, target_id, parent_node, parent_pipe
        )

    levels_dict = {nid: levels_table[nid] for nid in visited_order if levels_table.contains(nid)}
    for k, v in levels_table.items():
        levels_dict.setdefault(k, v)

    return TraversalResult(
        algorithm="BFS",
        start_node=start_id,
        target_node=target_id,
        visited_order=visited_order,
        traversed_edges=traversed_edges,
        levels=levels_dict,
        path_nodes=path_nodes,
        path_pipes=path_pipes,
        target_reached=reached,
    )


def dfs(
    graph: DirectedGraph,
    start_id: str,
    target_id: Optional[str] = None,
) -> TraversalResult:
    """Recorrido en profundidad (DFS) iterativo implementado con Pila (Stack) y Tabla Hash propias."""
    if not graph.has_node(start_id):
        raise KeyError(f"Nodo inicial no encontrado en el grafo: {start_id}")
    if target_id is not None and not graph.has_node(target_id):
        raise KeyError(f"Nodo destino no encontrado en el grafo: {target_id}")

    stack: Stack[tuple[str, Optional[str], Optional[PipeEdge], int]] = Stack()
    visited: HashTable[str, bool] = HashTable()
    parent_node: HashTable[str, Optional[str]] = HashTable()
    parent_pipe: HashTable[str, Optional[PipeEdge]] = HashTable()
    depths: Dict[str, int] = {}

    visited_order: List[str] = []
    traversed_edges: List[PipeEdge] = []

    stack.push((start_id, None, None, 0))
    reached = False

    while not stack.is_empty():
        current, prev_node, prev_edge, depth = stack.pop()
        if visited.contains(current):
            continue

        visited.put(current, True)
        parent_node.put(current, prev_node)
        parent_pipe.put(current, prev_edge)
        depths[current] = depth
        visited_order.append(current)
        if prev_edge is not None:
            traversed_edges.append(prev_edge)

        if target_id is not None and current == target_id:
            reached = True
            break

        # Apilar en orden inverso para visitar primero las tuberías en su orden natural.
        outgoing = graph.outgoing_pipes(current).to_list()
        for edge in reversed(outgoing):
            if not visited.contains(edge.to_node):
                stack.push((edge.to_node, current, edge, depth + 1))

    path_nodes: List[str] = []
    path_pipes: List[PipeEdge] = []
    if target_id is not None and visited.contains(target_id):
        reached = True
        path_nodes, path_pipes = _reconstruct_path(
            start_id, target_id, parent_node, parent_pipe
        )

    return TraversalResult(
        algorithm="DFS",
        start_node=start_id,
        target_node=target_id,
        visited_order=visited_order,
        traversed_edges=traversed_edges,
        levels=depths,
        path_nodes=path_nodes,
        path_pipes=path_pipes,
        target_reached=reached,
    )


def bfs_anim_frames(
    graph: DirectedGraph,
    start_id: str,
    target_id: Optional[str] = None,
) -> Tuple[TraversalResult, List[TraversalAnimFrame]]:
    """Genera fotogramas por nivel (onda expansiva) usando Queue y HashTable propias."""
    if not graph.has_node(start_id):
        raise KeyError(f"Nodo inicial no encontrado en el grafo: {start_id}")
    if target_id is not None and not graph.has_node(target_id):
        raise KeyError(f"Nodo destino no encontrado en el grafo: {target_id}")

    queue: Queue[str] = Queue()
    visited: HashTable[str, bool] = HashTable()
    parent_node: HashTable[str, Optional[str]] = HashTable()
    parent_pipe: HashTable[str, Optional[PipeEdge]] = HashTable()
    levels_table: HashTable[str, int] = HashTable()

    visited_order: List[str] = []
    traversed_edges: List[PipeEdge] = []
    visited_nodes_set: Set[str] = set()
    visited_edges_set: Set[str] = set()
    frames: List[TraversalAnimFrame] = []

    visited.put(start_id, True)
    parent_node.put(start_id, None)
    parent_pipe.put(start_id, None)
    levels_table.put(start_id, 0)
    queue.enqueue(start_id)

    frames.append(
        TraversalAnimFrame(
            algorithm="BFS",
            step_index=0,
            total_steps=0,
            structure_name="Queue",
            structure_items=list(queue),
            active_nodes={start_id},
            active_edges=set(),
            visited_nodes={start_id},
            visited_edges=set(),
            backtracked_nodes=set(),
            backtracked_edges=set(),
            cursor_node=start_id,
            note=f"Encolado inicial: {start_id}",
        )
    )

    reached = start_id == target_id
    while not queue.is_empty():
        level_count = len(queue)
        wave_nodes: Set[str] = set()
        wave_edges: Set[str] = set()
        current_level = levels_table[queue.peek()]

        for _ in range(level_count):
            current = queue.dequeue()
            visited_order.append(current)
            visited_nodes_set.add(current)
            wave_nodes.add(current)
            in_edge = parent_pipe.get(current)
            if in_edge is not None:
                wave_edges.add(in_edge.pipe_id)
                visited_edges_set.add(in_edge.pipe_id)

            if target_id is not None and current == target_id:
                reached = True
                break

            if not reached:
                for edge in graph.outgoing_pipes(current):
                    neighbor = edge.to_node
                    if not visited.contains(neighbor):
                        visited.put(neighbor, True)
                        parent_node.put(neighbor, current)
                        parent_pipe.put(neighbor, edge)
                        levels_table.put(neighbor, current_level + 1)
                        traversed_edges.append(edge)
                        queue.enqueue(neighbor)

        frames.append(
            TraversalAnimFrame(
                algorithm="BFS",
                step_index=len(frames),
                total_steps=0,
                structure_name="Queue",
                structure_items=list(queue),
                active_nodes=set(wave_nodes),
                active_edges=set(wave_edges),
                visited_nodes=set(visited_nodes_set),
                visited_edges=set(visited_edges_set),
                backtracked_nodes=set(),
                backtracked_edges=set(),
                cursor_node=target_id if reached else None,
                note=f"Nivel {current_level}: onda de {len(wave_nodes)} nodo(s) ({', '.join(sorted(wave_nodes)[:6])})",
            )
        )
        if reached:
            break

    path_nodes: List[str] = []
    path_pipes: List[PipeEdge] = []
    if target_id is not None and visited.contains(target_id):
        reached = True
        path_nodes, path_pipes = _reconstruct_path(
            start_id, target_id, parent_node, parent_pipe
        )
        frames.append(
            TraversalAnimFrame(
                algorithm="BFS",
                step_index=len(frames),
                total_steps=0,
                structure_name="Queue",
                structure_items=[],
                active_nodes=set(path_nodes),
                active_edges={p.pipe_id for p in path_pipes},
                visited_nodes=set(visited_nodes_set),
                visited_edges=set(visited_edges_set),
                backtracked_nodes=set(),
                backtracked_edges=set(),
                cursor_node=target_id,
                note=f"Ruta óptima ({len(path_pipes)} tramos): {' → '.join(path_nodes)}",
            )
        )

    total = len(frames)
    for idx, fr in enumerate(frames):
        fr.step_index = idx
        fr.total_steps = total

    levels_dict = {nid: levels_table[nid] for nid in visited_order if levels_table.contains(nid)}
    for k, v in levels_table.items():
        levels_dict.setdefault(k, v)
    res = TraversalResult(
        algorithm="BFS",
        start_node=start_id,
        target_node=target_id,
        visited_order=visited_order,
        traversed_edges=traversed_edges,
        levels=levels_dict,
        path_nodes=path_nodes,
        path_pipes=path_pipes,
        target_reached=reached,
    )
    return res, frames


def dfs_anim_frames(
    graph: DirectedGraph,
    start_id: str,
    target_id: Optional[str] = None,
) -> Tuple[TraversalResult, List[TraversalAnimFrame]]:
    """Genera fotogramas de sonda profunda + backtracking usando Stack y HashTable propias."""
    if not graph.has_node(start_id):
        raise KeyError(f"Nodo inicial no encontrado en el grafo: {start_id}")
    if target_id is not None and not graph.has_node(target_id):
        raise KeyError(f"Nodo destino no encontrado en el grafo: {target_id}")

    stack: Stack[tuple[str, Optional[str], Optional[PipeEdge], int]] = Stack()
    visited: HashTable[str, bool] = HashTable()
    parent_node: HashTable[str, Optional[str]] = HashTable()
    parent_pipe: HashTable[str, Optional[PipeEdge]] = HashTable()
    depths: Dict[str, int] = {}

    visited_order: List[str] = []
    traversed_edges: List[PipeEdge] = []
    visited_nodes_set: Set[str] = set()
    visited_edges_set: Set[str] = set()
    frames: List[TraversalAnimFrame] = []

    stack.push((start_id, None, None, 0))
    frames.append(
        TraversalAnimFrame(
            algorithm="DFS",
            step_index=0,
            total_steps=0,
            structure_name="Stack",
            structure_items=[item[0] for item in stack],
            active_nodes={start_id},
            active_edges=set(),
            visited_nodes=set(),
            visited_edges=set(),
            backtracked_nodes=set(),
            backtracked_edges=set(),
            cursor_node=start_id,
            note=f"Apilado inicial: {start_id}",
        )
    )

    reached = False
    while not stack.is_empty():
        current, prev_node, prev_edge, depth = stack.pop()
        if visited.contains(current):
            continue

        visited.put(current, True)
        parent_node.put(current, prev_node)
        parent_pipe.put(current, prev_edge)
        depths[current] = depth
        visited_order.append(current)
        visited_nodes_set.add(current)
        if prev_edge is not None:
            traversed_edges.append(prev_edge)
            visited_edges_set.add(prev_edge.pipe_id)

        # Rama activa desde start_id hasta current
        branch_nodes, branch_edges = _reconstruct_path(
            start_id, current, parent_node, parent_pipe
        )
        branch_node_set = set(branch_nodes)
        branch_edge_set = {e.pipe_id for e in branch_edges}
        backtracked_nodes = visited_nodes_set - branch_node_set
        backtracked_edges = visited_edges_set - branch_edge_set

        if target_id is not None and current == target_id:
            reached = True
        else:
            outgoing = graph.outgoing_pipes(current).to_list()
            for edge in reversed(outgoing):
                if not visited.contains(edge.to_node):
                    stack.push((edge.to_node, current, edge, depth + 1))

        # Filtrar elementos ya visitados en la visualización de la pila para claridad didáctica
        stack_preview = [item[0] for item in stack if not visited.contains(item[0])]
        frames.append(
            TraversalAnimFrame(
                algorithm="DFS",
                step_index=len(frames),
                total_steps=0,
                structure_name="Stack",
                structure_items=stack_preview,
                active_nodes=branch_node_set,
                active_edges=branch_edge_set,
                visited_nodes=set(visited_nodes_set),
                visited_edges=set(visited_edges_set),
                backtracked_nodes=backtracked_nodes,
                backtracked_edges=backtracked_edges,
                cursor_node=current,
                note=f"Cursor en {current} (prof. {depth}) · Backtrack: {len(backtracked_nodes)} nodo(s)",
            )
        )
        if reached:
            break

    path_nodes: List[str] = []
    path_pipes: List[PipeEdge] = []
    if target_id is not None and visited.contains(target_id):
        reached = True
        path_nodes, path_pipes = _reconstruct_path(
            start_id, target_id, parent_node, parent_pipe
        )
        path_node_set = set(path_nodes)
        path_edge_set = {p.pipe_id for p in path_pipes}
        frames.append(
            TraversalAnimFrame(
                algorithm="DFS",
                step_index=len(frames),
                total_steps=0,
                structure_name="Stack",
                structure_items=[],
                active_nodes=path_node_set,
                active_edges=path_edge_set,
                visited_nodes=set(visited_nodes_set),
                visited_edges=set(visited_edges_set),
                backtracked_nodes=visited_nodes_set - path_node_set,
                backtracked_edges=visited_edges_set - path_edge_set,
                cursor_node=target_id,
                note=f"Ruta DFS ({len(path_pipes)} tramos): {' → '.join(path_nodes)}",
            )
        )

    total = len(frames)
    for idx, fr in enumerate(frames):
        fr.step_index = idx
        fr.total_steps = total

    res = TraversalResult(
        algorithm="DFS",
        start_node=start_id,
        target_node=target_id,
        visited_order=visited_order,
        traversed_edges=traversed_edges,
        levels=depths,
        path_nodes=path_nodes,
        path_pipes=path_pipes,
        target_reached=reached,
    )
    return res, frames


def topological_sort(graph: DirectedGraph) -> tuple[List[str], bool]:
    """Ordenamiento topológico (Kahn) usando Cola y Tabla Hash propias.

    Retorna `(orden, es_dag)`.
    """
    in_deg: HashTable[str, int] = HashTable()
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
            v = edge.to_node
            new_deg = in_deg[v] - 1
            in_deg.put(v, new_deg)
            if new_deg == 0:
                queue.enqueue(v)

    return order, len(order) == graph.num_nodes
