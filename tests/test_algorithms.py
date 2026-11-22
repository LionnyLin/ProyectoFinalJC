"""Pruebas unitarias para BFS, DFS, frames, Kahn, consultas O(1) y criticidad."""

import os, unittest
from src.algorithms import (
    OVERLOAD_PERSISTENCE_LEVELS, UTILIZATION_LEVELS, UTILIZATION_SCALE, TraversalAnimFrame, TraversalFrame,
    bfs, bfs_anim_frames, build_route_to_sink, classify_overload_persistence, classify_utilization,
    compute_source_attribution, dfs, dfs_anim_frames, find_isolated_from_sinks, find_node, find_pipe,
    get_node_details, get_pipe_details, rank_critical_pipes, search_entities, search_entity,
    topological_sort, trace_downstream, trace_upstream, trace_upstream_result,
)
from src.simulation import PipeIntervention, SewerSimulationEngine, SimulationConfig
from src.io.data_loader import load_dataset

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


class TestAlgorithms(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_dataset(DATA_XLSX).graph

    def test_bfs_and_dfs_from_all_sources_to_ptar(self) -> None:
        sources = self.graph.source_ids()
        self.assertEqual(len(sources), 8)
        for src in sources:
            rb, rd = bfs(self.graph, src, "31"), dfs(self.graph, src, "31")
            self.assertTrue(rb.target_reached and rd.target_reached)
            self.assertLessEqual(len(rb.path_pipes), len(rd.path_pipes))
            for res in (rb, rd):
                self.assertEqual((res.path_nodes[0], res.path_nodes[-1]), (src, "31"))
                self.assertEqual(len(res.path_pipes) + 1, len(res.path_nodes))
                for idx, edge in enumerate(res.path_pipes):
                    self.assertEqual((edge.from_node, edge.to_node), (res.path_nodes[idx], res.path_nodes[idx + 1]))
                    self.assertTrue(self.graph.has_pipe(edge.pipe_id))

    def test_traversal_frame_recording_and_start_equals_target(self) -> None:
        for fn, struct in ((bfs, "Queue"), (dfs, "Stack")):
            res = fn(self.graph, "6", "31", record_frames=True)
            self.assertTrue(res.target_reached and len(res.frames) >= 3)
            prev_v = 0
            for idx, fr in enumerate(res.frames):
                self.assertEqual((fr.step_index, fr.total_steps, fr.structure_name), (idx, len(res.frames), struct))
                self.assertIsInstance(fr.structure_items, list)
                self.assertTrue(fr.active_edge is None or self.graph.has_pipe(fr.active_edge))
                self.assertGreaterEqual(len(fr.visited_nodes), prev_v)
                prev_v = len(fr.visited_nodes)
            self.assertIn("6", res.frames[0].structure_items)
            self.assertEqual((res.frames[-1].structure_items, res.frames[-1].active_edge), ([], res.path_pipes[-1].pipe_id))

        rb, rd = bfs(self.graph, "31", "31", record_frames=True), dfs(self.graph, "31", "31", record_frames=True)
        self.assertTrue(rb.target_reached and rd.target_reached)
        self.assertEqual((rb.path_nodes, rd.path_nodes, rb.path_pipes, rd.path_pipes), (["31"], ["31"], [], []))
        self.assertEqual((rb.visited_order, rb.levels), (rd.visited_order, rd.levels))
        self.assertTrue(all(fr.active_edge is None for fr in rb.frames + rd.frames))

    def test_topological_sort_respects_all_59_edges(self) -> None:
        order, is_dag = topological_sort(self.graph)
        self.assertTrue(is_dag and len(order) == 46 and self.graph.num_pipes == 59)
        pos = {nid: i for i, nid in enumerate(order)}
        for edge in self.graph.pipes():
            self.assertLess(pos[edge.from_node], pos[edge.to_node])

    def test_queries_search_details_and_tracing(self) -> None:
        for q, exp in (("31", ("node", "31")), (" c ", ("node", "C")), ("P30", ("pipe", "P30")),
                       ("p30", ("pipe", "P30")), ("NO_EXISTE", (None, None)), ("  ", (None, None))):
            self.assertEqual(search_entity(self.graph, q), exp)

        nd, pd = get_node_details(self.graph, "31"), get_pipe_details(self.graph, "P30")
        assert nd is not None and pd is not None
        self.assertTrue(len(nd.outgoing) == 0 and nd.total_incoming_capacity_m3s > 0.0)
        self.assertEqual((pd.from_node.node_id, pd.to_node.node_id), ("29", "31"))
        self.assertTrue(pd.velocity_ms > 0.0 and pd.transit_time_min > 0.0)
        self.assertIsNone(get_node_details(self.graph, "NO_EXISTE"))
        self.assertIsNone(get_pipe_details(self.graph, "P999"))

        self.assertIn("31", trace_downstream(self.graph, "6").visited_order)
        up_nodes, up_pipes = trace_upstream(self.graph, "31")
        self.assertEqual(len(up_pipes), 59)
        self.assertTrue(all(src in up_nodes for src in self.graph.source_ids()))
        with self.assertRaises(KeyError):
            trace_upstream(self.graph, "NO_EXISTE")

    def test_utilization_scale_and_critical_ranking(self) -> None:
        self.assertEqual((UTILIZATION_SCALE, len(UTILIZATION_SCALE)), (UTILIZATION_LEVELS, 5))
        bounds = [
            (0.0, "#22c55e", 0, False, False), (25.0, "#22c55e", 0, False, False),
            (25.01, "#eab308", 1, False, False), (50.0, "#eab308", 1, False, False),
            (50.01, "#f97316", 2, False, False), (75.0, "#f97316", 2, False, False),
            (75.01, "#ef4444", 3, True, False), (100.0, "#ef4444", 3, True, False),
            (100.01, "#991b1b", 4, True, True),
        ]
        for val, color, tier, crit, over in bounds:
            c = classify_utilization(val)
            self.assertEqual((c.color_hex, c.tier_index, c.is_critical, c.is_overloaded), (color, tier, crit, over))

        flows = {p.pipe_id: 0.01 for p in self.graph.pipes()}
        utils = {p.pipe_id: 10.0 for p in self.graph.pipes()}
        utils.update({"P30": 140.0, "P1": 85.0, "P5": 115.0})
        crit = rank_critical_pipes(self.graph, flows, utils, min_utilization_pct=75.0, exclusive_min=True)
        over = rank_critical_pipes(self.graph, flows, utils, min_utilization_pct=100.0, exclusive_min=True)
        self.assertEqual(([r.pipe_id for r in crit], [r.rank for r in crit]), (["P30", "P5", "P1"], [1, 2, 3]))
        self.assertEqual([r.pipe_id for r in over], ["P30", "P5"])
        self.assertTrue(all(r.excess_flow_m3s > 0.0 for r in over))

    def test_trace_upstream_result_downstream_frames_and_strict_75_100(self) -> None:
        up = trace_upstream_result(self.graph, "31", record_frames=True)
        self.assertEqual(up.algorithm, "UPSTREAM")
        self.assertEqual(up.start_node, "31")
        self.assertEqual(len(up.frames[-1].visited_edges), 59)
        self.assertTrue(set(self.graph.source_ids()).issubset(set(up.visited_order)))
        self.assertGreater(len(up.frames), 0)
        for idx, frame in enumerate(up.frames):
            self.assertEqual(frame.structure_name, "Queue")
            self.assertEqual(frame.step_index, idx)
            self.assertEqual(frame.total_steps, len(up.frames))

        with self.assertRaises(KeyError):
            trace_upstream_result(self.graph, "NO_EXISTE")

        down = trace_downstream(self.graph, "6", record_frames=True)
        self.assertGreater(len(down.frames), 0)
        self.assertTrue(all(f.structure_name == "Queue" for f in down.frames))

        flows = {p.pipe_id: 0.01 for p in self.graph.pipes()}
        utils = {p.pipe_id: 10.0 for p in self.graph.pipes()}
        utils.update({"P30": 140.0, "P1": 85.0, "P2": 100.0, "P3": 75.0, "P5": 115.0})
        strict_crit = rank_critical_pipes(
            self.graph,
            flows,
            utils,
            min_utilization_pct=75.0,
            max_utilization_pct=100.0,
            exclusive_min=True,
        )
        self.assertEqual([r.pipe_id for r in strict_crit], ["P2", "P1"])
        self.assertTrue(all(75.0 < r.utilization_pct <= 100.0 for r in strict_crit))

    def test_find_and_search_entities(self) -> None:
        self.assertEqual(find_node(self.graph, " 31 ").node_id, "31")
        self.assertIsNone(find_node(self.graph, "ZZZ"))
        self.assertEqual(find_pipe(self.graph, "P31 ").pipe_id, "P31")
        self.assertIsNone(find_pipe(self.graph, "P999"))
        nodes, pipes = search_entities(self.graph, "p3")
        self.assertTrue({"P3", "P30", "P31"} <= {p.pipe_id for p in pipes})
        nodes, pipes = search_entities(self.graph, "31")
        self.assertIn("31", {n.node_id for n in nodes})
        self.assertTrue({"P3", "P30"} <= {p.pipe_id for p in pipes})  # coincide por extremo de la tubería
        all_nodes, all_pipes = search_entities(self.graph, "  ")
        self.assertEqual((len(all_nodes), len(all_pipes)), (self.graph.num_nodes, 59))
        self.assertEqual(search_entities(self.graph, "no-existe-xyz"), ([], []))

    def test_isolation_route_and_traversal_anim_frames(self) -> None:
        self.assertEqual(find_isolated_from_sinks(self.graph, set()), (set(), set()))
        nodes, pipes = find_isolated_from_sinks(self.graph, {"P3"})
        self.assertEqual(nodes, {"C", "1", "27"})
        self.assertEqual(pipes, {"P1", "P2"})
        self.assertNotIn("31", nodes)
        # Cerrar P3 y P30 (únicas entradas a la PTAR) aísla toda la red salvo el sumidero
        n_all, _ = find_isolated_from_sinks(self.graph, {"P3", "P30"})
        self.assertEqual(len(n_all), self.graph.num_nodes - 1)

        for kwargs in ({"pipe_id": "P31"}, {"node_id": "17"}, {"node_id": "C"}):
            route = build_route_to_sink(self.graph, **kwargs)
            self.assertTrue(route and route[-1].to_node == "31")
            for a, b in zip(route, route[1:]):
                self.assertEqual(a.to_node, b.from_node)
            self.assertEqual(self.graph.get_node(route[0].from_node).node_type, "source")
        self.assertIn("P31", [e.pipe_id for e in build_route_to_sink(self.graph, pipe_id="P31")])
        self.assertEqual(build_route_to_sink(self.graph, pipe_id="NOPE"), [])
        self.assertEqual(build_route_to_sink(self.graph), [])
        self.assertEqual(build_route_to_sink(self.graph, node_id="31")[-1].to_node, "31")  # solo prefijo aguas arriba

        self.assertIs(TraversalAnimFrame, TraversalFrame)
        res_d, frames_d = dfs_anim_frames(self.graph, "17", "31")
        self.assertIs(frames_d, res_d.frames)
        self.assertTrue(res_d.target_reached and len(frames_d) > 2)
        _, frames_full = dfs_anim_frames(self.graph, "17")  # recorrido completo: hay ramas agotadas
        self.assertTrue(any(f.backtracked_nodes and f.backtracked_edges for f in frames_full), "DFS debe registrar retroceso")
        for f in frames_full + frames_d[:-1]:
            self.assertEqual(f.active_nodes | f.backtracked_nodes, f.visited_nodes | {f.current_node})
            self.assertFalse(f.active_nodes & f.backtracked_nodes)
            self.assertFalse(f.active_edges & f.backtracked_edges)
            self.assertIn("17", f.active_nodes)
            self.assertIn(f.current_node, f.active_nodes)
        last = frames_d[-1]
        self.assertEqual(last.active_nodes, set(res_d.path_nodes))
        self.assertEqual(last.active_edges, {p.pipe_id for p in res_d.path_pipes})

        res_b, frames_b = bfs_anim_frames(self.graph, "17", "31")
        self.assertTrue(res_b.target_reached and frames_b[0].active_nodes == {"17"})
        for f in frames_b[1:-1]:
            self.assertIn(f.current_node, f.active_nodes)
            self.assertTrue(f.active_nodes <= f.visited_nodes | set(f.structure_items))
            for pid in f.active_edges:
                e = self.graph.get_pipe(pid)
                self.assertTrue(e.to_node in f.active_nodes)
        self.assertTrue(any(len(f.active_nodes) > 1 for f in frames_b))
        self.assertEqual(frames_b[-1].active_nodes, set(res_b.path_nodes))
        self.assertEqual([f.step_index for f in frames_b], list(range(len(frames_b))))
        # Sin objetivo, bfs/dfs conservan su firma
        self.assertEqual(bfs(self.graph, "17").visited_order, bfs_anim_frames(self.graph, "17")[0].visited_order)
        self.assertEqual(dfs(self.graph, "17").frames, [])
        up = trace_upstream_result(self.graph, "31", record_frames=True)
        self.assertTrue(up.frames and all(f.current_node in f.active_nodes for f in up.frames))

    def test_source_attribution_and_overload_persistence_levels(self) -> None:
        graph = self.graph
        attr = compute_source_attribution(graph)
        sources = set(graph.source_ids())
        for nid, shares in attr.node_shares.items():
            if shares:
                self.assertAlmostEqual(sum(f for _, f in shares), 1.0, places=9)
                self.assertTrue({sid for sid, _ in shares} <= sources)
                self.assertEqual(shares, sorted(shares, key=lambda kv: (-kv[1], kv[0])))
        for sid in sources:
            self.assertEqual(attr.node_shares[sid], [(sid, 1.0)])
        self.assertEqual(len(attr.node_shares["31"]), len(sources))
        self.assertEqual(set(attr.pipe_shares), {p.pipe_id for p in graph.pipes()})

        engine = SewerSimulationEngine(graph, load_dataset(DATA_XLSX).basin)
        cfg = SimulationConfig(5, "Extrema", 100.0, interventions={"P3": PipeIntervention("P3", 100.0)})
        res = engine.run(cfg)
        snap = res.snapshots[40]
        live = compute_source_attribution(graph, snap)
        for nid, shares in live.node_shares.items():
            if shares:
                self.assertAlmostEqual(sum(f for _, f in shares), 1.0, places=9)
        self.assertEqual(live.pipe_shares["P3"], [])  # tubería cerrada: sin aporte atribuible
        self.assertEqual(live.node_shares["31"] != [], True)
        override = compute_source_attribution(graph, None, pipe_qmax_overrides={"P3": 0.0})
        self.assertEqual(override.pipe_shares["P3"], [])
        eq = compute_source_attribution(graph, None, "equal", source_distribution="equal")
        self.assertAlmostEqual(sum(f for _, f in eq.node_shares["31"]), 1.0, places=9)

        self.assertEqual(len(OVERLOAD_PERSISTENCE_LEVELS), 5)
        tiers = [classify_overload_persistence(m, 100.0)[0] for m in (0.0, 10.0, 40.0, 60.0, 90.0)]
        self.assertEqual(tiers, [0, 1, 2, 3, 4])

    def test_rank_critical_pipes_demand_tiebreak_and_overrides(self) -> None:
        ids = ("P1", "P2", "P3")
        utils = {"P1": 120.0, "P2": 120.0, "P3": 80.0}
        flows = {pid: 0.01 for pid in ids}
        base = rank_critical_pipes(self.graph, flows, utils, min_utilization_pct=50.0)
        self.assertEqual([r.pipe_id for r in base][-1], "P3")
        dem = {"P1": 130.0, "P2": 300.0, "P3": 80.0}
        ranked = rank_critical_pipes(self.graph, flows, utils, 50.0, pipe_demand_ratios_pct=dem)
        self.assertEqual([r.pipe_id for r in ranked], ["P2", "P1", "P3"])
        self.assertEqual([r.rank for r in ranked], [1, 2, 3])
        self.assertEqual(ranked[0].demand_ratio_pct, 300.0)
        self.assertEqual(base[0].demand_ratio_pct, base[0].utilization_pct)  # sin demanda: igual a la utilización
        qm = {"P1": 0.02}
        over = rank_critical_pipes(self.graph, flows, utils, 50.0, pipe_qmax_overrides=qm,
                                   pipe_excess_flows_m3s={"P2": 0.123})
        by_id = {r.pipe_id: r for r in over}
        self.assertEqual(by_id["P1"].q_max_m3s, 0.02)
        self.assertAlmostEqual(by_id["P1"].excess_flow_m3s, 0.2 * 0.02)
        self.assertEqual(by_id["P2"].excess_flow_m3s, 0.123)
        self.assertEqual(by_id["P2"].q_max_m3s, self.graph.get_pipe("P2").q_max_m3s)
        self.assertEqual(by_id["P3"].excess_flow_m3s, max(0.0, 0.01 - self.graph.get_pipe("P3").q_max_m3s,
                                                          (0.8 - 1.0) * self.graph.get_pipe("P3").q_max_m3s))
        # Los filtros siguen funcionando (llamadas posicionales previas intactas)
        self.assertEqual([r.pipe_id for r in rank_critical_pipes(self.graph, flows, utils, 100.0, None, True)], ["P1", "P2"])
        self.assertEqual([r.pipe_id for r in rank_critical_pipes(self.graph, flows, utils, 75.0, 100.0)], ["P3"])


if __name__ == "__main__":
    unittest.main()
