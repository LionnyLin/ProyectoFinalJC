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
    compute_fmax_calibrated_ingress,
    estimate_fmax_scenarios,
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
        # En lluvia E3 completa (24.25 m³/s), ampliar P31 (8"->16") multiplica su capacidad conducida (>5x)
        self.assertGreater(int_res.peak_pipe_flow["P31"], base_res.peak_pipe_flow["P31"] * 5.0)
        # Y por debajo del límite de saturación (100% F_max), la ampliación sí reduce su % de utilización
        sub_base = engine.run(
            SimulationConfig(
                scenario_id=0, scenario_name="100% base", intensity_mm_h=0.0,
                duration_min=60.0, storm_duration_min=45.0, target_fmax_pct=100.0,
            )
        )
        sub_int = engine.run(
            SimulationConfig(
                scenario_id=0, scenario_name="100% P31=16", intensity_mm_h=0.0,
                duration_min=60.0, storm_duration_min=45.0, target_fmax_pct=100.0,
                interventions=dict(int_cfg.interventions),
            )
        )
        self.assertLess(sub_int.peak_pipe_utilization["P31"], sub_base.peak_pipe_utilization["P31"])
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
        # Con admisión local en fuentes (tope 120%) y reparto por capacidad, tanto P25 (cuello central) como P31 (fuente) se sobrecargan
        self.assertGreater(mod.pipe_overloaded_minutes["P25"], 20.0)
        self.assertLessEqual(mod.pipe_overloaded_minutes["P25"], 90.0)
        self.assertGreater(mod.pipe_overloaded_minutes["P31"], 20.0)
        self.assertLessEqual(mod.pipe_overloaded_minutes["P31"], 90.0)

        # Con reparto uniforme 1/8, P31 también supera el 100% y acumula minutos de sobrecarga
        mod_eq = engine.run(
            SimulationConfig(
                scenario_id=3,
                scenario_name="Moderate rain",
                intensity_mm_h=30.0,
                duration_min=90.0,
                storm_duration_min=60.0,
                source_distribution="equal",
            )
        )
        self.assertGreater(mod_eq.pipe_overloaded_minutes["P31"], 20.0)

    def test_ford_fulkerson_bounded_utilization_and_surface_flooding(self) -> None:
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        # E2: valores por defecto oficiales -> ingress=1.0, Q_san=0.0; Tiempo seco produce 0 m³
        dry_res = engine.run(
            SimulationConfig(scenario_id=1, scenario_name="Dry weather", intensity_mm_h=0.0)
        )
        self.assertAlmostEqual(dry_res.total_inflow_m3, 0.0, places=9)
        self.assertAlmostEqual(max(dry_res.peak_pipe_utilization.values()), 0.0, places=9)
        self.assertAlmostEqual(dry_res.peak_system_utilization_pct, 0.0, places=9)

        # Meseta del tope 120% en fuentes y sistema en E3 y E5, con rebose de entrada > 0 y pozos <= 4 m³
        for scen_id, scen_name, intensity in [(3, "Moderate rain", 30.0), (5, "Extreme rain", 100.0)]:
            cfg_cap = SimulationConfig(
                scenario_id=scen_id,
                scenario_name=scen_name,
                intensity_mm_h=intensity,
                duration_min=90.0,
                storm_duration_min=60.0,
                source_distribution="capacity",
                max_manhole_storage_m3=4.0,
            )
            res_cap = engine.run(cfg_cap)
            self.assertLess(res_cap.max_mass_balance_error_m3, 1e-6)
            self.assertAlmostEqual(res_cap.system_max_flow_m3s, 0.35914566, places=5)
            self.assertAlmostEqual(res_cap.total_source_capacity_m3s, 0.49522, places=4)
            self.assertAlmostEqual(res_cap.utilization_cap_pct, 120.0, places=6)
            self.assertAlmostEqual(res_cap.peak_system_utilization_pct, 120.0, places=6)
            self.assertAlmostEqual(max(res_cap.peak_pipe_utilization.values()), 120.0, places=6)
            # En Opción A las tuberías fuente (P31, P1, P43) también alcanzan el tope físico 120%
            for src_pid in ("P31", "P1", "P43"):
                self.assertAlmostEqual(res_cap.peak_pipe_utilization[src_pid], 120.0, places=6)
                self.assertIn(src_pid, res_cap.overflow_capped_pipes)
            self.assertEqual(len(res_cap.ever_overloaded_pipes), 18)
            self.assertGreater(res_cap.peak_system_demand_ratio_pct, 120.0)
            self.assertGreater(res_cap.total_inlet_overflow_m3, 0.0)
            self.assertGreater(res_cap.total_surface_flooding_m3, 0.0)
            self.assertLess(res_cap.total_admitted_inflow_m3, res_cap.total_inflow_m3)
            for v_st in res_cap.max_manhole_storage_m3.values():
                self.assertLessEqual(v_st, 4.0 + 1e-9)

        # Compatibilidad: modo opcional system_fmax mantiene recorte global 1.20*F_max (<100% en P31)
        res_sys_mode = engine.run(
            SimulationConfig(
                scenario_id=5,
                scenario_name="Extreme rain system_fmax",
                intensity_mm_h=100.0,
                duration_min=90.0,
                storm_duration_min=60.0,
                source_distribution="capacity",
                admission_mode="system_fmax",
            )
        )
        self.assertLess(res_sys_mode.peak_pipe_utilization["P31"], 100.0)

        # Tope configurable a 135%
        res_135 = engine.run(
            SimulationConfig(
                scenario_id=5,
                scenario_name="Extreme rain 135%",
                intensity_mm_h=100.0,
                duration_min=90.0,
                storm_duration_min=60.0,
                source_distribution="capacity",
                max_physical_utilization_pct=135.0,
            )
        )
        self.assertLess(res_135.max_mass_balance_error_m3, 1e-6)
        self.assertAlmostEqual(res_135.peak_system_utilization_pct, 135.0, places=6)
        self.assertAlmostEqual(max(res_135.peak_pipe_utilization.values()), 135.0, places=6)

        # Comparación equal (1/8) vs capacity al 100% de F_max (equal satura P31 a 120%, capacity ~78%)
        res_eq = engine.run(
            SimulationConfig(
                scenario_id=0,
                scenario_name="100% F_max equal",
                intensity_mm_h=0.0,
                duration_min=90.0,
                storm_duration_min=60.0,
                source_distribution="equal",
                target_fmax_pct=100.0,
            )
        )
        res_cap_100 = engine.run(
            SimulationConfig(
                scenario_id=0,
                scenario_name="100% F_max cap",
                intensity_mm_h=0.0,
                duration_min=90.0,
                storm_duration_min=60.0,
                source_distribution="capacity",
                target_fmax_pct=100.0,
            )
        )
        self.assertLess(res_eq.max_mass_balance_error_m3, 1e-6)
        self.assertGreater(
            res_eq.peak_pipe_utilization["P31"],
            res_cap_100.peak_pipe_utilization["P31"],
        )

    def test_fmax_estimator_plateau_and_calibration(self) -> None:
        base_cfg = SimulationConfig(
            scenario_id=0,
            scenario_name="Estimador",
            intensity_mm_h=0.0,
            duration_min=90.0,
            storm_duration_min=60.0,
        )
        ff_res, rows = estimate_fmax_scenarios(self.dataset, base_cfg)
        self.assertAlmostEqual(ff_res.max_flow_m3s, 0.35914566, places=5)
        by_pct = {round(r.target_fmax_pct): r for r in rows}
        self.assertIn(0, by_pct)
        self.assertIn(100, by_pct)
        self.assertIn(120, by_pct)
        self.assertIn(150, by_pct)
        self.assertIn(200, by_pct)

        self.assertAlmostEqual(by_pct[0].system_utilization_pct, 0.0, places=6)
        self.assertAlmostEqual(by_pct[100].system_utilization_pct, 100.0, places=6)
        # Meseta constante del uso (120%) y progresión de saturación en fuentes hasta tope local 1.20*Qmax_fuentes
        for pct in (120, 150, 200):
            self.assertAlmostEqual(by_pct[pct].system_utilization_pct, 120.0, places=6)
            self.assertAlmostEqual(by_pct[pct].max_pipe_utilization_pct, 120.0, places=6)
            self.assertTrue(by_pct[pct].is_overflow_capped)

        self.assertAlmostEqual(by_pct[120].admitted_flow_m3s, 1.20 * ff_res.max_flow_m3s, places=4)
        self.assertAlmostEqual(by_pct[150].admitted_flow_m3s, 1.50 * ff_res.max_flow_m3s, places=4)
        self.assertAlmostEqual(by_pct[150].result.peak_pipe_utilization["P31"], 120.0, places=4)
        self.assertEqual(by_pct[150].num_overloaded_pipes, 18)
        self.assertAlmostEqual(
            by_pct[200].admitted_flow_m3s,
            1.20 * by_pct[200].result.total_source_capacity_m3s,
            places=4,
        )
        self.assertGreater(by_pct[200].inlet_overflow_rate_m3s, 0.0)
        self.assertGreater(by_pct[150].total_surface_flooding_m3, by_pct[120].total_surface_flooding_m3)
        self.assertGreater(by_pct[200].total_surface_flooding_m3, by_pct[150].total_surface_flooding_m3)

        # Factor de ingreso calibrado para que 30 mm/h corresponda al 100% de F_max
        f_cal = compute_fmax_calibrated_ingress(
            ff_res.max_flow_m3s,
            self.dataset.basin.runoff_coefficient_c,
            self.dataset.basin.area_ha,
            reference_intensity_mm_h=30.0,
        )
        self.assertGreater(f_cal, 0.01)
        self.assertLess(f_cal, 0.05)
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        res_cal = engine.run(
            SimulationConfig(
                scenario_id=3,
                scenario_name="E3 Calibrado",
                intensity_mm_h=30.0,
                ingress_factor=f_cal,
                duration_min=90.0,
                storm_duration_min=60.0,
            )
        )
        self.assertAlmostEqual(res_cal.peak_system_utilization_pct, 100.0, places=2)
        self.assertAlmostEqual(res_cal.total_inlet_overflow_m3, 0.0, places=6)

    def test_e3_transit_delay_dt_invariance_and_e4_flow_coherence(self) -> None:
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        # E3: llegada mínima física a PTAR 31 es 8.7529 min (27->C->31); nunca debe llegar antes
        sinks = []
        for dt in (0.5, 1.0, 2.0, 5.0):
            res = engine.run(
                SimulationConfig(
                    scenario_id=3,
                    scenario_name="Moderate rain",
                    intensity_mm_h=30.0,
                    duration_min=90.0,
                    storm_duration_min=60.0,
                    dt_min=dt,
                    ingress_factor=0.025,
                    dry_weather_flow_per_source_m3s=0.003,
                )
            )
            first_arr = next(
                (s.time_min for s in res.snapshots if s.total_sink_discharge_m3s > 1e-9),
                999.0,
            )
            self.assertGreaterEqual(first_arr, 8.75)
            sinks.append(res.total_sink_discharge_m3)
        # Invarianza ante dt (dispersión < 0.2%)
        self.assertLess(max(sinks) - min(sinks), 1.0)

        # E4: coherencia estricta node.outflow_m3s == sum(pipe.flow_m3s) en todos los pasos
        res_e3 = engine.run(
            SimulationConfig(scenario_id=3, scenario_name="Moderate rain", intensity_mm_h=30.0)
        )
        for snap in res_e3.snapshots:
            for nid, nst in snap.node_states.items():
                outs = self.dataset.graph.outgoing_pipes(nid)
                if outs:
                    pipe_sum = sum(snap.pipe_states[e.pipe_id].flow_m3s for e in outs)
                    self.assertAlmostEqual(nst.outflow_m3s, pipe_sum, places=8)

    def test_m1_m2_m3_m8_regressions(self) -> None:
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        # M2: lluvia uniforme con storm=1, dt=3 debe inyectar volumen completo, y duration=10, dt=3 termina en 10.0 min
        unif = engine.run(
            SimulationConfig(
                scenario_id=3,
                scenario_name="Uniforme",
                intensity_mm_h=30.0,
                duration_min=10.0,
                storm_duration_min=1.0,
                dt_min=3.0,
            )
        )
        expected_in = 0.00278 * 0.75 * 30.0 * 388.0 * 60.0
        self.assertAlmostEqual(unif.total_inflow_m3, expected_in, delta=1e-3)
        self.assertAlmostEqual(unif.snapshots[-1].time_min, 10.0, places=6)

        # M3 + M8: tubería cerrada al 100% reporta 0% y is_closed=True; source_distribution="capacity" responde
        _q_base, inflows_base = engine.compute_source_inflows_by_source(
            SimulationConfig(scenario_id=3, scenario_name="Mod", intensity_mm_h=30.0), 10.0
        )
        cfg_closed = SimulationConfig(
            scenario_id=3,
            scenario_name="Mod",
            intensity_mm_h=30.0,
            interventions={"P31": PipeIntervention("P31", obstruction_pct=100.0)},
        )
        _q_closed, inflows_closed = engine.compute_source_inflows_by_source(cfg_closed, 10.0)
        self.assertAlmostEqual(inflows_closed["17"], 0.0, places=9)
        self.assertGreater(inflows_base["17"], 0.0)
        res_closed = engine.run(cfg_closed)
        self.assertAlmostEqual(res_closed.peak_pipe_utilization["P31"], 0.0, places=9)
        self.assertTrue(res_closed.snapshots[1].pipe_states["P31"].is_closed)


if __name__ == "__main__":
    unittest.main()
