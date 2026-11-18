"""Pruebas unitarias de comportamiento y adaptabilidad de la interfaz gráfica."""

import time
import tkinter as tk
import unittest

from src.gui import BicentenarioSewerApp


def _pump(app: tk.Tk, ms: int = 120) -> None:
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.015)


class TestGuiResponsiveAndBehavior(unittest.TestCase):
    """Verifica el comportamiento funcional y la adaptación a distintos tamaños de ventana."""

    def setUp(self) -> None:
        self.app = BicentenarioSewerApp()
        _pump(self.app, 180)

    def tearDown(self) -> None:
        try:
            self.app._on_close()
        except tk.TclError:
            pass

    def test_responsive_breakpoints_and_panel_exclusivity_in_compact(self) -> None:
        # Ventana amplia
        self.app.geometry("1400x860+20+20")
        _pump(self.app, 180)
        self.assertEqual(self.app._layout_tier, "wide")
        self.assertEqual(self.app._topbar_mode, "wide")
        self.assertTrue(self.app._show_left)
        self.assertTrue(self.app._show_right)

        # Ventana mediana
        self.app.geometry("1080x680+20+20")
        _pump(self.app, 180)
        self.assertEqual(self.app._layout_tier, "medium")
        self.assertEqual(self.app._topbar_mode, "medium")

        # Ventana compacta: alternancia exclusiva entre Parámetros y Análisis
        self.app.geometry("840x580+20+20")
        _pump(self.app, 180)
        self.assertEqual(self.app._layout_tier, "compact")
        self.assertEqual(self.app._topbar_mode, "compact")
        self.assertFalse(self.app._show_left and self.app._show_right)

        self.app.toggle_right_panel()
        _pump(self.app, 140)
        self.assertTrue(self.app._show_right)
        self.assertFalse(self.app._show_left)

        self.app.toggle_left_panel()
        _pump(self.app, 140)
        self.assertTrue(self.app._show_left)
        self.assertFalse(self.app._show_right)

    def test_traversals_upstream_downstream_and_search(self) -> None:
        self.app.var_bfs_start.set("6")
        self.app.var_bfs_target.set("31")
        self.app._run_traversal("BFS")
        self.assertTrue(len(self.app.network_canvas.highlight_pipe_ids) > 0)
        self.assertIn("31", self.app.network_canvas.highlight_node_ids)

        self.app.var_bfs_start.set("31")
        self.app._run_trace("up")
        self.assertEqual(len(self.app.network_canvas.highlight_node_ids), 46)

        self.app.var_search.set("P31")
        self.app._action_search()
        self.assertEqual(self.app._selected_pipe_id, "P31")

    def test_playback_step_and_critical_selection_persistence(self) -> None:
        self.app.notebook.select(1)
        self.app._on_pipe_selected("P31")
        self.app.network_canvas.select_pipe("P31")
        self.app._player_step(1)
        _pump(self.app, 80)
        self.assertEqual(self.app.tree_critical.selection(), ("P31",))

        self.app.toggle_play_pause()
        self.assertTrue(self.app.is_playing)
        _pump(self.app, 120)
        self.app.toggle_play_pause()
        self.assertFalse(self.app.is_playing)

    def test_auto_comparison_on_tab_switch(self) -> None:
        self.assertEqual(len(self.app.comparisons), 0)
        self.app.notebook.select(3)
        _pump(self.app, 200)
        self.assertEqual(len(self.app.comparisons), 5)
        self.assertEqual(len(self.app.tree_comp.get_children()), 5)


if __name__ == "__main__":
    unittest.main()
