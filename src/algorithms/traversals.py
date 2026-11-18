"""Algoritmos obligatorios de recorrido sobre el grafo dirigido propio."""

from dataclasses import dataclass
from typing import Dict, List, Optional
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
