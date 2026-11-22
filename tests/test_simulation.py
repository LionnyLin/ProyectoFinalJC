"""Pruebas de simulación temporal, Método Racional, balance de masa, reportes y rendimiento."""

import csv, os, tempfile, unittest
from docx import Document
from src.data_structures import LinkedList
from src.io.data_loader import load_dataset
from src.algorithms import find_isolated_from_sinks
from src.simulation import (
    PipeIntervention, SewerSimulationEngine, SimulationConfig, compare_all_scenarios,
    generate_docx_report, generate_markdown_report, resolve_pipe_hydraulics,
)

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


class TestSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset(DATA_XLSX)
        cls.engine = SewerSimulationEngine(cls.dataset.graph, cls.dataset.basin)

    def test_rational_method_and_dry_weather_zero(self) -> None:
        dry = self.engine.run(SimulationConfig(1, "Dry weather", 0.0, duration_min=60.0, storm_duration_min=45.0))
        self.assertEqual((dry.total_inflow_m3, dry.total_sink_discharge_m3, dry.total_surface_flooding_m3,
                          dry.max_mass_balance_error_m3, max(dry.peak_pipe_utilization.values())), (0.0, 0.0, 0.0, 0.0, 0.0))

        ext = self.engine.run(SimulationConfig(5, "Extreme rain", 100.0, duration_min=60.0, storm_duration_min=20.0))
        q_exp = 0.00278 * 0.75 * 100.0 * 388.0
        self.assertAlmostEqual(ext.snapshots[1].total_source_inflow_m3s, q_exp, places=6)
        self.assertAlmostEqual(ext.total_inflow_m3, q_exp * 20.0 * 60.0, delta=1e-3)

    def test_physical_transit_delay_and_dt_invariance(self) -> None:
        res_fine = self.engine.run(SimulationConfig(3, "Moderate rain", 30.0, duration_min=90.0, storm_duration_min=60.0, dt_min=0.5))
        for snap in res_fine.snapshots:
            if snap.time_min < 8.75:
                self.assertEqual(snap.total_sink_discharge_m3s, 0.0, f"Llegada prematura en t={snap.time_min}")
        self.assertGreater(res_fine.total_sink_discharge_m3, 0.0)

        vols, peaks = [], []
        for dt in (0.5, 1.0, 2.0, 5.0):
            r = self.engine.run(SimulationConfig(3, "Moderate rain", 30.0, duration_min=90.0, storm_duration_min=60.0, dt_min=dt))
            vols.append(r.total_sink_discharge_m3)
            peaks.append(max(r.peak_pipe_utilization.values()))
        self.assertLess((max(vols) - min(vols)) / min(vols), 0.02)
        self.assertLess((max(peaks) - min(peaks)) / min(peaks), 0.02)

    def test_linked_list_history_overload_and_repeatability(self) -> None:
        cfg = SimulationConfig(3, "Moderate rain", 30.0, duration_min=60.0, storm_duration_min=45.0, dt_min=1.0)
        res1 = self.engine.run(cfg)
        self.assertIsInstance(self.engine.history, LinkedList)
        self.assertEqual(len(self.engine.history), len(res1.snapshots))
        self.assertEqual([s.time_min for s in self.engine.history], [s.time_min for s in res1.snapshots])
        self.assertTrue(len(res1.ever_overloaded_pipes) > 0 and max(res1.peak_pipe_utilization.values()) > 100.0)

        for pid, ps in res1.snapshots[20].pipe_states.items():
            pipe = self.dataset.graph.get_pipe(pid)
            assert pipe is not None
            self.assertLessEqual(ps.flow_m3s, pipe.q_max_m3s + 1e-12)
            self.assertAlmostEqual(ps.utilization_pct, (ps.demand_flow_m3s / pipe.q_max_m3s) * 100.0, places=6)

        res2 = self.engine.run(cfg)
        self.assertEqual(len(res1.snapshots), len(res2.snapshots))
        for s1, s2 in zip(res1.snapshots, res2.snapshots):
            self.assertEqual(
                (s1.total_sink_discharge_m3s, s1.total_manhole_storage_m3, s1.total_surface_flooding_m3),
                (s2.total_sink_discharge_m3s, s2.total_manhole_storage_m3, s2.total_surface_flooding_m3),
            )

    def test_mass_balance_and_node_flow_coherence_all_5_scenarios(self) -> None:
        g, sinks = self.dataset.graph, set(self.dataset.graph.sink_ids())
        for sc in self.dataset.scenarios:
            res = self.engine.run(SimulationConfig(sc.scenario_id, sc.condition, sc.intensity_mm_h, duration_min=90.0, storm_duration_min=60.0))
            self.assertLess(res.max_mass_balance_error_m3, 1e-6)
            for snap in res.snapshots:
                self.assertLess(snap.mass_balance_error_m3, 1e-6)
                for nid in g.node_ids():
                    if nid not in sinks:
                        pipe_sum = sum(snap.pipe_states[p.pipe_id].flow_m3s for p in g.outgoing_pipes(nid))
                        self.assertAlmostEqual(snap.node_states[nid].outflow_m3s, pipe_sum, places=9)

    def test_split_rule_and_source_distribution_combinations(self) -> None:
        runs = {}
        for sr in ("proportional", "equal"):
            for sd in ("capacity", "equal"):
                r = self.engine.run(SimulationConfig(3, "Moderate rain", 30.0, 60.0, 45.0, 1.0, sr, sd))
                self.assertLess(r.max_mass_balance_error_m3, 1e-6)
                runs[(sr, sd)] = r
        self.assertNotAlmostEqual(runs[("proportional", "capacity")].total_sink_discharge_m3,
                                  runs[("equal", "capacity")].total_sink_discharge_m3, places=3)
        self.assertNotAlmostEqual(runs[("proportional", "capacity")].peak_pipe_utilization["P1"],
                                  runs[("proportional", "equal")].peak_pipe_utilization["P1"], places=2)

    def test_compare_all_scenarios_reports_and_performance(self) -> None:
        base_cfg = SimulationConfig(3, "Moderate rain", 30.0, duration_min=90.0, storm_duration_min=60.0, dt_min=1.0)
        single = self.engine.run(base_cfg)
        self.assertLess(single.execution_time_ms, 100.0, f"Simulación lenta: {single.execution_time_ms:.2f} ms")

        summaries = compare_all_scenarios(self.dataset, base_cfg)
        self.assertEqual(len(summaries), 5)
        self.assertGreater(summaries[4].max_utilization_pct, summaries[0].max_utilization_pct)
        self.assertTrue(all(s.mass_balance_error_m3 < 1e-6 for s in summaries))

        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = generate_markdown_report(self.dataset, summaries[2].result, summaries, os.path.join(tmpdir, "rep.md"))
            csv_path = os.path.join(tmpdir, "rep_tuberias.csv")
            docx_path = generate_docx_report(self.dataset, summaries[2].result, summaries, os.path.join(tmpdir, "rep.docx"))
            self.assertTrue(all(os.path.isfile(p) for p in (md_path, csv_path, docx_path)))
            with open(md_path, "r", encoding="utf-8") as fh:
                md_text = fh.read()
            self.assertTrue("PTAR Punta Canoa" in md_text and "## 5. Comparación" in md_text)
            with open(csv_path, "r", encoding="utf-8") as fh:
                self.assertEqual(len(list(csv.reader(fh))), 60)  # Encabezado + 59 tuberías
            doc = Document(docx_path)
            self.assertIn("Ciudad Bicentenario", "\n".join(p.text for p in doc.paragraphs))
            self.assertEqual((len(doc.tables), len(doc.tables[3].rows)), (4, 6))

    # ---- Intervenciones, ingreso, caudal sanitario y métricas de sobrecarga ----
    def _cfg(self, intensity=100.0, **kw) -> SimulationConfig:
        kw.setdefault("duration_min", 90.0)
        kw.setdefault("storm_duration_min", 60.0)
        return SimulationConfig(5, "Test", intensity, **kw)

    def test_pipe_intervention_validation_and_hydraulics(self) -> None:
        for bad in (-1.0, 100.1, float("nan")):
            with self.assertRaises(ValueError):
                PipeIntervention("P3", obstruction_pct=bad)
        for bad in (0.0, -4.0, float("inf")):
            with self.assertRaises(ValueError):
                PipeIntervention("P3", diameter_in_override=bad)
        self.assertTrue(PipeIntervention("P3", 100.0).is_closed and PipeIntervention("P3", 10.0).has_obstruction)
        edge = self.dataset.graph.get_pipe("P3")
        q0, v0, t0, d0 = resolve_pipe_hydraulics(edge, None)
        q_obs, _, _, _ = resolve_pipe_hydraulics(edge, PipeIntervention("P3", 50.0))
        q_big, v_big, t_big, d_big = resolve_pipe_hydraulics(edge, PipeIntervention("P3", 0.0, edge.diameter_in * 1.5))
        self.assertAlmostEqual(q_obs, 0.5 * q0, places=9)
        self.assertGreater(q_big, q0)
        self.assertGreater(v_big, v0)
        self.assertLess(t_big, t0)
        self.assertAlmostEqual(d_big, edge.diameter_in * 1.5)

    def test_live_interventions_obstruction_closure_and_mass_balance(self) -> None:
        base = self.engine.run(self._cfg())
        q0 = self.dataset.graph.get_pipe("P3").q_max_m3s
        obs = self.engine.run(self._cfg(interventions={"P3": PipeIntervention("P3", 50.0)}))
        ps_base, ps_obs = base.snapshots[30].pipe_states["P3"], obs.snapshots[30].pipe_states["P3"]
        self.assertAlmostEqual(obs.snapshots[0].pipe_states["P3"].effective_q_max_m3s, 0.5 * q0, places=9)
        self.assertAlmostEqual(ps_obs.effective_q_max_m3s, 0.5 * q0, places=9)
        self.assertEqual(ps_base.effective_q_max_m3s, q0)
        self.assertGreater(obs.peak_pipe_utilization["P3"], base.peak_pipe_utilization["P3"])
        self.assertLess(obs.peak_pipe_flow["P3"], q0)

        closed = self.engine.run(self._cfg(interventions={"P3": PipeIntervention("P3", 100.0)}))
        for snap in closed.snapshots:
            ps = snap.pipe_states["P3"]
            self.assertTrue(ps.is_closed)
            self.assertEqual((ps.flow_m3s, ps.utilization_pct, ps.category.tier_index), (0.0, 0.0, 0))
            self.assertEqual(ps.excess_flow_m3s, ps.demand_flow_m3s)
        self.assertEqual(closed.peak_pipe_flow["P3"], 0.0)
        self.assertGreater(closed.peak_pipe_demand_flow["P3"], 0.0)
        self.assertEqual(closed.total_sink_discharge_m3 > 0.0, True)  # P30 sigue operando
        self.assertFalse(closed.snapshots[10].pipe_states["P30"].is_closed)
        iso_nodes, iso_pipes = find_isolated_from_sinks(self.dataset.graph, {"P3"})
        self.assertTrue({"C", "1", "27"} <= iso_nodes and {"P1", "P2"} <= iso_pipes)

        bigger = self.engine.run(self._cfg(interventions={"P3": PipeIntervention("P3", 0.0, 24.0)}))
        self.assertGreater(bigger.snapshots[5].pipe_states["P3"].effective_q_max_m3s, q0)
        self.assertGreater(bigger.snapshots[5].pipe_states["P3"].effective_velocity_ms,
                           self.dataset.graph.get_pipe("P3").reference_velocity_ms)
        for res in (obs, closed, bigger):
            self.assertLess(res.max_mass_balance_error_m3, 1e-8)
        # Cierre total de las salidas de una fuente: el agua se retiene o rebosa, nunca se pierde
        outs = {p.pipe_id: PipeIntervention(p.pipe_id, 100.0) for p in self.dataset.graph.outgoing_pipes("1")}
        res = self.engine.run(self._cfg(interventions=outs))
        self.assertLess(res.max_mass_balance_error_m3, 1e-8)
        self.assertGreater(res.total_surface_flooding_m3, 0.0)

    def test_ingress_factor_and_dry_weather_flow(self) -> None:
        full = self.engine.run(self._cfg(duration_min=30.0, storm_duration_min=20.0))
        part = self.engine.run(self._cfg(duration_min=30.0, storm_duration_min=20.0, ingress_factor=0.025))
        self.assertAlmostEqual(part.total_inflow_m3, full.total_inflow_m3 * 0.025, delta=1e-6)
        self.assertAlmostEqual(part.snapshots[1].total_source_inflow_m3s, full.snapshots[1].total_source_inflow_m3s * 0.025, places=9)

        n_src, q_san = len(self.dataset.graph.source_ids()), 0.002
        dry = self.engine.run(self._cfg(0.0, duration_min=40.0, dry_weather_flow_per_source_m3s=q_san))
        for snap in dry.snapshots[1:]:
            self.assertAlmostEqual(snap.total_source_inflow_m3s, n_src * q_san, places=9)
        self.assertAlmostEqual(dry.total_inflow_m3, n_src * q_san * 40.0 * 60.0, delta=1e-6)
        self.assertGreater(dry.total_sink_discharge_m3, 0.0)
        self.assertLess(dry.max_mass_balance_error_m3, 1e-8)
        # Sanitario + lluvia se suman; el sanitario no se escala por el factor de ingreso
        mix = self.engine.run(self._cfg(duration_min=30.0, storm_duration_min=20.0, ingress_factor=0.5, dry_weather_flow_per_source_m3s=q_san))
        exp = full.snapshots[1].total_source_inflow_m3s * 0.5 + n_src * q_san
        self.assertAlmostEqual(mix.snapshots[1].total_source_inflow_m3s, exp, places=9)
        self.assertAlmostEqual(mix.snapshots[-1].total_source_inflow_m3s, n_src * q_san, places=9)  # tras la tormenta
        self.assertLess(mix.max_mass_balance_error_m3, 1e-8)
        # Invarianza ante Δt con caudal sanitario
        v = [self.engine.run(self._cfg(0.0, duration_min=40.0, dt_min=dt, dry_weather_flow_per_source_m3s=q_san)).total_inflow_m3 for dt in (0.5, 1.0, 5.0)]
        self.assertAlmostEqual(v[0], v[2], delta=1e-6)

    def test_public_source_inflow_api(self) -> None:
        cfg = self._cfg(ingress_factor=0.5, dry_weather_flow_per_source_m3s=0.001)
        q_total, per_src = self.engine.compute_source_inflows_by_source(cfg, 100.0)
        n = len(self.dataset.graph.source_ids())
        self.assertEqual(set(per_src), set(self.dataset.graph.source_ids()))
        self.assertAlmostEqual(q_total, sum(per_src.values()))
        self.assertAlmostEqual(q_total, 0.5 * 0.00278 * 0.75 * 100.0 * 388.0 + n * 0.001, places=9)
        t2, avg = self.engine.compute_source_inflow_m3s(cfg, 100.0)
        self.assertAlmostEqual((t2, avg), (q_total, q_total / n))
        eq_cfg = self._cfg(source_distribution="equal")
        _, eq = self.engine.compute_source_inflows_by_source(eq_cfg, 50.0)
        self.assertTrue(max(eq.values()) - min(eq.values()) < 1e-12)
        # Con cierre total de las salidas de una fuente, esa fuente deja de recibir aporte por capacidad
        outs = {p.pipe_id: PipeIntervention(p.pipe_id, 100.0) for p in self.dataset.graph.outgoing_pipes("1")}
        _, closed = self.engine.compute_source_inflows_by_source(self._cfg(interventions=outs), 50.0)
        self.assertEqual(closed["1"], 0.0)

    def test_overloaded_minutes_and_peak_demand_metrics(self) -> None:
        res = self.engine.run(self._cfg(duration_min=90.0))
        mins = res.pipe_overloaded_minutes
        self.assertEqual(set(mins), set(res.peak_pipe_utilization))
        self.assertTrue(all(0.0 <= m <= 90.0 + 1e-9 for m in mins.values()))
        self.assertEqual({pid for pid, m in mins.items() if m > 0.0}, set(res.ever_overloaded_pipes))
        for pid in res.ever_overloaded_pipes:  # minutos = suma de dt de instantáneas sobrecargadas
            n = sum(1 for sn in res.snapshots[1:] if sn.pipe_states[pid].utilization_pct > 100.0)
            self.assertAlmostEqual(mins[pid], float(n))
        for pid, ratio in res.peak_pipe_demand_ratio.items():
            self.assertGreaterEqual(ratio + 1e-9, res.peak_pipe_utilization[pid])
            self.assertGreaterEqual(res.peak_pipe_demand_flow[pid] + 1e-12, res.peak_pipe_flow[pid])
        worst = max(res.peak_pipe_demand_ratio, key=res.peak_pipe_demand_ratio.get)
        self.assertGreater(res.peak_pipe_demand_ratio[worst], 100.0)
        self.assertEqual(set(res.max_node_flooding_m3), set(self.dataset.graph.node_ids()))
        self.assertAlmostEqual(sum(res.max_node_flooding_m3.values()), res.total_surface_flooding_m3, delta=1e-6)
        none = self.engine.run(self._cfg(0.0))
        self.assertTrue(all(m == 0.0 for m in none.pipe_overloaded_minutes.values()))
        # Duración acotada con Δt grueso
        coarse = self.engine.run(self._cfg(duration_min=90.0, dt_min=30.0))
        self.assertTrue(all(m <= 90.0 + 1e-9 for m in coarse.pipe_overloaded_minutes.values()))

    def test_comparison_propagates_config_and_demand_ratio(self) -> None:
        iv = {"P3": PipeIntervention("P3", 50.0)}
        cfg = self._cfg(ingress_factor=0.5, dry_weather_flow_per_source_m3s=0.001, interventions=iv)
        sums = compare_all_scenarios(self.dataset, cfg)
        for sm in sums:
            self.assertEqual(sm.result.config.ingress_factor, 0.5)
            self.assertEqual(sm.result.config.dry_weather_flow_per_source_m3s, 0.001)
            self.assertEqual(sm.result.config.interventions, iv)
            self.assertIsNot(sm.result.config.interventions, iv)
            self.assertAlmostEqual(sm.max_demand_ratio_pct, max(sm.result.peak_pipe_demand_ratio.values()))
            self.assertLess(sm.mass_balance_error_m3, 1e-8)
        self.assertGreaterEqual(sums[4].max_demand_ratio_pct, sums[0].max_demand_ratio_pct)

    def test_runtime_guard_with_interventions(self) -> None:
        import time
        cfg = self._cfg(interventions={"P3": PipeIntervention("P3", 30.0), "P1": PipeIntervention("P1", 0.0, 12.0)})
        t0 = time.perf_counter()
        for sc in self.dataset.scenarios:
            self.engine.run(SimulationConfig(sc.scenario_id, sc.condition, sc.intensity_mm_h, interventions=cfg.interventions))
        self.assertLess(time.perf_counter() - t0, 3.0)  # Holgado: objetivo real ~0.2 s


if __name__ == "__main__":
    unittest.main()
