"""Pruebas de GUI: funciones puras de tema, API de los 7 módulos y smoke test con display."""

import os, tkinter as tk, unittest
from unittest.mock import patch
from src.algorithms.analysis import UTILIZATION_SCALE
from src.gui import app as gui_app, charts_panel, comparison_panel, controls_panel, inspector_panel, network_canvas, theme

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


def _has_display() -> bool:
    try:
        root = tk.Tk(); root.withdraw(); root.destroy()
        return True
    except tk.TclError:
        return False


class TestGuiHeadless(unittest.TestCase):
    """Pruebas puras sin requerir display X11."""

    def test_theme_palette_color_scale_and_translations(self) -> None:
        for c in (theme.PALETTE_GRAPHITE, theme.PALETTE_SILVER, theme.PALETTE_IVORY, theme.PALETTE_SLATE):
            self.assertTrue(c.startswith("#") and len(c) == 7)
        self.assertEqual(len(theme.COLOR_SCALE_LEGEND), 5)
        self.assertEqual([c for _, c, _ in theme.COLOR_SCALE_LEGEND], [c for _, _, c, _ in UTILIZATION_SCALE])
        self.assertTrue(all(c in theme.TIER_TEXT_ON_LIGHT for _, c, _ in theme.COLOR_SCALE_LEGEND))
        self.assertEqual(theme.translate_scenario_name("Dry weather"), "Tiempo seco")
        self.assertEqual(theme.translate_scenario_name("Extreme rain", short=True), "Extrema")
        self.assertEqual(theme.translate_scenario_name("Custom"), "Custom")
        self.assertEqual(theme.format_scenario_label(3, "Moderate rain", 30.0), "Esc. 3: Lluvia moderada (30 mm/h)")
        self.assertTrue(all(theme.SPLIT_RULE_FROM_ES[v] == k for k, v in theme.SPLIT_RULE_TO_ES.items()))
        self.assertTrue(all(theme.SOURCE_DIST_FROM_ES[v] == k for k, v in theme.SOURCE_DIST_TO_ES.items()))

    def test_all_seven_gui_modules_expose_expected_symbols(self) -> None:
        expected = {
            theme: ("COLOR_SCALE_LEGEND", "translate_scenario_name", "format_scenario_label", "resolve_fonts", "apply_ttk_theme"),
            controls_panel: ("ControlsPanel",), inspector_panel: ("InspectorTab", "CriticalPipesTab"),
            charts_panel: ("ChartsPanel",), comparison_panel: ("ComparisonPanel",),
            network_canvas: ("NetworkCanvas",), gui_app: ("BicentenarioSewerApp",),
        }
        for mod, attrs in expected.items():
            for attr in attrs:
                self.assertTrue(hasattr(mod, attr), f"Falta {attr} en {mod.__name__}")
        for m in ("load_data", "run_simulation", "go_to_step", "step_forward", "step_backward",
                  "select_entity", "start_traversal_animation", "step_traversal_animation",
                  "clear_traversal", "run_comparison", "_on_close"):
            self.assertTrue(callable(getattr(gui_app.BicentenarioSewerApp, m, None)), f"Falta {m}")


