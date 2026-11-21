"""Pruebas de GUI: funciones puras de tema, API de los 7 módulos y smoke test con display."""

import os, tkinter as tk, unittest
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


if __name__ == "__main__":
    unittest.main()
