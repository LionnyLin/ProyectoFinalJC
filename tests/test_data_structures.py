"""Pruebas unitarias para las estructuras de datos propias (sin librerías prohibidas)."""

import ast, math, os, unittest
from src.data_structures import (
    DirectedGraph, HashTable, LinkedList, ManholeNode, PipeEdge, PriorityQueue, Queue, Stack,
)

DS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "data_structures"))


class _CollidingKey:
    def __init__(self, label: str) -> None:
        self.label = label
    def __hash__(self) -> int:
        return 42
    def __eq__(self, other: object) -> bool:
        return isinstance(other, _CollidingKey) and self.label == other.label


class TestDataStructures(unittest.TestCase):
    def test_hash_table_crud_collisions_resize_and_add(self) -> None:
        ht: HashTable[object, float] = HashTable(initial_capacity=8)
        self.assertEqual(len(ht._buckets), 16)
        caps = {len(ht._buckets)}
        for i in range(40):
            ht.put(f"P{i}", float(i * 10))
            cap = len(ht._buckets)
            self.assertEqual(cap & (cap - 1), 0)
            caps.add(cap)
        self.assertTrue({16, 32, 64}.issubset(caps))
        self.assertEqual((len(ht), ht["P0"], ht["P39"]), (40, 0.0, 390.0))
        self.assertTrue("P15" in ht and ht.contains("P15"))

        ht["P15"] = 999.0
        self.assertEqual(ht.get("P15"), 999.0)
        self.assertAlmostEqual(ht.add("ACC", 2.5), 2.5)
        self.assertAlmostEqual(ht.add("ACC", 1.75), 4.25)
        self.assertAlmostEqual(ht["ACC"], 4.25)
        self.assertEqual(ht.remove("P15"), 999.0)
        self.assertFalse(ht.contains("P15"))
        with self.assertRaises(KeyError):
            _ = ht["NO_EXISTE"]

        ht_col: HashTable[_CollidingKey, int] = HashTable()
        keys = [_CollidingKey(f"K{i}") for i in range(6)]
        for i, k in enumerate(keys):
            ht_col.put(k, i)
        self.assertEqual([ht_col[k] for k in keys], list(range(6)))
        self.assertEqual(ht_col.remove(keys[2]), 2)
        self.assertFalse(ht_col.contains(keys[2]))
        self.assertEqual(ht_col[keys[5]], 5)

    def test_linked_list_queue_and_stack(self) -> None:
        ll: LinkedList[str] = LinkedList()
        self.assertTrue(ll.is_empty())
        for fn in (ll.pop_front, ll.pop_back, ll.peek_front, ll.peek_back):
            with self.assertRaises(IndexError):
                fn()
        ll.append("A"); ll.append("B"); ll.prepend("Z")
        self.assertEqual((ll.to_list(), list(ll), list(ll.iter_backward())), (["Z", "A", "B"], ["Z", "A", "B"], ["B", "A", "Z"]))
        self.assertEqual((ll.peek_front(), ll.peek_back(), ll.get_at(1), ll.get_at(-1)), ("Z", "B", "A", "B"))
        self.assertEqual((ll.pop_front(), ll.pop_back(), len(ll)), ("Z", "B", 1))

        q, s = Queue[int](), Stack[int]()
        for fn in (q.dequeue, q.peek, s.pop, s.peek):
            with self.assertRaises(IndexError):
                fn()
        for val in (1, 2, 3):
            q.enqueue(val); s.push(val)
        self.assertEqual((list(q), list(s), q.peek(), s.peek()), ([1, 2, 3], [3, 2, 1], 1, 3))
        self.assertEqual([q.dequeue() for _ in range(3)], [1, 2, 3])
        self.assertEqual([s.pop() for _ in range(3)], [3, 2, 1])
        self.assertTrue(q.is_empty() and s.is_empty())

    def test_priority_queue_min_heap_and_fifo_ties(self) -> None:
        pq: PriorityQueue[str] = PriorityQueue()
        with self.assertRaises(IndexError):
            pq.pop()
        for prio, item in ((5.0, "c-a"), (1.0, "uno"), (5.0, "c-b"), (2.5, "dos"), (5.0, "c-c")):
            pq.push(prio, item)
        self.assertEqual(pq.peek(), (1.0, "uno"))
        self.assertEqual([pq.pop()[1] for _ in range(len(pq))], ["uno", "dos", "c-a", "c-b", "c-c"])
        self.assertTrue(pq.is_empty())

    def test_directed_graph_slots_and_hydraulics(self) -> None:
        self.assertTrue(hasattr(ManholeNode, "__slots__") and hasattr(PipeEdge, "__slots__"))
        n1, n31 = ManholeNode("1", node_type="source"), ManholeNode("31", node_type="sink")
        p = PipeEdge("P1", "1", "C", 10.0, 0.254, 0.015, 0.01, 0.05376693, 1149.04)
        self.assertFalse(hasattr(n1, "__dict__") or hasattr(p, "__dict__"))
        g = DirectedGraph()
        g.add_node(n1); g.add_node(n31); g.add_pipe(p)
        self.assertEqual((g.num_nodes, g.num_pipes, g.source_ids(), g.sink_ids()), (3, 1, ["1"], ["31"]))
        self.assertEqual((g.in_degree("1"), g.out_degree("1"), g.in_degree("C"), g.out_degree("C")), (0, 1, 1, 0))
        self.assertIs(g.get_pipe("P1"), p)
        self.assertIs(g.pipe_between("1", "C"), p)
        self.assertEqual((g.outgoing_pipes("1").to_list(), g.incoming_pipes("C").to_list()), ([p], [p]))
        area = math.pi * (0.254 ** 2) / 4.0
        self.assertAlmostEqual(p.area_m2, area, places=9)
        self.assertAlmostEqual(p.reference_velocity_ms, 0.05376693 / area, places=6)
        self.assertAlmostEqual(p.velocity_ms, p.reference_velocity_ms, places=9)
        self.assertAlmostEqual(p.transit_time_s, 1149.04 / p.reference_velocity_ms, places=6)
        self.assertAlmostEqual(p.transit_time_min, p.transit_time_s / 60.0, places=6)
        with self.assertRaises(ValueError):
            g.add_pipe(p)

    def test_ast_no_forbidden_imports_in_data_structures(self) -> None:
        forbidden = {"collections", "heapq", "networkx"}
        py_files = [f for f in os.listdir(DS_DIR) if f.endswith(".py")]
        self.assertGreaterEqual(len(py_files), 6)
        for fname in py_files:
            with open(os.path.join(DS_DIR, fname), "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=fname)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden, f"{fname}: {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden, f"{fname}: {node.module}")


if __name__ == "__main__":
    unittest.main()