class TestGuiSmoke(unittest.TestCase):
    """Smoke tests interactivos de BicentenarioSewerApp cuando hay display disponible."""

    def setUp(self) -> None:
        if not _has_display():
            self.skipTest("Entorno headless sin display X11 disponible")
        self.app = gui_app.BicentenarioSewerApp(initial_data_path=DATA_XLSX)
        self.app.withdraw()
        self.app.update_idletasks()

    def tearDown(self) -> None:
        if hasattr(self, "app") and self.app is not None:
            self.app._on_close()

    def test_smoke_simulation_steps_selection_traversal_and_tabs(self) -> None:
        self.assertIsNotNone(self.app.dataset)
        self.assertIsNotNone(self.app.result)
        self.app.controls.select_scenario_by_id(5)
        res = self.app.run_simulation()
        self.assertIsNotNone(res)
        self.assertEqual(res.config.scenario_id, 5)
        self.app.step_forward(); self.assertEqual(self.app.current_step, 1)
        self.app.step_backward(); self.assertEqual(self.app.current_step, 0)
        self.app.select_entity("pipe", "P30")
        self.assertEqual((self.app.selected_kind, self.app.selected_id), ("pipe", "P30"))
        for algo in ("BFS", "DFS"):
            self.app.start_traversal_animation(algo, "6", "31")
            self.assertGreaterEqual(len(self.app.traversal_frames), 3)
            self.app.step_traversal_animation(1); self.assertEqual(self.app.anim_idx, 1)
            self.app.step_traversal_animation(-1); self.assertEqual(self.app.anim_idx, 0)
            self.app.clear_traversal(); self.assertEqual(len(self.app.traversal_frames), 0)
        self.app.run_comparison()
        for idx in range(4):
            self.app.notebook.select(idx); self.app.update()
            self.assertEqual(self.app._active_tab(), idx)

    def test_critical_pipes_treeview_selection_has_no_event_loop(self) -> None:
        """Regresión: seleccionar filas en CriticalPipesTab no debe crear bucle <<TreeviewSelect>>."""
        self.app.notebook.select(1)
        self.app.go_to_step(25)
        self.app.update()
        tree = self.app.critical_tab._tree
        rows = tree.get_children()
        self.assertGreater(len(rows), 3)
        calls = [0]
        orig = self.app.select_entity
        def wrapped(kind, eid):
            calls[0] += 1
            return orig(kind, eid)
        self.app.select_entity = wrapped
        for iid in rows[:3]:
            tree.selection_set(iid)
            self.app.update()
        self.assertEqual(calls[0], 3)

    def test_upstream_and_downstream_are_visually_distinct(self) -> None:
        self.app._action_trace("17", upstream=False)
        self.app.step_traversal_animation(len(self.app.traversal_frames) - 1)
        self.app.update()
        self.assertEqual(self.app.network_canvas._traversal_mode, "downstream")
        self.assertGreater(len(self.app.traversal_frames), 0)
        down_banner = self.app.network_canvas._banner_lbl.cget("text")
        self.assertIn("Aguas abajo", down_banner)
        self.assertTrue(bool(self.app.network_canvas._banner_lbl.place_info()))
        down_edges = [
            iid for iid in self.app.network_canvas.find_all()
            if self.app.network_canvas.type(iid) == "line"
            and self.app.network_canvas.itemcget(iid, "fill") == theme.TRAV_DOWNSTREAM_EDGE
        ]
        self.assertGreater(len(down_edges), 0)
        self.assertTrue(all(self.app.network_canvas.itemcget(iid, "dash") == "" for iid in down_edges))

        self.app._action_trace("31", upstream=True)
        self.app.step_traversal_animation(len(self.app.traversal_frames) - 1)
        self.app.update()
        self.assertEqual(self.app.network_canvas._traversal_mode, "upstream")
        self.assertGreater(len(self.app.traversal_frames), 0)
        up_banner = self.app.network_canvas._banner_lbl.cget("text")
        self.assertIn("Aguas arriba", up_banner)
        self.assertNotEqual(up_banner, down_banner)
        up_edges = [
            iid for iid in self.app.network_canvas.find_all()
            if self.app.network_canvas.type(iid) == "line"
            and self.app.network_canvas.itemcget(iid, "fill") == theme.TRAV_UPSTREAM_EDGE
        ]
        self.assertGreater(len(up_edges), 0)
        self.assertTrue(all(self.app.network_canvas.itemcget(iid, "dash") != "" for iid in up_edges))

        self.app._action_trace("17", upstream=True)
        self.app.update()
        note = self.app.controls._traversal_note.cget("text")
        self.assertTrue(len(note.strip()) > 0)

    def test_critical_pipes_strict_75_to_100_range(self) -> None:
        self.app.controls._scenario_var.set(self.app.controls._scenario_combo["values"][4])
        self.app.run_simulation()
        self.app.update()
        target_step = None
        for idx in range(len(self.app.result.snapshots)):
            snap = self.app.result.snapshots[idx]
            if snap.near_capacity_pipe_ids and snap.overloaded_pipe_ids:
                target_step = idx
                break
        self.assertIsNotNone(target_step)
        self.app.go_to_step(target_step)
        self.app.notebook.select(1)
        self.app.update()

        tab = self.app.critical_tab
        tab._filter_var.set("Críticas (>75–100%)")
        tab.update_view(self.app.dataset.graph, self.app.result.snapshots[target_step])
        self.app.update()
        crit_rows = tab._tree.get_children()
        self.assertGreater(len(crit_rows), 0)
        for iid in crit_rows:
            util_str = str(tab._tree.item(iid, "values")[5]).rstrip("%")
            util_val = float(util_str)
            self.assertGreater(util_val, 75.0)
            self.assertLessEqual(util_val, 100.0)

        tab._filter_var.set("Sobrecargadas (>100%)")
        tab.update_view(self.app.dataset.graph, self.app.result.snapshots[target_step])
        self.app.update()
        over_rows = tab._tree.get_children()
        self.assertGreater(len(over_rows), 0)
        for iid in over_rows:
            util_str = str(tab._tree.item(iid, "values")[5]).rstrip("%")
            self.assertGreater(float(util_str), 100.0)

        snap = self.app.result.snapshots[target_step]
        kpi_crit_text = self.app._kpi_labels["crit"].cget("text")
        self.assertIn(str(len(snap.near_capacity_pipe_ids)), kpi_crit_text)

    def test_search_error_feedback_on_missing_or_empty_entity(self) -> None:
        with patch("tkinter.messagebox.showwarning") as mock_warn:
            self.app._action_search("NO_EXISTE_999")
            self.app.update()
            self.assertEqual(mock_warn.call_count, 1)
            fb_text = self.app.controls._search_feedback.cget("text")
            self.assertIn("NO_EXISTE_999", fb_text)

        self.app.controls._search_var.set("   ")
        self.app.controls._emit_search()
        self.app.update()
        empty_fb = self.app.controls._search_feedback.cget("text")
        self.assertTrue(len(empty_fb.strip()) > 0)

        self.app._action_search("P30")
        self.app.update()
        self.assertEqual((self.app.selected_kind, self.app.selected_id), ("pipe", "P30"))
        ok_fb = self.app.controls._search_feedback.cget("text")
        self.assertIn("P30", ok_fb)

    def test_slider_and_playback_buttons_states(self) -> None:
        self.assertIsInstance(self.app._scale, tk.Scale)
        self.assertEqual(str(self.app._scale.cget("state")), "normal")

        self.app.go_to_step(0)
        self.app.update()
        self.assertEqual(str(self.app._btn_step_back.cget("state")), "disabled")
        self.assertEqual(str(self.app._btn_step_fwd.cget("state")), "normal")
        self.assertEqual(str(self.app._btn_reset.cget("state")), "disabled")

        self.app._on_slider_move("10")
        self.app.update()
        self.assertEqual(self.app.current_step, 10)
        self.assertEqual(str(self.app._btn_step_back.cget("state")), "normal")
        self.assertEqual(str(self.app._btn_reset.cget("state")), "normal")

        self.assertFalse(hasattr(self.app.controls, "_btn_first"))
        self.assertFalse(hasattr(self.app.controls, "_struct_title"))

        self.app._action_traversal("BFS", "17", "31", animate=True)
        self.app.update()
        self.assertGreater(len(self.app.traversal_frames), 0)
        self.assertTrue(bool(self.app.controls._traversal_note.winfo_manager()))
        self.assertTrue(len(self.app.controls._traversal_note.cget("text").strip()) > 0)

        self.app.clear_traversal()
        self.app.update()
        self.assertEqual(len(self.app.traversal_frames), 0)
        self.assertEqual(self.app.controls._traversal_note.winfo_manager(), "")

        self.app.run_simulation(auto_play=True)
        self.assertTrue(self.app.is_playing)
        self.app._stop_playback(False)


if __name__ == "__main__":
    unittest.main()
