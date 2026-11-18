"""Pruebas unitarias de comportamiento y adaptabilidad de la interfaz gráfica."""

import time
import tkinter as tk
import unittest

from src.gui import BicentenarioSewerApp
from src.gui import theme


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

    def test_palette_tokens_and_spanish_presentation(self) -> None:
        self.assertEqual(theme.SHELL_BG.upper(), "#4A4A4A")
        self.assertEqual(theme.DOCK_BG.upper(), "#CBCBCB")
        self.assertEqual(theme.CANVAS_BG.upper(), "#FFFFE3")
        self.assertEqual(theme.ACCENT_PRIMARY.upper(), "#6D8196")
        self.assertEqual(self.app.topbar.cget("bg").upper(), "#4A4A4A")
        self.assertEqual(self.app.left_panel.cget("bg").upper(), "#CBCBCB")
        self.assertEqual(self.app.network_canvas.cget("bg").upper(), "#FFFFE3")

        # Escenarios y selectores en español sin alterar valores internos del motor
        self.assertIn("Lluvia moderada", self.app.var_scenario.get())
        self.app.var_split_rule_es.set("Equitativa")
        self.app.var_hyetograph_es.set("Triangular")
        cfg = self.app._build_sim_config()
        self.assertEqual(cfg.split_rule, "equal")
        self.assertEqual(cfg.hyetograph, "triangular")

    def test_cartographic_surgery_basin_focus_and_traversal_anim(self) -> None:
        # 0. La simulación inicia siempre en el minuto 0
        self.assertEqual(self.app.current_step, 0)
        self.assertAlmostEqual(self.app.result.snapshots[self.app.current_step].time_min, 0.0)

        # 1. Al seleccionar tubería muestra diámetro actual y conserva el menú durante reproducción
        self.app.network_canvas.select_pipe("P31")
        self.app._on_pipe_selected("P31")
        self.assertIn('8"', self.app.lbl_diam_current.cget("text"))
        self.app.var_diam_override.set('16"')
        self.app._action_apply_intervention()
        _pump(self.app, 80)
        self.assertIn('16"', self.app.lbl_diam_current.cget("text"))
        self.assertTrue(bool(self.app.pipe_intervention_card.winfo_ismapped()))

        self.app.toggle_play_pause()
        _pump(self.app, 260)
        self.assertTrue(bool(self.app.pipe_intervention_card.winfo_ismapped()))
        self.assertEqual(self.app._selected_pipe_id, "P31")
        self.app.toggle_play_pause()

        # 2. Cirugía cartográfica: obstrucción 100% en P3 (C -> 31) y perfil longitudinal
        self.app.network_canvas.select_pipe("P3")
        self.app._on_pipe_selected("P3")
        self.app.var_obstruction_pct.set(100.0)
        self.app._action_apply_intervention()
        _pump(self.app, 100)
        self.assertIn("C", self.app._isolated_nodes)
        self.assertIsNotNone(self.app._previous_result)

        self.app.temporal_charts.set_subtab("profile")
        _pump(self.app, 80)
        self.assertEqual(self.app.temporal_charts._subtab, "profile")
        self.app.temporal_charts.set_subtab("hydro")

        self.app._action_restore_all_interventions()
        self.assertEqual(len(self.app._isolated_nodes), 0)
        self.assertEqual(self.app.current_step, 0)

        self.app.network_canvas.select_pipe("P31")
        self.app._on_pipe_selected("P31")
        self.app._action_toggle_basin_isolation()
        self.assertTrue(self.app.network_canvas._basin_active)
        self.assertIn("P31", self.app.network_canvas._basin_pipes)
        self.app._action_toggle_basin_isolation()
        self.assertFalse(self.app.network_canvas._basin_active)

        self.app._last_traversal_alg = "BFS"
        self.app._action_toggle_traversal_anim()
        _pump(self.app, 120)
        self.app._stop_traversal_anim(clear_canvas=True)
        self.app._last_traversal_alg = "DFS"
        self.app._action_toggle_traversal_anim()
        _pump(self.app, 120)
        self.app._stop_traversal_anim(clear_canvas=True)

    def test_scenario_switch_while_paused_and_chart_dpi_fit(self) -> None:
        # Avanzar a t > 0 y mantener pausado
        self.app._set_step(25)
        self.assertFalse(self.app.is_playing)
        self.assertEqual(self.app.result.config.scenario_id, 3)

        # Cambiar de escenario en el selector estando pausado -> actualiza enseguida desde t=0
        vals = list(self.app.combo_scenario["values"])
        self.app.var_scenario.set(vals[4])
        self.app.combo_scenario.event_generate("<<ComboboxSelected>>")
        _pump(self.app, 120)
        self.assertEqual(self.app.result.config.scenario_id, 5)
        self.assertEqual(self.app.current_step, 0)
        self.assertAlmostEqual(self.app.result.snapshots[0].time_min, 0.0)

        # Verificar encaje exacto 1:1 de PhotoImage vs widget sin salto DPI 1.5x al mapear pestañas
        self.app.notebook.select(3)
        _pump(self.app, 220)
        comp_w = self.app.comparison_charts.canvas.get_tk_widget()
        comp_photo = self.app.comparison_charts.canvas._tkphoto
        self.assertEqual(int(round(self.app.comparison_charts.figure.dpi)), self.app._mpl_dpi)
        self.assertEqual(comp_photo.width(), comp_w.winfo_width())
        self.assertEqual(comp_photo.height(), comp_w.winfo_height())

        self.app.notebook.select(2)
        _pump(self.app, 220)
        tmp_w = self.app.temporal_charts.canvas.get_tk_widget()
        tmp_photo = self.app.temporal_charts.canvas._tkphoto
        self.assertEqual(int(round(self.app.temporal_charts.figure.dpi)), self.app._mpl_dpi)
        self.assertEqual(tmp_photo.width(), tmp_w.winfo_width())
        self.assertEqual(tmp_photo.height(), tmp_w.winfo_height())

    def test_guided_tour_source_attribution_and_stress_map_mode(self) -> None:
        # 1. Guía de sustentación: botón visible, 4 hallazgos + enfoque + cierre
        self.assertTrue(bool(self.app.btn_guided_tour.winfo_ismapped()))
        self.app.toggle_guided_tour()
        _pump(self.app, 280)
        self.assertTrue(self.app._tour_active)
        self.assertTrue(bool(self.app._tour_card.winfo_ismapped()))
        self.assertAlmostEqual(self.app.result.snapshots[self.app.current_step].time_min, 5.0)

        for target_min in (25.0, 40.0, 65.0):
            self.app._go_tour_stop(self.app._tour_step + 1)
            _pump(self.app, 260)
            self.assertAlmostEqual(
                self.app.result.snapshots[self.app.current_step].time_min, target_min
            )

        self.app._close_guided_tour()
        _pump(self.app, 240)
        self.assertFalse(self.app._tour_active)
        self.assertFalse(bool(self.app._tour_card.winfo_ismapped()))

        # 2. Trazabilidad por fuente aportante en el inspector
        self.app.notebook.select(0)
        self.app.network_canvas.select_pipe("P31")
        self.app._on_pipe_selected("P31")
        _pump(self.app, 80)
        self.assertTrue(bool(self.app.source_attribution_card.winfo_ismapped()))
        self.assertIn("F17: 100.0%", self.app.lbl_source_breakdown.cget("text"))

        self.app.network_canvas.select_pipe("P25")
        self.app._on_pipe_selected("P25")
        _pump(self.app, 80)
        self.assertGreater(len(self.app._current_source_shares), 1)

        # 3. Modo Mapa de Estrés Acumulado (Instantáneo | Pico Máximo | Minutos en Sobrecarga)
        self.app._set_map_mode("peak")
        _pump(self.app, 80)
        self.assertEqual(self.app.network_canvas._map_mode, "peak")

        self.app._set_map_mode("overload_minutes")
        _pump(self.app, 80)
        self.assertEqual(self.app.network_canvas._map_mode, "overload_minutes")
        self.assertIn("sobrecarga", self.app._legend_header_label.cget("text").lower())

        self.app._set_map_mode("instant")
        _pump(self.app, 60)


if __name__ == "__main__":
    unittest.main()
