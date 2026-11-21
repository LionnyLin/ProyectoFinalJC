"""Pruebas de simulación temporal, Método Racional, balance de masa, reportes y rendimiento."""

import csv, os, tempfile, unittest
from docx import Document
from src.data_structures import LinkedList
from src.io.data_loader import load_dataset
from src.simulation import (
    SewerSimulationEngine, SimulationConfig, compare_all_scenarios,
    generate_docx_report, generate_markdown_report,
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


if __name__ == "__main__":
    unittest.main()
