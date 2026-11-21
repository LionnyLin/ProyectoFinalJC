"""Grafo dirigido propio basado en tabla hash y listas enlazadas de adyacencia."""

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple

from .hash_table import HashTable
from .linked_list import LinkedList


@dataclass(slots=True)
class ManholeNode:
    """Vértice de la red: source, manhole o sink."""

    node_id: str
    node_type: str = "manhole"  # "source" | "manhole" | "sink"
    x: float = 0.0
    y: float = 0.0
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.node_id


@dataclass(slots=True)
class PipeEdge:
    """Arista dirigida: tubería con geometría y capacidad máxima Qmax (Manning)."""

    pipe_id: str
    from_node: str
    to_node: str
    diameter_in: float
    diameter_m: float
    manning_n: float
    slope: float
    q_max_m3s: float
    length_m: float
    note: str = ""

    @property
    def area_m2(self) -> float:
        return math.pi * (self.diameter_m ** 2) / 4.0

    @property
    def reference_velocity_ms(self) -> float:
        area = self.area_m2
        return self.q_max_m3s / area if area > 0.0 else 0.0

    @property
    def velocity_ms(self) -> float:
        return self.reference_velocity_ms

    @property
    def transit_time_s(self) -> float:
        v = self.reference_velocity_ms
        return self.length_m / v if v > 0.0 else 0.0

    @property
    def transit_time_min(self) -> float:
        return self.transit_time_s / 60.0


class DirectedGraph:
    """Grafo dirigido propio con HashTable O(1) y LinkedList para adyacencias."""

    def __init__(self) -> None:
        self._nodes: HashTable[str, ManholeNode] = HashTable(64)
        self._pipes: HashTable[str, PipeEdge] = HashTable(128)
        self._adj: HashTable[str, LinkedList[PipeEdge]] = HashTable(64)
        self._radj: HashTable[str, LinkedList[PipeEdge]] = HashTable(64)
        self._node_order: LinkedList[str] = LinkedList()
        self._pipe_order: LinkedList[str] = LinkedList()
        self._sources: LinkedList[str] = LinkedList()
        self._sinks: LinkedList[str] = LinkedList()

    def add_node(self, node: ManholeNode) -> None:
        nid = node.node_id
        prev = self._nodes.get(nid)
        if prev is None:
            self._node_order.append(nid)
            self._adj.put(nid, LinkedList())
            self._radj.put(nid, LinkedList())
        elif prev.node_type != node.node_type:
            if prev.node_type == "source":
                self._sources.remove_if(lambda x: x == nid)
            elif prev.node_type == "sink":
                self._sinks.remove_if(lambda x: x == nid)
        if prev is None or prev.node_type != node.node_type:
            if node.node_type == "source":
                self._sources.append(nid)
            elif node.node_type == "sink":
                self._sinks.append(nid)
        self._nodes.put(nid, node)

    def add_pipe(self, pipe: PipeEdge) -> None:
        if pipe.pipe_id in self._pipes:
            raise ValueError(f"Identificador de tubería duplicado: {pipe.pipe_id}")
        if pipe.from_node not in self._nodes:
            self.add_node(ManholeNode(node_id=pipe.from_node))
        if pipe.to_node not in self._nodes:
            self.add_node(ManholeNode(node_id=pipe.to_node))
        self._pipes.put(pipe.pipe_id, pipe)
        self._pipe_order.append(pipe.pipe_id)
        self._adj[pipe.from_node].append(pipe)
        self._radj[pipe.to_node].append(pipe)

    def outgoing_pipes(self, node_id: str) -> LinkedList[PipeEdge]:
        adj = self._adj.get(node_id)
        if adj is None:
            raise KeyError(f"Nodo inexistente: {node_id}")
        return adj

    def incoming_pipes(self, node_id: str) -> LinkedList[PipeEdge]:
        radj = self._radj.get(node_id)
        if radj is None:
            raise KeyError(f"Nodo inexistente: {node_id}")
        return radj

    def pipe_between(self, from_node: str, to_node: str) -> Optional[PipeEdge]:
        for edge in self.outgoing_pipes(from_node):
            if edge.to_node == to_node:
                return edge
        return None

    def get_node(self, node_id: str) -> Optional[ManholeNode]: return self._nodes.get(node_id)
    def get_pipe(self, pipe_id: str) -> Optional[PipeEdge]: return self._pipes.get(pipe_id)
    def has_node(self, node_id: str) -> bool: return node_id in self._nodes
    def has_pipe(self, pipe_id: str) -> bool: return pipe_id in self._pipes
    def node_ids(self) -> List[str]: return self._node_order.to_list()
    def pipe_ids(self) -> List[str]: return self._pipe_order.to_list()
    def nodes(self) -> List[ManholeNode]: return [self._nodes[nid] for nid in self._node_order]
    def pipes(self) -> List[PipeEdge]: return [self._pipes[pid] for pid in self._pipe_order]
    def source_ids(self) -> List[str]: return self._sources.to_list()
    def sink_ids(self) -> List[str]: return self._sinks.to_list()
    def in_degree(self, node_id: str) -> int: return len(self.incoming_pipes(node_id))
    def out_degree(self, node_id: str) -> int: return len(self.outgoing_pipes(node_id))
    def total_network_length_m(self) -> float: return sum(p.length_m for p in self.pipes())

    @property
    def num_nodes(self) -> int: return len(self._nodes)

    @property
    def num_pipes(self) -> int: return len(self._pipes)

    def summary(self) -> Tuple[int, int, int, int, float]:
        return (self.num_nodes, self.num_pipes, len(self._sources), len(self._sinks), self.total_network_length_m())
