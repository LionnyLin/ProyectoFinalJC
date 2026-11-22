"""Pruebas del recorrido guiado (G12): ficha flotante, paradas por escenario, foco, cierre y Esc."""

import os, tkinter as tk, unittest

from src.gui import app as gui_app

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


def _has_display() -> bool:
    try:
        root = tk.Tk(); root.withdraw(); root.destroy()
        return True
    except tk.TclError:
        return False


class TestGuidedTour(unittest.TestCase):
    def setUp(self) -> None:
        if not _has_display():
            self.skipTest("Entorno headless sin display X11 disponible")
        self.app = gui_app.BicentenarioSewerApp(initial_data_path=DATA_XLSX)
        self.app.withdraw(); self.app.update_idletasks()
        self.app.controls.select_scenario_by_id(5)
        self.app.run_simulation()

    def tearDown(self) -> None:
        if hasattr(self, "app"):
            self.app._on_close()

    def _time(self) -> float:
        return self.app.result.snapshots[self.app.current_step].time_min

    def _stops_for(self, sid: int):
        self.app.controls.select_scenario_by_id(sid)
        self.app.run_simulation()
        return self.app.tour.build_stops()

    def test_open_shows_card_and_goes_to_first_stop(self) -> None:
        app, tour = self.app, self.app.tour
        app.toggle_play(); self.assertTrue(app.is_playing)
        app.btn_guided_tour.invoke()
        self.assertTrue(tour.active)
        self.assertFalse(app.is_playing)
        self.assertTrue(tour.card.winfo_manager())
        self.assertAlmostEqual(self._time(), 5.0)
        self.assertEqual(tour.lbl_count.cget("text"), "1 / 4")
        cv = app.network_canvas
        self.assertTrue(cv._tour_active)
        self.assertEqual(cv._tour_nodes, set(app.dataset.graph.source_ids()))
        self.assertEqual(str(tour.btn_prev.cget("state")), "disabled")

    def test_next_previous_navigation_and_counter(self) -> None:
        app, tour = self.app, self.app.tour
        tour.toggle()
        expected = [s.target_min for s in tour.stops]
        for i in (1, 2, 3):
            tour.btn_next.invoke()
            self.assertEqual(tour.step, i)
            self.assertEqual(tour.lbl_count.cget("text"), f"{i + 1} / 4")
            self.assertAlmostEqual(self._time(), expected[i])
            self.assertEqual(app.network_canvas._tour_pipes, tour.stops[i].pipes)
        self.assertEqual(tour.btn_next.cget("text"), "Finalizar")
        tour.btn_prev.invoke()
        self.assertEqual(tour.step, 2)
        self.assertEqual(tour.lbl_count.cget("text"), "3 / 4")
        tour.go_to(3); tour.btn_next.invoke()  # Finalizar cierra
        self.assertFalse(tour.active)

    def test_stops_differ_per_scenario_and_metrics_come_from_result(self) -> None:
        s1, s5 = self._stops_for(1), self._stops_for(5)
        self.assertEqual((len(s1), len(s5)), (4, 4))
        self.assertNotEqual([s.title for s in s1], [s.title for s in s5])
        self.assertNotEqual(s1[1].desc, s5[1].desc)
        res = self.app.result
        snap = res.snapshots[s5[3].step_idx]
        self.assertIn(f"{snap.total_sink_discharge_m3s:.4f}", s5[3].metrics)
        self.assertIn(f"{res.max_mass_balance_error_m3:.1e}", s5[3].metrics)
        s1_snap = res.snapshots[s5[0].step_idx]
        self.assertIn(f"{s1_snap.total_source_inflow_m3s:.4f}", s5[0].metrics)
        self.assertTrue({"P25", "P3"} <= s5[2].pipes)
        # El escenario 1 (tiempo seco) no genera caudal en las fuentes
        self.app.controls.select_scenario_by_id(1); self.app.run_simulation()
        self.assertIn("0.0000", self.app.tour.build_stops()[0].metrics)

    def test_close_button_and_escape_clear_focus_and_hide_card(self) -> None:
        app, tour = self.app, self.app.tour
        tour.toggle(); tour.go_to(1)
        tour.close()
        self.assertFalse(tour.active); self.assertFalse(tour.card.winfo_manager())
        self.assertFalse(app.network_canvas._tour_active)
        tour.toggle(); self.assertTrue(tour.active)
        app._shortcut_escape(None)
        self.assertFalse(tour.active); self.assertFalse(tour.card.winfo_manager())
        self.assertFalse(app.network_canvas._tour_active)

    def test_scenario_change_with_tour_open_recomputes_stops(self) -> None:
        app, tour = self.app, self.app.tour
        app._layout_tier = "compact"  # etiqueta compacta independiente del WM
        tour.toggle(); tour.go_to(2)
        old_title = tour.stops[2].title
        app.controls.select_scenario_by_id(2)
        app.run_simulation()
        self.assertTrue(tour.active)
        self.assertEqual(tour.step, 0)
        self.assertIn("Escenario 2:", tour.lbl_scenario.cget("text"))
        self.assertIn("ESC. 2", tour.lbl_hdr.cget("text"))
        self.assertNotEqual(tour.stops[2].title, old_title)
        self.assertIn("Esc. 2", app.btn_guided_tour.cget("text"))
        self.assertTrue(app.network_canvas._tour_active)
        self.assertAlmostEqual(self._time(), 5.0)

    def test_run_with_autoplay_closes_tour_consistently(self) -> None:
        app, tour = self.app, self.app.tour
        tour.toggle()
        app.run_simulation(auto_play=True)
        self.assertFalse(tour.active); self.assertFalse(tour.card.winfo_manager())
        self.assertFalse(app.network_canvas._tour_active)
        self.assertTrue(app.is_playing)
        app._stop_playback()

    def test_button_label_compact_and_wide(self) -> None:
        app = self.app
        app._layout_topbar("compact", False)
        self.assertEqual(app.btn_guided_tour.cget("text"), "Guía Esc. 5")
        app._layout_topbar("medium", False)
        self.assertEqual(app.btn_guided_tour.cget("text"), "Guía Esc. 5")
        app._layout_topbar("wide", True)
        self.assertEqual(app.btn_guided_tour.cget("text"), "Recorrido guiado")
        self.assertTrue(app.btn_guided_tour.winfo_manager())

    def test_map_mode_change_and_play_close_tour(self) -> None:
        app, tour = self.app, self.app.tour
        tour.toggle(); app._set_map_mode("peak")
        self.assertFalse(tour.active); self.assertFalse(app.network_canvas._tour_active)
        app._set_map_mode("instant")
        tour.toggle(); app.toggle_play()
        self.assertFalse(tour.active)
        app._stop_playback()


if __name__ == "__main__":
    unittest.main()
