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
        self.app.var_source_dist_es.set("Uniforme (1/8)")
        cfg = self.app._build_sim_config()
        self.assertEqual(cfg.split_rule, "equal")
        self.assertEqual(cfg.hyetograph, "triangular")
        self.assertEqual(cfg.source_distribution, "equal")
        self.app.var_source_dist_es.set("Por capacidad")

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

        self.app._set_step(45)
        self.app.var_bfs_start.set("10")
        self.app.var_bfs_target.set("31")
        self.app._last_traversal_alg = "BFS"
        self.app._action_toggle_traversal_anim()
        _pump(self.app, 120)
        # El frame final de ruta debe conservar el color hidráulico de la tubería
        final_fr = self.app._anim_frames[-1]
        self.app.network_canvas.set_traversal_frame(final_fr)
        _pump(self.app, 40)
        for pid in ("P35", "P51"):
            line_id = self.app.network_canvas._pipe_draw_refs[pid][0]
            self.assertNotEqual(
                self.app.network_canvas.itemcget(line_id, "fill"),
                theme.ACCENT_PRIMARY,
            )
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

    def test_left_panel_scroll_clamping_no_blank_gap(self) -> None:
        # 1. En ventana alta (contenido cabe completo), intentar rodar no crea espacio gris superior
        self.app.geometry("1400x1400+10+10")
        _pump(self.app, 180)
        self.assertLessEqual(
            self.app.left_frame.winfo_reqheight(),
            self.app.left_canvas.winfo_height(),
        )
        self.app._scroll_left_canvas(-10)
        self.app.left_canvas.yview_scroll(-5, "units")
        _pump(self.app, 80)
        self.assertAlmostEqual(self.app.left_canvas.canvasy(0), 0.0, places=2)
        self.assertEqual(
            self.app._rail_sim_container.winfo_rooty() - self.app.left_canvas.winfo_rooty(),
            0,
        )

        # 2. En ventana baja (contenido requiere scroll), sí permite bajar y al agrandar vuelve a 0
        self.app.geometry("1200x560+10+10")
        _pump(self.app, 180)
        if self.app.left_frame.winfo_reqheight() > self.app.left_canvas.winfo_height():
            self.app._scroll_left_canvas(4)
            _pump(self.app, 80)
            self.assertGreater(self.app.left_canvas.yview()[0], 0.0)
            self.app.geometry("1400x1400+10+10")
            _pump(self.app, 180)
            self.assertAlmostEqual(self.app.left_canvas.canvasy(0), 0.0, places=2)
            self.assertEqual(self.app.left_canvas.yview(), (0.0, 1.0))

        # 3. Cambiar entre pestañas del panel izquierdo conserva yview en 0
        self.app._switch_rail_tab("trav")
        _pump(self.app, 80)
        self.assertAlmostEqual(self.app.left_canvas.canvasy(0), 0.0, places=2)
        self.app._switch_rail_tab("sim")
        _pump(self.app, 80)
        self.assertAlmostEqual(self.app.left_canvas.canvasy(0), 0.0, places=2)

    def test_guided_tour_per_scenario_and_autoplay_on_execute(self) -> None:
        # 1. Cada escenario tiene su propio recorrido guiado e indica claramente la escena
        vals = list(self.app.combo_scenario["values"])
        self.assertEqual(len(vals), 5)

        self.app.toggle_guided_tour()
        _pump(self.app, 180)
        self.assertTrue(self.app._tour_active)

        seen_titles = set()
        for idx, scen_lbl in enumerate(vals, start=1):
            self.app.var_scenario.set(scen_lbl)
            self.app.combo_scenario.event_generate("<<ComboboxSelected>>")
            _pump(self.app, 180)

            self.assertIn(f"Esc. {idx}", self.app.btn_guided_tour.cget("text"))
            self.assertIn(f"ESC. {idx}", self.app._lbl_tour_hdr.cget("text"))
            self.assertIn(f"Escenario {idx}:", self.app._lbl_tour_scenario.cget("text"))
            stops = self.app._build_tour_stops()
            self.assertEqual(len(stops), 4)
            seen_titles.add(str(stops[1]["title"]))

        # Los 5 escenarios producen hallazgos diferenciados
        self.assertEqual(len(seen_titles), 5)

        # 2. Al presionar "Ejecutar simulación", cierra la guía y reproduce automáticamente
        self.app.var_speed.set("10x")
        self.app.btn_run_sim.invoke()
        _pump(self.app, 180)
        self.assertFalse(self.app._tour_active)
        self.assertTrue(self.app.is_playing)
        self.assertGreater(self.app.current_step, 0)
        self.app._player_pause()

        # 3. Validación robusta ante entradas vacías o fuera de rango en parámetros
        self.app.var_duration.set(0.0)
        with self.assertRaises(ValueError):
            self.app._build_sim_config()
        # _run_param_rerun no debe lanzar excepción si el campo está temporalmente inválido
        self.app._run_param_rerun()
        self.app.var_duration.set(90.0)

    def test_stress_map_modes_frozen_global_and_pause_on_select(self) -> None:
        # 1. Incluso regresando a t = 0 min, Minutos en Sobrecarga muestra totales globales 0–90 min
        self.app._set_step(0)
        self.app._set_map_mode("overload_minutes")
        _pump(self.app, 80)
        expected_p31_ov = self.app.result.pipe_overloaded_minutes.get("P31", 0.0)
        self.assertGreater(expected_p31_ov, 0.0)
        self.assertAlmostEqual(
            self.app.network_canvas._overload_minutes_map.get("P31", 0.0),
            expected_p31_ov,
            places=3,
        )
        self.assertIn("0–90 min", self.app.network_canvas._stamp_lbl.cget("text"))
        self.assertIn("0–90 min", self.app._legend_header_label.cget("text"))
        self.assertIn("0–90", self.app.lbl_clock.cget("text"))
        self.assertEqual(self.app.current_step, 0)

        # 2. En Pico Máximo desde t = 0 muestra el pico global completo y KPI coherente
        self.app._set_map_mode("peak")
        _pump(self.app, 80)
        expected_p30_peak = self.app.result.peak_pipe_utilization.get("P30", 0.0)
        expected_max_peak = max(self.app.result.peak_pipe_utilization.values(), default=0.0)
        self.assertAlmostEqual(
            self.app.network_canvas._peak_util_map.get("P30", 0.0),
            expected_p30_peak,
            places=2,
        )
        self.assertIn("0–90 min", self.app.network_canvas._stamp_lbl.cget("text"))
        self.assertIn("0–90 min", self.app._legend_header_label.cget("text"))
        self.assertEqual(self.app._kpi_cards["max_util"].cget("text"), f"{expected_max_peak:.1f}%")

        # 3. Al reproducir y pulsar Pico Máximo o Minutos en Sobrecarga, pausa automáticamente
        #    y conserva current_step para al regresar a Instantáneo
        self.app.var_speed.set("10x")
        self.app.btn_run_sim.invoke()
        _pump(self.app, 180)
        self.assertEqual(self.app._map_mode, "instant")
        self.assertTrue(self.app.is_playing)
        self.app._set_map_mode("peak")
        _pump(self.app, 80)
        self.assertFalse(self.app.is_playing)
        saved_step = self.app.current_step
        self.assertGreater(saved_step, 0)
        self.assertAlmostEqual(
            self.app.network_canvas._peak_util_map.get("P30", 0.0),
            expected_p30_peak,
            places=2,
        )
        # Regresar a Instantáneo O(t) restaura el instante guardado en el slider
        self.app._set_map_mode("instant")
        _pump(self.app, 60)
        self.assertEqual(self.app.current_step, saved_step)
        self.assertAlmostEqual(
            self.app.network_canvas.snapshot.time_min,
            self.app.result.snapshots[saved_step].time_min,
            places=3,
        )

        # 4. Avanzar paso (+1) o Reproducir desde Minutos en Sobrecarga regresa a Instantáneo
        self.app._set_map_mode("overload_minutes")
        _pump(self.app, 60)
        self.app._player_step(1)
        _pump(self.app, 60)
        self.assertEqual(self.app._map_mode, "instant")
        self.assertEqual(self.app.current_step, min(len(self.app.result.snapshots) - 1, saved_step + 1))

        self.app._set_map_mode("overload_minutes")
        _pump(self.app, 60)
        self.app.toggle_play_pause()
        _pump(self.app, 120)
        self.assertEqual(self.app._map_mode, "instant")
        self.assertTrue(self.app.is_playing)
        self.app._player_pause()

        # En t=40 un redraw completo conserva la etiqueta de P25 y _hide_tooltip limpia _last_hover_key
        self.app._set_step(40)
        self.app.network_canvas.redraw()
        self.assertIn("P25", self.app.network_canvas._pipe_label_refs)
        self.app.network_canvas._last_hover_key = "node:31"
        self.app.network_canvas._hide_tooltip()
        self.assertIsNone(self.app.network_canvas._last_hover_key)

        # Iniciar BFS con Guía de Sustentación activa cierra la guía automáticamente para mostrar la ruta
        self.app.toggle_guided_tour()
        self.assertTrue(self.app._tour_active)
        self.app.var_bfs_start.set("6")
        self.app.var_bfs_target.set("31")
        self.app._run_traversal("BFS")
        self.assertFalse(self.app._tour_active)
        self.assertFalse(self.app.network_canvas._tour_active)
        self.assertIn("31", self.app.network_canvas.highlight_node_ids)

    def test_u1_u2_u3_u4_ui_fixes(self) -> None:
        # U1: toggle Aguas arriba / Aguas abajo solo en el Inspector (segundo clic limpia)
        self.app.network_canvas.select_node("20")
        self.app._on_node_selected("20")
        _pump(self.app, 60)
        self.app.btn_insp_downstream.invoke()
        _pump(self.app, 60)
        self.assertEqual(self.app._inspector_trace_state, ("20", "down"))
        self.assertGreater(len(self.app.network_canvas.highlight_pipe_ids), 0)
        self.app.btn_insp_downstream.invoke()
        _pump(self.app, 60)
        self.assertIsNone(self.app._inspector_trace_state)
        self.assertEqual(len(self.app.network_canvas.highlight_pipe_ids), 0)

        # U3: filtros excluyentes en Tuberías Críticas (>75-100% vs >100% vs <=75%)
        self.app._set_step(30)
        self.app.notebook.select(1)
        _pump(self.app, 80)
        self.app.var_crit_filter.set("critical")
        self.app._refresh_critical_table()
        _pump(self.app, 60)
        for pid in self.app.tree_critical.get_children():
            u_txt = self.app.tree_critical.set(pid, "util").split("%")[0].strip()
            u_val = float(u_txt)
            self.assertGreater(u_val, 75.0)
            self.assertLessEqual(u_val, 100.0)
        self.app.var_crit_filter.set("overloaded")
        self.app._refresh_critical_table()
        _pump(self.app, 60)
        for pid in self.app.tree_critical.get_children():
            u_txt = self.app.tree_critical.set(pid, "util").split("%")[0].strip()
            self.assertGreater(float(u_txt), 100.0)
        self.app.var_crit_filter.set("rest")
        self.app._refresh_critical_table()
        _pump(self.app, 60)
        for pid in self.app.tree_critical.get_children():
            u_txt = self.app.tree_critical.set(pid, "util").split("%")[0].strip()
            self.assertLessEqual(float(u_txt), 75.0)

        # U2: Comparación actualiza timestamp y marca sucio al cambiar parámetros
        self.app.notebook.select(3)
        _pump(self.app, 200)
        self.assertIn("Al día", self.app.lbl_comp_hint.cget("text"))
        self.app.var_ingress_pct.set(2.5)
        self.app._schedule_param_rerun()
        _pump(self.app, 180)
        self.assertIn("Parámetros modificados", self.app.lbl_comp_hint.cget("text"))
        self.app.btn_compare_scenarios.invoke()
        _pump(self.app, 180)
        self.assertIn("Al día", self.app.lbl_comp_hint.cget("text"))
        self.app._apply_preset(100.0, 0.0)
        _pump(self.app, 80)

        # U2 tabla completa + scroll horizontal en Comparación (sin recorte en panel mediano)
        self.app.geometry("1080x680+20+20")
        self.app.notebook.select(3)
        _pump(self.app, 180)
        self.assertTrue(bool(self.app.comp_xscroll.winfo_ismapped()))
        self.assertEqual(
            self.app.tree_comp.item("3", "values")[0],
            "E3 Lluvia moderada",
        )
        self.assertEqual(
            self.app.tree_comp.item("5", "values")[0],
            "E5 Lluvia extrema",
        )
        total_comp_w = sum(
            self.app.tree_comp.column(c, "width") for c in self.app.tree_comp["columns"]
        )
        self.assertGreater(total_comp_w, self.app.tree_comp.winfo_width())
        self.assertLess(self.app.tree_comp.xview()[1], 1.0)

        # U4: _ScenarioMenuButton pausa reproducción al desplegar y reemplaza los 3 selectores de simulación
        self.assertEqual(len(self.app.combo_scenario["values"]), 5)
        for combo_attr in ("combo_split_rule", "combo_hyetograph", "combo_source_dist"):
            widget = getattr(self.app, combo_attr)
            self.assertEqual(widget.winfo_class(), "Menubutton")
            before_txt = widget.cget("text")
            self.assertTrue(bool(before_txt))
            self.app.toggle_play_pause()
            self.assertTrue(self.app.is_playing)
            widget._handle_postcommand()
            self.assertFalse(self.app.is_playing)
            self.assertEqual(widget.cget("text"), before_txt)
        self.app.combo_scenario._handle_postcommand()
        self.assertFalse(self.app.is_playing)

    def test_network_canvas_compact_hidpi_no_node_or_badge_overlap(self) -> None:
        from src.gui.network_canvas import NetworkCanvas

        for width, height, dpi_scale, zoom, expect_all_texts in (
            (652, 378, 1.5, 1.0, True),
            (652, 378, 1.0, 1.0, True),
            (644, 374, 1.5, 0.55, False),
        ):
            canvas = NetworkCanvas(self.app, dpi_scale=dpi_scale, width=width, height=height)
            canvas.place(x=0, y=0, width=width, height=height)
            _pump(self.app, 40)
            canvas.set_graph(self.app.dataset.graph)
            canvas._zoom = zoom
            canvas.redraw()
            _pump(self.app, 40)

            ovals = {}
            node_texts = {}
            ptar_box = None
            fuente_boxes = []
            for iid in canvas.find_all():
                tags = canvas.gettags(iid)
                if "node_layer" not in tags:
                    continue
                nid = canvas._item_to_node.get(iid)
                if not nid:
                    continue
                itype = canvas.type(iid)
                if itype == "oval":
                    bb = canvas.coords(iid)
                    w_o = bb[2] - bb[0]
                    if nid not in ovals or w_o < (ovals[nid][2] - ovals[nid][0]):
                        ovals[nid] = bb
                elif itype == "text":
                    txt = canvas.itemcget(iid, "text")
                    if txt == nid:
                        node_texts[nid] = canvas.bbox(iid)
                    elif "PTAR" in txt:
                        ptar_box = canvas.bbox(iid)
                    elif txt == "Fuente":
                        fuente_boxes.append((nid, canvas.bbox(iid)))

            self.assertEqual(len(ovals), 46)
            if expect_all_texts:
                self.assertEqual(len(node_texts), 46)
            else:
                self.assertLessEqual(len(node_texts), 2)

            # Ningún par de nodos debe solaparse
            nids = list(ovals.keys())
            for i in range(len(nids)):
                a = ovals[nids[i]]
                for j in range(i + 1, len(nids)):
                    b = ovals[nids[j]]
                    overlaps = not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])
                    self.assertFalse(overlaps, f"Nodos solapados {nids[i]}-{nids[j]} en zoom={zoom}")

            # Las etiquetas internas visibles deben caber dentro de su círculo
            for nid, tb in node_texts.items():
                ob = ovals[nid]
                self.assertGreaterEqual(tb[0], ob[0] - 1)
                self.assertLessEqual(tb[2], ob[2] + 1)
                self.assertGreaterEqual(tb[1], ob[1] - 1)
                self.assertLessEqual(tb[3], ob[3] + 1)

            # El cartel PTAR no debe invadir otros nodos ni overlays
            self.assertIsNotNone(ptar_box)
            for nid, ob in ovals.items():
                if nid == "31":
                    continue
                self.assertFalse(
                    not (ptar_box[2] < ob[0] or ptar_box[0] > ob[2] or ptar_box[3] < ob[1] or ptar_box[1] > ob[3])
                )
            for ov_box in canvas._overlay_boxes(width, height):
                for _nid, fb in fuente_boxes:
                    self.assertFalse(
                        not (fb[2] < ov_box[0] or fb[0] > ov_box[2] or fb[3] < ov_box[1] or fb[1] > ov_box[3])
                    )

            canvas.destroy()


if __name__ == "__main__":
    unittest.main()
