"""Pruebas unitarias para las estructuras de datos propias."""

import unittest

from src.data_structures import (
    DirectedGraph,
    HashTable,
    LinkedList,
    ManholeNode,
    PipeEdge,
    PriorityQueue,
    Queue,
    Stack,
)


class TestDataStructures(unittest.TestCase):
    def test_hash_table_crud_and_resize(self) -> None:
        ht: HashTable[str, int] = HashTable(initial_capacity=8)
        for i in range(40):
            ht.put(f"P{i}", i * 10)
        self.assertEqual(len(ht), 40)
        self.assertEqual(ht["P0"], 0)
        self.assertEqual(ht["P39"], 390)
        self.assertTrue("P15" in ht)
        ht.put("P15", 999)
        self.assertEqual(ht["P15"], 999)
        removed = ht.remove("P15")
        self.assertEqual(removed, 999)
        self.assertFalse(ht.contains("P15"))
        with self.assertRaises(KeyError):
            _ = ht["NO_EXISTE"]

    def test_linked_list_operations(self) -> None:
        ll: LinkedList[str] = LinkedList()
        ll.append("A")
        ll.append("B")
        ll.prepend("Z")
        self.assertEqual(ll.to_list(), ["Z", "A", "B"])
        self.assertEqual(list(ll.iter_backward()), ["B", "A", "Z"])
        self.assertEqual(ll.get_at(1), "A")
        self.assertEqual(ll.get_at(-1), "B")
        self.assertEqual(ll.pop_front(), "Z")
        self.assertEqual(ll.pop_back(), "B")
        self.assertEqual(len(ll), 1)

    def test_queue_and_stack_lifo_fifo(self) -> None:
        q: Queue[int] = Queue()
        s: Stack[int] = Stack()
        for val in (1, 2, 3):
            q.enqueue(val)
            s.push(val)
        self.assertEqual([q.dequeue(), q.dequeue(), q.dequeue()], [1, 2, 3])
        self.assertEqual([s.pop(), s.pop(), s.pop()], [3, 2, 1])
        self.assertTrue(q.is_empty())
        self.assertTrue(s.is_empty())

    def test_priority_queue_ordering_and_stability(self) -> None:
        pq: PriorityQueue[str] = PriorityQueue()
        pq.push(5.0, "cinco-a")
        pq.push(1.0, "uno")
        pq.push(5.0, "cinco-b")
        pq.push(2.5, "dos")
        ordered = [pq.pop()[1] for _ in range(len(pq))]
        self.assertEqual(ordered, ["uno", "dos", "cinco-a", "cinco-b"])

    def test_directed_graph_and_hydraulics(self) -> None:
        g = DirectedGraph()
        g.add_node(ManholeNode("1", node_type="source"))
        g.add_node(ManholeNode("31", node_type="sink"))
        p = PipeEdge("P1", "1", "C", 10.0, 0.254, 0.015, 0.01, 0.05376693, 1149.04)
        g.add_pipe(p)
        self.assertEqual(g.num_nodes, 3)
        self.assertEqual(g.num_pipes, 1)
        self.assertEqual(g.source_ids(), ["1"])
        self.assertEqual(g.sink_ids(), ["31"])
        self.assertIs(g.get_pipe("P1"), p)
        self.assertGreater(p.reference_velocity_ms, 0.9)
        self.assertGreater(p.transit_time_min, 15.0)
        with self.assertRaises(ValueError):
            g.add_pipe(p)


if __name__ == "__main__":
    unittest.main()
