"""Grafo dirigido propio para la red de alcantarillado de Ciudad Bicentenario."""

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple
from .hash_table import HashTable
from .linked_list import LinkedList


@dataclass
class ManholeNode:
    """Vértice del grafo: alcantarilla fuente, pozo de inspección o sumidero (PTAR)."""

    node_id: str
    node_type: str = "manhole"  # "source", "manhole", "sink"
    x: float = 0.5
    y: float = 0.5
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.node_id


@dataclass
class PipeEdge:
    """Arista dirigida del grafo: tubería con atributos geométricos e hidráulicos."""

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
        """Área transversal circular (m²)."""
        return math.pi * (self.diameter_m ** 2) / 4.0

    @property
    def reference_velocity_ms(self) -> float:
        """Velocidad de referencia a tubo lleno (m/s): V = Qmax / A."""
        area = self.area_m2
        if area <= 0.0:
            return 1.0
        return self.q_max_m3s / area

    @property
    def transit_time_s(self) -> float:
        """Tiempo de tránsito estimado (s): t_i = L_i / V_i."""
        vel = self.reference_velocity_ms
        if vel <= 0.0:
            return 0.0
        return self.length_m / vel

    @property
    def transit_time_min(self) -> float:
        """Tiempo de tránsito estimado (minutos)."""
        return self.transit_time_s / 60.0


class DirectedGraph:
    """Grafo dirigido con listas de adyacencia y tablas hash propias."""

    def __init__(self) -> None:
        self._nodes: HashTable[str, ManholeNode] = HashTable()
        self._pipes: HashTable[str, PipeEdge] = HashTable()
        self._adj: HashTable[str, LinkedList[PipeEdge]] = HashTable()
        self._radj: HashTable[str, LinkedList[PipeEdge]] = HashTable()
        self._sources: LinkedList[str] = LinkedList()
        self._sinks: LinkedList[str] = LinkedList()
        self._node_order: LinkedList[str] = LinkedList()
        self._pipe_order: LinkedList[str] = LinkedList()

    def add_node(self, node: ManholeNode) -> None:
        """Agrega o actualiza un nodo y su lista de adyacencia."""
        if node.node_id not in self._nodes:
            self._node_order.append(node.node_id)
            self._adj.put(node.node_id, LinkedList())
            self._radj.put(node.node_id, LinkedList())
            if node.node_type == "source":
                self._sources.append(node.node_id)
            elif node.node_type == "sink":
                self._sinks.append(node.node_id)
        else:
            prev = self._nodes[node.node_id]
            if prev.node_type != node.node_type:
                if prev.node_type == "source":
                    self._sources.remove_if(lambda nid: nid == node.node_id)
                elif prev.node_type == "sink":
                    self._sinks.remove_if(lambda nid: nid == node.node_id)
                if node.node_type == "source":
                    self._sources.append(node.node_id)
                elif node.node_type == "sink":
                    self._sinks.append(node.node_id)
        self._nodes.put(node.node_id, node)

    def add_pipe(self, pipe: PipeEdge) -> None:
        """Agrega una arista dirigida entre dos nodos (crea los nodos si no existen)."""
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

    def get_node(self, node_id: str) -> Optional[ManholeNode]:
        """Consulta un nodo en O(1) promedio mediante tabla hash."""
        return self._nodes.get(node_id)

    def get_pipe(self, pipe_id: str) -> Optional[PipeEdge]:
        """Consulta una tubería en O(1) promedio mediante tabla hash."""
        return self._pipes.get(pipe_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def has_pipe(self, pipe_id: str) -> bool:
        return pipe_id in self._pipes

    def outgoing_pipes(self, node_id: str) -> LinkedList[PipeEdge]:
        """Retorna la lista enlazada de tuberías salientes desde `node_id`."""
        adj_list = self._adj.get(node_id)
        if adj_list is None:
            raise KeyError(f"Nodo inexistente: {node_id}")
        return adj_list

    def incoming_pipes(self, node_id: str) -> LinkedList[PipeEdge]:
        """Retorna la lista enlazada de tuberías entrantes hacia `node_id`."""
        radj_list = self._radj.get(node_id)
        if radj_list is None:
            raise KeyError(f"Nodo inexistente: {node_id}")
        return radj_list

    def node_ids(self) -> List[str]:
        return self._node_order.to_list()

    def pipe_ids(self) -> List[str]:
        return self._pipe_order.to_list()

    def nodes(self) -> List[ManholeNode]:
        return [self._nodes[nid] for nid in self._node_order]

    def pipes(self) -> List[PipeEdge]:
        return [self._pipes[pid] for pid in self._pipe_order]

    def source_ids(self) -> List[str]:
        return self._sources.to_list()

    def sink_ids(self) -> List[str]:
        return self._sinks.to_list()

    def in_degree(self, node_id: str) -> int:
        return len(self.incoming_pipes(node_id))

    def out_degree(self, node_id: str) -> int:
        return len(self.outgoing_pipes(node_id))

    @property
    def num_nodes(self) -> int:
        return len(self._nodes)

    @property
    def num_pipes(self) -> int:
        return len(self._pipes)

    def total_network_length_m(self) -> float:
        return sum(p.length_m for p in self.pipes())

    def pipe_between(self, from_node: str, to_node: str) -> Optional[PipeEdge]:
        """Busca una tubería directa entre `from_node` y `to_node`."""
        for edge in self.outgoing_pipes(from_node):
            if edge.to_node == to_node:
                return edge
        return None

    def summary(self) -> Tuple[int, int, int, int, float]:
        """Retorna (n_nodos, n_tuberías, n_fuentes, n_sumideros, longitud_total_m)."""
        return (
            self.num_nodes,
            self.num_pipes,
            len(self._sources),
            len(self._sinks),
            self.total_network_length_m(),
        )
