"""Pruebas unitarias de simulación temporal, sobrecarga, balance de masa y consistencia."""

import os
import tempfile
import unittest

from src.io.data_loader import load_dataset
from src.simulation import (
    PipeIntervention,
    SewerSimulationEngine,
    SimulationConfig,
    compare_all_scenarios,
    generate_markdown_report,
)


DATA_XLSX = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx")
)


class TestSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset(DATA_XLSX)

    def test_transit_delay_water_does_not_teleport(self) -> None:
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        cfg = SimulationConfig(
            scenario_id=2,
            scenario_name="Light rain",
            intensity_mm_h=10.0,
            duration_min=60.0,
            storm_duration_min=45.0,
            dt_min=1.0,
        )
        res = engine.run(cfg)
        # En t=1 min, la tubería final P30 (29 -> 31) aún no debe recibir agua
        snap_t1 = res.snapshots[1]
        self.assertAlmostEqual(snap_t1.pipe_states["P30"].flow_m3s, 0.0, places=9)
        self.assertAlmostEqual(snap_t1.total_sink_discharge_m3s, 0.0, places=9)
        # Al final de la simulación, el agua sí debe haber llegado a la PTAR (nodo 31)
        self.assertGreater(res.total_sink_discharge_m3, 0.0)

    def test_mass_conservation_and_overload_storage(self) -> None:
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        # Lluvia extrema 100 mm/h con 100% racional durante 20 min, luego drenaje hasta 120 min
        cfg = SimulationConfig(
            scenario_id=5,
            scenario_name="Extreme rain",
            intensity_mm_h=100.0,
            duration_min=120.0,
            storm_duration_min=20.0,
            dt_min=1.0,
            ingress_factor=1.0,
            dry_weather_flow_per_source_m3s=0.0,
        )
        res = engine.run(cfg)
        self.assertGreater(len(res.ever_overloaded_pipes), 0)
        self.assertGreater(sum(res.max_manhole_storage_m3.values()), 0.0)
        # Conservación exacta de masa en todos los pasos
        self.assertLess(res.max_mass_balance_error_m3, 1e-6)

        # Verificar orden de magnitud del Método Racional: Q = 0.00278 * 0.75 * 100 * 388 = 80.898 m³/s
        expected_total_inflow = 0.00278 * 0.75 * 100.0 * 388.0 * (20.0 * 60.0)
        self.assertAlmostEqual(res.total_inflow_m3, expected_total_inflow, delta=1e-3)

    def test_repeatability_and_linked_list_history(self) -> None:
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        cfg = SimulationConfig(
            scenario_id=3,
            scenario_name="Moderate rain",
            intensity_mm_h=30.0,
            duration_min=45.0,
            storm_duration_min=30.0,
            dt_min=1.0,
        )
        res1 = engine.run(cfg)
        hist_len = len(engine.history)
        res2 = engine.run(cfg)

        self.assertEqual(hist_len, len(res1.snapshots))
        self.assertEqual(len(res1.snapshots), len(res2.snapshots))
        for s1, s2 in zip(res1.snapshots, res2.snapshots):
            self.assertAlmostEqual(s1.total_sink_discharge_m3s, s2.total_sink_discharge_m3s, places=12)
            self.assertAlmostEqual(s1.total_manhole_storage_m3, s2.total_manhole_storage_m3, places=12)

    def test_all_scenarios_comparison_and_report(self) -> None:
        base_cfg = SimulationConfig(
            scenario_id=1,
            scenario_name="Dry weather",
            intensity_mm_h=0.0,
            duration_min=60.0,
            storm_duration_min=45.0,
            dt_min=1.0,
        )
        summaries = compare_all_scenarios(self.dataset, base_cfg)
        self.assertEqual(len(summaries), 5)
        for s in summaries:
            self.assertLess(s.mass_balance_error_m3, 1e-6)
        # Escenario 5 debe tener mayor utilización máxima que Escenario 1
        self.assertGreater(summaries[4].max_utilization_pct, summaries[0].max_utilization_pct)

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = os.path.join(tmpdir, "reporte.md")
            out = generate_markdown_report(self.dataset, summaries[2].result, summaries, report_path)
            self.assertTrue(os.path.isfile(out))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "reporte_tuberias.csv")))

    def test_live_pipe_interventions_and_validation(self) -> None:
        with self.assertRaises(ValueError):
            PipeIntervention("P3", obstruction_pct=120.0)
        with self.assertRaises(ValueError):
            PipeIntervention("P3", diameter_in_override=0.0)

        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        base_cfg = SimulationConfig(
            scenario_id=3,
            scenario_name="Moderate rain",
            intensity_mm_h=30.0,
            duration_min=60.0,
            storm_duration_min=45.0,
        )
        base_res = engine.run(base_cfg)

        # Cierre al 100% de P3 (C -> 31) y ampliación de P31 (8" -> 16")
        int_cfg = SimulationConfig(
            scenario_id=3,
            scenario_name="Moderate rain",
            intensity_mm_h=30.0,
            duration_min=60.0,
            storm_duration_min=45.0,
            interventions={
                "P3": PipeIntervention("P3", obstruction_pct=100.0),
                "P31": PipeIntervention("P31", obstruction_pct=0.0, diameter_in_override=16.0),
            },
        )
        int_res = engine.run(int_cfg)
        self.assertLess(int_res.max_mass_balance_error_m3, 1e-6)
        self.assertGreater(int_res.max_manhole_storage_m3["C"], 0.0)
        self.assertLess(int_res.peak_pipe_utilization["P31"], base_res.peak_pipe_utilization["P31"])
        self.assertAlmostEqual(self.dataset.graph.get_pipe("P31").diameter_in, 8.0, places=6)

    def test_overloaded_minutes_memory(self) -> None:
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        dry = engine.run(
            SimulationConfig(
                scenario_id=1,
                scenario_name="Dry weather",
                intensity_mm_h=0.0,
                duration_min=90.0,
                storm_duration_min=60.0,
            )
        )
        self.assertEqual(sum(dry.pipe_overloaded_minutes.values()), 0.0)

        mod = engine.run(
            SimulationConfig(
                scenario_id=3,
                scenario_name="Moderate rain",
                intensity_mm_h=30.0,
                duration_min=90.0,
                storm_duration_min=60.0,
            )
        )
        self.assertGreater(mod.pipe_overloaded_minutes["P31"], 20.0)
        self.assertLessEqual(mod.pipe_overloaded_minutes["P31"], 90.0)

    def test_physical_utilization_cap_demand_separation_and_surface_flooding(self) -> None:
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        # Escenario extremo: utilización física acotada <= 115%, demanda > 200%, pozos <= 4 m³ y rebose > 0
        cfg_cap = SimulationConfig(
            scenario_id=5,
            scenario_name="Extreme rain",
            intensity_mm_h=100.0,
            duration_min=90.0,
            storm_duration_min=60.0,
            source_distribution="capacity",
            max_manhole_storage_m3=4.0,
            max_physical_utilization_pct=115.0,
        )
        res_cap = engine.run(cfg_cap)
        self.assertLess(res_cap.max_mass_balance_error_m3, 1e-6)
        self.assertLessEqual(max(res_cap.peak_pipe_utilization.values()), 115.0 + 1e-9)
        self.assertGreater(max(res_cap.peak_pipe_demand_ratio.values()), 300.0)
        self.assertGreater(res_cap.total_surface_flooding_m3, 0.0)
        for v_st in res_cap.max_manhole_storage_m3.values():
            self.assertLessEqual(v_st, 4.0 + 1e-9)

        # Comparación con reparto uniforme 1/8
        cfg_eq = SimulationConfig(
            scenario_id=5,
            scenario_name="Extreme rain",
            intensity_mm_h=100.0,
            duration_min=90.0,
            storm_duration_min=60.0,
            source_distribution="equal",
        )
        res_eq = engine.run(cfg_eq)
        self.assertLess(res_eq.max_mass_balance_error_m3, 1e-6)
        self.assertLessEqual(max(res_eq.peak_pipe_utilization.values()), 115.0 + 1e-9)
        self.assertGreater(
            res_eq.peak_pipe_demand_ratio["P31"],
            res_cap.peak_pipe_demand_ratio["P31"],
        )


if __name__ == "__main__":
    unittest.main()
