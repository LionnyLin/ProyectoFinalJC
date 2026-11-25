"""Pruebas unitarias para BFS, DFS, consultas y clasificación de criticidad."""

import os
import unittest

from src.algorithms import (
    bfs,
    bfs_anim_frames,
    build_route_to_sink,
    classify_overload_persistence,
    classify_utilization,
    compute_source_attribution,
    dfs,
    dfs_anim_frames,
    find_isolated_from_sinks,
    find_node,
    find_pipe,
    ford_fulkerson_max_flow,
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
        self.assertEqual(cat_over.color_hex, "#991b1b")
        self.assertTrue(cat_over.is_overloaded)

    def test_rank_critical_pipes_order(self) -> None:
        flows = {p.pipe_id: 0.01 for p in self.graph.pipes()}
        utils = {p.pipe_id: 10.0 for p in self.graph.pipes()}
        utils["P30"] = 140.0
        utils["P1"] = 85.0
        ranked = rank_critical_pipes(self.graph, flows, utils, min_utilization_pct=75.0, exclusive_min=True)
        self.assertEqual([r.pipe_id for r in ranked], ["P30", "P1"])
        ranked_near = rank_critical_pipes(
            self.graph, flows, utils, min_utilization_pct=75.0, max_utilization_pct=100.0, exclusive_min=True
        )
        self.assertEqual([r.pipe_id for r in ranked_near], ["P1"])
        ranked_rest = rank_critical_pipes(
            self.graph, flows, utils, min_utilization_pct=0.0, max_utilization_pct=75.0, exclusive_min=False
        )
        self.assertNotIn("P30", [r.pipe_id for r in ranked_rest])
        self.assertNotIn("P1", [r.pipe_id for r in ranked_rest])

    def test_isolation_route_and_traversal_anim_frames(self) -> None:
        iso_nodes, iso_pipes = find_isolated_from_sinks(self.graph, {"P3"})
        self.assertIn("C", iso_nodes)
        self.assertIn("1", iso_nodes)
        self.assertNotIn("31", iso_nodes)
        self.assertTrue(len(iso_pipes) > 0)

        route = build_route_to_sink(self.graph, pipe_id="P31", sink_id="31")
        self.assertTrue(len(route) >= 2)
        self.assertEqual(route[-1].to_node, "31")
        self.assertTrue(any(p.pipe_id == "P31" for p in route))

        res_b, frames_b = bfs_anim_frames(self.graph, "6", "31")
        self.assertTrue(res_b.target_reached)
        self.assertGreaterEqual(len(frames_b), 3)
        self.assertEqual(frames_b[0].structure_name, "Queue")

        res_d, frames_d = dfs_anim_frames(self.graph, "6", "31")
        self.assertTrue(res_d.target_reached)
        self.assertGreaterEqual(len(frames_d), 3)
        self.assertEqual(frames_d[0].structure_name, "Stack")

    def test_source_attribution_and_overload_persistence_levels(self) -> None:
        attr_prop = compute_source_attribution(self.graph, snapshot=None, split_rule="proportional")
        self.assertEqual(attr_prop.pipe_shares["P31"], [("17", 1.0)])
        sink_sum = sum(frac for _s, frac in attr_prop.node_shares["31"])
        self.assertAlmostEqual(sink_sum, 1.0, places=6)
        self.assertGreater(len(attr_prop.pipe_shares["P25"]), 1)

        attr_eq = compute_source_attribution(
            self.graph, snapshot=None, split_rule="equal", source_distribution="equal"
        )
        self.assertAlmostEqual(sum(frac for _s, frac in attr_eq.node_shares["31"]), 1.0, places=6)
        # Con reparto por capacidad vs uniforme 1/8, la participación de la fuente 9 en PTAR 31 cambia
        share_9_cap = dict(attr_prop.node_shares["31"]).get("9", 0.0)
        share_9_eq = dict(attr_eq.node_shares["31"]).get("9", 0.0)
        self.assertGreater(share_9_cap, share_9_eq)

        self.assertEqual(classify_overload_persistence(0.0, 90.0)[0], 0)
        self.assertEqual(classify_overload_persistence(15.0, 90.0)[0], 1)
        self.assertEqual(classify_overload_persistence(35.0, 90.0)[0], 2)
        self.assertEqual(classify_overload_persistence(60.0, 90.0)[0], 3)
        self.assertEqual(classify_overload_persistence(80.0, 90.0)[0], 4)

        # Tubería cerrada 100% no recibe atribución de fuentes (M3)
        attr_closed = compute_source_attribution(
            self.graph, snapshot=None, pipe_qmax_overrides={"P31": 0.0}
        )
        self.assertEqual(attr_closed.pipe_shares["P31"], [])

    def test_ford_fulkerson_max_flow_and_min_cut(self) -> None:
        from src.data_structures import DirectedGraph, ManholeNode, PipeEdge

        res = ford_fulkerson_max_flow(self.graph)
        self.assertAlmostEqual(res.max_flow_m3s, 0.35914566, places=5)
        self.assertAlmostEqual(res.max_flow_m3s, res.min_cut_capacity_m3s, places=9)
        self.assertEqual(sorted(res.min_cut_pipes), ["P28", "P3", "P43", "P53"])
        self.assertGreater(res.iterations, 0)
        self.assertEqual(len(res.augmenting_paths), res.iterations)

        # Conservación de flujo en fuentes, sumideros y nodos intermedios
        self.assertAlmostEqual(sum(res.source_flows.values()), res.max_flow_m3s, places=8)
        self.assertAlmostEqual(sum(res.sink_flows.values()), res.max_flow_m3s, places=8)
        in_node_flow = {nid: 0.0 for nid in self.graph.node_ids()}
        out_node_flow = {nid: 0.0 for nid in self.graph.node_ids()}
        for pid, q_val in res.edge_flows.items():
            pipe = self.graph.get_pipe(pid)
            cap = res.edge_capacities[pid]
            self.assertGreaterEqual(q_val, -1e-9)
            self.assertLessEqual(q_val, cap + 1e-9)
            out_node_flow[pipe.from_node] += q_val
            in_node_flow[pipe.to_node] += q_val
        for nid in self.graph.node_ids():
            node = self.graph.get_node(nid)
            if node.node_type not in ("source", "sink"):
                self.assertAlmostEqual(in_node_flow[nid], out_node_flow[nid], places=8)

        # Intervenciones: reducir tubería de corte mínimo y cerrar todo el corte mínimo
        p28_cap = self.graph.get_pipe("P28").q_max_m3s
        res_reduced = ford_fulkerson_max_flow(
            self.graph, pipe_capacities={"P28": 0.5 * p28_cap}
        )
        self.assertLess(res_reduced.max_flow_m3s, res.max_flow_m3s)

        p29_cap = self.graph.get_pipe("P29").q_max_m3s
        res_p29 = ford_fulkerson_max_flow(
            self.graph, pipe_capacities={"P29": 0.8 * p29_cap}
        )
        self.assertLessEqual(res_p29.max_flow_m3s, res.max_flow_m3s + 1e-12)

        res_blocked = ford_fulkerson_max_flow(
            self.graph,
            pipe_capacities={pid: 0.0 for pid in res.min_cut_pipes},
        )
        self.assertAlmostEqual(res_blocked.max_flow_m3s, 0.0, places=9)

        # Grafo sintético con aristas paralelas y cancelación en arista inversa residual
        g = DirectedGraph()
        g.add_node(ManholeNode(node_id="1", node_type="source"))
        g.add_node(ManholeNode(node_id="2", node_type="manhole"))
        g.add_node(ManholeNode(node_id="3", node_type="manhole"))
        g.add_node(ManholeNode(node_id="4", node_type="sink"))
        for pid, u, v, cap in [
            ("E1", "1", "2", 1.0),
            ("E2", "1", "2", 0.5),  # paralela 1 -> 2
            ("E3", "1", "3", 1.0),
            ("E4", "2", "3", 1.0),
            ("E5", "2", "4", 1.0),
            ("E6", "3", "4", 1.5),
        ]:
            g.add_pipe(
                PipeEdge(
                    pipe_id=pid,
                    from_node=u,
                    to_node=v,
                    diameter_in=20.0,
                    diameter_m=0.5,
                    manning_n=0.013,
                    slope=0.01,
                    q_max_m3s=cap,
                    length_m=10.0,
                )
            )
        syn = ford_fulkerson_max_flow(g)
        self.assertAlmostEqual(syn.max_flow_m3s, 2.5, places=9)
        self.assertAlmostEqual(syn.min_cut_capacity_m3s, 2.5, places=9)


if __name__ == "__main__":
    unittest.main()
