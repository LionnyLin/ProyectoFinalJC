"""Pruebas unitarias para BFS, DFS, consultas y clasificación de criticidad."""

import os
import unittest

from src.algorithms import (
    bfs,
    classify_utilization,
    dfs,
    find_node,
    find_pipe,
    rank_critical_pipes,
    search_entities,
    topological_sort,
    trace_downstream,
    trace_upstream,
)
from src.io.data_loader import load_dataset


DATA_XLSX = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx")
)


class TestAlgorithms(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset(DATA_XLSX)
        cls.graph = cls.dataset.graph

    def test_topological_sort_is_dag(self) -> None:
        order, is_dag = topological_sort(self.graph)
        self.assertTrue(is_dag)
        self.assertEqual(len(order), 46)

    def test_bfs_and_dfs_reach_ptar_from_every_source(self) -> None:
        for src in self.graph.source_ids():
            res_bfs = bfs(self.graph, src, "31")
            res_dfs = dfs(self.graph, src, "31")
            self.assertTrue(res_bfs.target_reached, f"BFS falló desde {src}")
            self.assertTrue(res_dfs.target_reached, f"DFS falló desde {src}")
            self.assertEqual(res_bfs.path_nodes[0], src)
            self.assertEqual(res_bfs.path_nodes[-1], "31")
            self.assertEqual(len(res_bfs.path_pipes) + 1, len(res_bfs.path_nodes))
            self.assertEqual(res_dfs.path_nodes[0], src)
            self.assertEqual(res_dfs.path_nodes[-1], "31")

    def test_queries_and_tracing(self) -> None:
        self.assertIsNotNone(find_node(self.graph, "31"))
        self.assertIsNotNone(find_pipe(self.graph, "P30"))
        nodes, pipes = search_entities(self.graph, "P5")
        self.assertTrue(any(p.pipe_id == "P5" for p in pipes))
        down_nodes, _ = trace_downstream(self.graph, "6")
        self.assertIn("31", down_nodes)
        up_nodes, _ = trace_upstream(self.graph, "31")
        for src in self.graph.source_ids():
            self.assertIn(src, up_nodes)

    def test_utilization_color_scale_boundaries(self) -> None:
        self.assertEqual(classify_utilization(0.0).color_hex, "#22c55e")
        self.assertEqual(classify_utilization(25.0).color_hex, "#22c55e")
        self.assertEqual(classify_utilization(25.01).color_hex, "#eab308")
        self.assertEqual(classify_utilization(50.0).color_hex, "#eab308")
        self.assertEqual(classify_utilization(50.01).color_hex, "#f97316")
        self.assertEqual(classify_utilization(75.0).color_hex, "#f97316")
        self.assertEqual(classify_utilization(75.01).color_hex, "#ef4444")
        self.assertEqual(classify_utilization(100.0).color_hex, "#ef4444")
        cat_over = classify_utilization(100.1)
        self.assertEqual(cat_over.color_hex, "#7f1d1d")
        self.assertTrue(cat_over.is_overloaded)

    def test_rank_critical_pipes_order(self) -> None:
        flows = {p.pipe_id: 0.01 for p in self.graph.pipes()}
        utils = {p.pipe_id: 10.0 for p in self.graph.pipes()}
        utils["P30"] = 140.0
        utils["P1"] = 85.0
        ranked = rank_critical_pipes(self.graph, flows, utils, min_utilization_pct=75.0)
        self.assertEqual([r.pipe_id for r in ranked], ["P30", "P1"])


if __name__ == "__main__":
    unittest.main()
