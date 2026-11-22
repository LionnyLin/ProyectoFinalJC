"""Pruebas de GUI: modos de mapa, cabecera KPI, leyenda dinámica, pulsos, backtracking y cableado de paneles."""

import os, tkinter as tk, unittest
from unittest.mock import patch

from src.algorithms import OVERLOAD_PERSISTENCE_LEVELS
from src.gui import app as gui_app, theme

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


def _has_display() -> bool:
    try:
        root = tk.Tk(); root.withdraw(); root.destroy()
        return True
    except tk.TclError:
        return False


class TestMapModesAndWiring(unittest.TestCase):
    def setUp(self) -> None:
        if not _has_display():
            self.skipTest("Entorno headless sin display X11 disponible")
        self.app = gui_app.BicentenarioSewerApp(initial_data_path=DATA_XLSX)
        self.app.withdraw(); self.app.update_idletasks()
        self.app._on_player_configure(type("E", (), {"width": 900})())  # anchos fijos: independiente del WM
        self.app._on_map_bar_configure(type("E", (), {"width": 900})())
        self.app.controls.select_scenario_by_id(5)
        self.app.run_simulation()

    def tearDown(self) -> None:
        if hasattr(self, "app"):
            self.app._on_close()

    def _captions(self):
        return [self.app._kpi_captions[k].cget("text") for k in self.app._kpi_keys]

    def _legend_total(self) -> int:
        return sum(int(l.cget("text").rsplit(":", 1)[1]) for _, l in self.app._legend_labels)

    # -- G11 / G10 / G7 -------------------------------------------------------
    def test_mode_selector_buttons_and_labels(self) -> None:
        app = self.app
        self.assertEqual([b.cget("text") for b in app._map_mode_buttons.values()],
                         ["Instantáneo O(t)", "Pico Máximo", "Minutos en Sobrecarga"])
        for width, expected in ((400, ["O(t)", "Pico", "Min >100%"]), (560, ["Instantáneo O(t)", "Pico Máximo", "Min. Sobrecarga"]),
                                (900, ["Instantáneo O(t)", "Pico Máximo", "Minutos en Sobrecarga"])):
            app._on_map_bar_configure(type("E", (), {"width": width})())
            self.assertEqual([b.cget("text") for b in app._map_mode_buttons.values()], expected)

    def test_peak_mode_pauses_updates_kpis_and_legend(self) -> None:
        app = self.app
        app.go_to_step(10); app.toggle_play(); self.assertTrue(app.is_playing)
        app._set_map_mode("peak")
        self.assertFalse(app.is_playing)
        self.assertEqual(app.network_canvas.map_mode, "peak")
        self.assertEqual(app.current_step, 10)
        self.assertEqual(self._captions(), list(theme.MAP_MODE_KPI_CAPTIONS["peak"]))
        peak = app.result.peak_pipe_utilization
        self.assertEqual(app._kpi_cards["max_util"].cget("text"), f"{max(peak.values()):.1f}%")
        self.assertEqual(app._kpi_cards["ptar"].cget("text"), f"{app.result.peak_sink_discharge_m3s:.4f} m³/s")
        self.assertTrue(app._legend_header.cget("text").startswith("Pico máximo · 0–90"))
        self.assertEqual(self._legend_total(), 59)
        self.assertTrue(app._lbl_clock.cget("text").startswith("Pico máximo · 0–90 min"))
        self.assertEqual(str(app._map_mode_buttons["peak"].cget("bg")), theme.ACCENT_PRIMARY)

    def test_overload_mode_levels_and_counts(self) -> None:
        app = self.app
        app._set_map_mode("overload_minutes")
        self.assertEqual(app.network_canvas.map_mode, "overload_minutes")
        self.assertEqual(self._captions(), list(theme.MAP_MODE_KPI_CAPTIONS["overload_minutes"]))
        self.assertEqual(app._legend_header.cget("text"), "Sobrecarga acumulada · 0–90 min")
        self.assertEqual([l.cget("text").split(":")[0] for _, l in app._legend_labels], [r for r, _, _ in OVERLOAD_PERSISTENCE_LEVELS])
        self.assertEqual([str(sw.cget("bg")) for sw in app._legend_swatches], [c for _, c, _ in OVERLOAD_PERSISTENCE_LEVELS])
        self.assertEqual(self._legend_total(), 59)
        ov = app.result.pipe_overloaded_minutes
        self.assertEqual(app._kpi_cards["critical"].cget("text"), str(sum(1 for v in ov.values() if v >= 0.5)))
        self.assertEqual(app._kpi_cards["ptar"].cget("text"), f"{app.result.total_sink_discharge_m3:.1f} m³")
        self.assertTrue(app._lbl_clock.cget("text").startswith("Sobrecarga acumulada · 0–90 min"))
        app._set_map_mode("instant")  # la leyenda recupera la escala oficial
        self.assertEqual([str(sw.cget("bg")) for sw in app._legend_swatches], [c for _, c, _ in theme.COLOR_SCALE_LEGEND])

    def test_instant_header_and_return_restores_step(self) -> None:
        app = self.app
        app.go_to_step(25)
        snap = app.result.snapshots[25]
        self.assertEqual(self._captions(), list(theme.MAP_MODE_KPI_CAPTIONS["instant"]))
        self.assertEqual(app._kpi_cards["critical"].cget("text"), str(len(snap.near_capacity_pipe_ids)))
        self.assertEqual(app._kpi_cards["overloaded"].cget("text"), str(len(snap.overloaded_pipe_ids)))
        self.assertIn("t = 25.0 / 90 min", app._lbl_clock.cget("text"))
        self.assertIn("Escala oficial · t = 25 min", app._legend_header.cget("text"))
        self.assertIn(f"{snap.total_source_inflow_m3s:.4f}", app._lbl_inflow.cget("text"))
        self.assertEqual(self._legend_total(), 59)
        app._set_map_mode("overload_minutes")
        self.assertEqual(app.current_step, 25)
        app._set_map_mode("instant")
        self.assertEqual(app.network_canvas.map_mode, "instant")
        self.assertEqual(app.current_step, 25)
        self.assertIn("t = 25.0 / 90 min", app._lbl_clock.cget("text"))

    def test_navigation_returns_to_instant(self) -> None:
        app = self.app
        actions = {
            "inicio": app._reset_playback, "paso+1": app.step_forward, "paso-1": app.step_backward, "play": app.toggle_play,
            "slider": lambda: app._on_slider_move("7"),
        }
        for name, action in actions.items():
            with self.subTest(name):
                app.go_to_step(12); app.update()
                app._set_map_mode("peak")
                action()
                self.assertEqual(app._map_mode, "instant")
                self.assertEqual(app.network_canvas.map_mode, "instant")
                app._stop_playback()
        app.go_to_step(12); app._set_map_mode("overload_minutes"); app.step_forward()
        self.assertEqual(app.current_step, 13)

    def test_new_simulation_feeds_stress_maps_and_autoplay_resets_mode(self) -> None:
        app = self.app
        app._set_map_mode("peak")
        app.run_simulation()  # re-simulación manual: conserva el modo
        self.assertEqual(app.network_canvas.map_mode, "peak")
        self.assertEqual(app.network_canvas._peak_util, app.result.peak_pipe_utilization)
        self.assertEqual(app.network_canvas._overload_min, app.result.pipe_overloaded_minutes)
        app.run_simulation(auto_play=True)  # Ejecutar simulación: vuelve a instantáneo y reproduce
        self.assertEqual((app._map_mode, app.network_canvas.map_mode, app.is_playing), ("instant", "instant", True))

    # -- Pulsos ---------------------------------------------------------------
    def test_flow_pulses_follow_playback(self) -> None:
        app, cv = self.app, self.app.network_canvas
        app._speed_var.set("10x"); app._on_speed_change()
        app.toggle_play()
        self.assertTrue(cv._playing)
        self.assertGreater(cv._speed_factor, 2.0)
        app._speed_var.set("1x"); app._on_speed_change()
        self.assertAlmostEqual(cv._speed_factor, 1.0)
        app.toggle_play(); self.assertFalse(cv._playing)
        app.toggle_play(); self.assertTrue(cv._playing)
        app._set_map_mode("peak"); self.assertFalse(cv._playing)
        app._ensure_instant(); app.toggle_play(); self.assertTrue(cv._playing)
        app._reset_playback(); self.assertFalse(cv._playing)
        app.toggle_play(); app.go_to_step(len(app.result.snapshots) - 2); app.update()
        for _ in range(3):
            app._play_tick()
        self.assertFalse(app.is_playing); self.assertFalse(cv._playing)
        app.toggle_play(); app._on_close(); self.assertIsNone(cv._pulse_after_id)
        self.app = gui_app.BicentenarioSewerApp(initial_data_path=DATA_XLSX); self.app.withdraw()

    # -- Backtracking DFS -----------------------------------------------------
    def test_dfs_frames_pass_backtracking_to_canvas(self) -> None:
        app = self.app
        captured = []
        orig = app.network_canvas.set_traversal_highlight
        with patch.object(app.network_canvas, "set_traversal_highlight", side_effect=lambda *a, **k: (captured.append(k), orig(*a, **k))[1]):
            app._action_traversal("DFS", "6", None, True)
            app._stop_traversal()
            for i in range(len(app.traversal_frames)):
                app.anim_idx = i; app._render_traversal_frame()
        self.assertTrue(captured)
        self.assertTrue(any(k.get("backtracked_nodes") for k in captured), "DFS debe pasar nodos con backtracking")
        self.assertTrue(any(k.get("active_nodes") for k in captured))
        last = app.traversal_frames[-1]
        self.assertEqual(set(captured[-1]["backtracked_nodes"]), set(last.backtracked_nodes))
        self.assertEqual(set(captured[-1]["active_edges"]), set(last.active_edges))

    # -- Evolución (G17) ------------------------------------------------------
    def test_charts_receive_previous_result_and_step_index(self) -> None:
        app = self.app
        cp = app.charts_panel
        self.assertIsNone(cp._prev)
        self.assertIs(cp._graph, app.dataset.graph)
        app.select_entity("pipe", "P31")
        app._action_apply_intervention(60.0, None)
        self.assertIsNotNone(app.previous_result)
        self.assertIs(cp._prev, app.previous_result)
        self.assertIs(cp._result, app.result)
        self.assertEqual(cp._focus_pipe, "P31")
        app.go_to_step(17)
        self.assertEqual(cp._step_index, 17)
        self.assertAlmostEqual(cp._pending_time, app.result.snapshots[17].time_min)
        app.select_entity("node", "6")
        self.assertEqual((cp._focus_pipe, cp._focus_node), (None, "6"))

    def test_active_route_reaches_profile_and_clears(self) -> None:
        app, cp = self.app, self.app.charts_panel
        app._action_traversal("BFS", "6", "31", False)
        res = app._traversal_result
        self.assertTrue(res.target_reached and res.path_pipes)
        expected = [p.pipe_id for p in res.path_pipes]
        self.assertEqual([e.pipe_id for e in cp._route_override], expected)
        self.assertEqual([e.pipe_id for e in cp._resolve_route()], expected)
        app.select_entity("pipe", "P31")  # la selección no pisa la ruta activa
        self.assertEqual([e.pipe_id for e in cp._resolve_route()], expected)
        app.run_simulation()
        self.assertEqual([e.pipe_id for e in cp._resolve_route()], expected)
        app.clear_traversal()
        self.assertIsNone(cp._route_override)
        self.assertNotEqual([e.pipe_id for e in cp._resolve_route()], expected)
        app._action_trace("6", False)  # una traza sin destino no fija ruta activa
        self.assertIsNone(cp._route_override)

    def test_evolution_tab_title(self) -> None:
        self.assertEqual(self.app.notebook.tab(2, "text"), "Evolución")

    # -- Comparación (G18) ----------------------------------------------------
    def test_comparison_dirty_and_auto_recalc_on_tab(self) -> None:
        app, cmp = self.app, self.app.comparison_panel
        app.notebook.select(3); app.update()
        self.assertIsNotNone(app.cached_comparisons)
        self.assertFalse(cmp.is_dirty)
        app.notebook.select(0); app.update()
        app.controls._param_vars["ingress"].set("50"); app.run_simulation()
        self.assertTrue(cmp.is_dirty); self.assertIsNone(app.cached_comparisons)
        app.notebook.select(3); app.update()
        self.assertFalse(cmp.is_dirty); self.assertIsNotNone(app.cached_comparisons)
        app.notebook.select(0); app.update()
        app.select_entity("pipe", "P31"); app._action_apply_intervention(40.0, None)
        self.assertTrue(cmp.is_dirty)
        # cambiar solo de escenario no invalida (la comparación cubre los 5)
        app.notebook.select(3); app.update()
        app.notebook.select(0); app.update()
        app.controls.select_scenario_by_id(2); app.run_simulation()
        self.assertFalse(cmp.is_dirty)

    def test_report_reuses_comparison_only_when_clean(self) -> None:
        app = self.app
        with patch.object(app, "run_comparison", wraps=app.run_comparison) as rc, \
             patch("tkinter.filedialog.asksaveasfilename", return_value=""):
            app.run_comparison(); rc.reset_mock()
            app._action_export("md"); self.assertEqual(rc.call_count, 0)  # caché vigente
            app._invalidate_comparisons()
            app._action_export("md"); self.assertEqual(rc.call_count, 1)  # recalcula


if __name__ == "__main__":
    unittest.main()
