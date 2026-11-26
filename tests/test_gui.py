"""Pruebas unitarias de comportamiento, paleta y adaptabilidad de la interfaz PySide6."""

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication

from src.gui import BicentenarioSewerApp, ensure_qapplication, theme
from src.gui.canvas import NetworkCanvas
from src.gui.panels import build_tour_stops


def _pump(ms: int = 120) -> None:
    qapp = QApplication.instance()
    if qapp is None:
        return
    end = time.time() + ms / 1000.0
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.015)


def _wait_tasks(app: BicentenarioSewerApp, timeout_ms: int = 8000) -> None:
    ok = app.wait_for_background_tasks(timeout_ms)
    if not ok:
        raise AssertionError("Tiempo agotado esperando tareas en segundo plano")
    _pump(80)


class TestGuiResponsiveAndBehavior(unittest.TestCase):
    """Verifica comportamiento funcional, paleta, composición modular y responsividad."""

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapplication()

    def setUp(self) -> None:
        self.app = BicentenarioSewerApp()
        self.app.show()
        _pump(180)

    def tearDown(self) -> None:
        self.app.wait_for_background_tasks(3000)
        self.app.close()
        _pump(40)
        self.app.deleteLater()
        _pump(20)

    def test_responsive_breakpoints_and_panel_exclusivity_in_compact(self) -> None:
        # Ventana amplia
        self.app.resize(1400, 860)
        _pump(180)
        self.assertEqual(self.app.state.layout_tier, "wide")
        self.assertEqual(self.app.state.topbar_mode, "wide")
        self.assertTrue(self.app.state.show_left)
        self.assertTrue(self.app.state.show_right)
        self.assertTrue(self.app.controls_panel.isVisible())
        self.assertTrue(self.app.right_panel.isVisible())

        # Ventana mediana
        self.app.resize(1080, 680)
        _pump(180)
        self.assertEqual(self.app.state.layout_tier, "medium")
        self.assertEqual(self.app.state.topbar_mode, "medium")

        # Ventana compacta: alternancia exclusiva entre Controles y Análisis
        self.app.resize(840, 580)
        _pump(180)
        self.assertEqual(self.app.state.layout_tier, "compact")
        self.assertEqual(self.app.state.topbar_mode, "compact")
        self.assertFalse(self.app.state.show_left and self.app.state.show_right)

        self.app.toggle_right_panel()
        _pump(140)
        self.assertTrue(self.app.state.show_right)
        self.assertFalse(self.app.state.show_left)

        self.app.toggle_left_panel()
        _pump(140)
        self.assertTrue(self.app.state.show_left)
        self.assertFalse(self.app.state.show_right)

    def test_traversals_upstream_downstream_and_search(self) -> None:
        self.app.controls_panel.combo_bfs_start.setCurrentText("6")
        self.app.controls_panel.combo_bfs_target.setCurrentText("31")
        self.app._run_traversal("BFS")
        self.assertTrue(len(self.app.network_canvas.highlight_pipe_ids) > 0)
        self.assertIn("31", self.app.network_canvas.highlight_node_ids)

        self.app.controls_panel.combo_bfs_start.setCurrentText("31")
        self.app._run_trace("up")
        self.assertEqual(len(self.app.network_canvas.highlight_node_ids), 46)

        self.app.controls_panel.entry_search.setText("P31")
        self.app._action_search("P31")
        self.assertEqual(self.app.state.selected_pipe_id, "P31")

    def test_playback_step_and_critical_selection_persistence(self) -> None:
        self.app.right_tabs.setCurrentIndex(1)
        self.app._on_pipe_selected("P31")
        self.app.network_canvas.select_pipe("P31")
        self.app._player_step(1)
        _pump(80)
        self.assertEqual(self.app.critical_panel.selected_pipe_id(), "P31")

        self.app.toggle_play_pause()
        self.assertTrue(self.app.state.is_playing)
        _pump(120)
        self.app.toggle_play_pause()
        self.assertFalse(self.app.state.is_playing)

    def test_auto_comparison_on_tab_switch(self) -> None:
        self.assertEqual(len(self.app.state.comparisons), 0)
        self.app.right_tabs.setCurrentIndex(3)
        _wait_tasks(self.app)
        self.assertEqual(len(self.app.state.comparisons), 5)
        self.assertEqual(self.app.comparison_panel.table.rowCount(), 5)

    def test_palette_tokens_and_spanish_presentation(self) -> None:
        self.assertEqual(theme.SHELL_BG.upper(), "#4A4A4A")
        self.assertEqual(theme.DOCK_BG.upper(), "#CBCBCB")
        self.assertEqual(theme.CANVAS_BG.upper(), "#FFFFE3")
        self.assertEqual(theme.ACCENT_PRIMARY.upper(), "#6D8196")

        # Verifica colores realmente renderizados en la GUI Qt
        top_img = self.app.top_bar.grab().toImage()
        self.assertEqual(top_img.pixelColor(4, 4).name().upper(), "#4A4A4A")

        left_img = self.app.controls_panel.grab().toImage()
        self.assertEqual(left_img.pixelColor(2, 2).name().upper(), "#CBCBCB")

        canvas_img = self.app.network_canvas.grab().toImage()
        self.assertEqual(canvas_img.pixelColor(4, 4).name().upper(), "#FFFFE3")

        # Escenarios y selectores en español sin alterar valores internos del motor
        self.assertIn("Lluvia moderada", self.app.controls_panel.combo_scenario.currentText())
        self.app.controls_panel.combo_split_rule.setCurrentText("Equitativa")
        self.app.controls_panel.combo_source_dist.setCurrentText("Uniforme (1/8)")
        cfg = self.app._build_sim_config()
        self.assertEqual(cfg.split_rule, "equal")
        self.assertEqual(cfg.source_distribution, "equal")
        self.app.controls_panel.combo_source_dist.setCurrentText("Por capacidad")

    def test_cartographic_surgery_basin_focus_and_traversal_anim(self) -> None:
        # 0. La simulación inicia siempre en el minuto 0
        self.assertEqual(self.app.state.current_step, 0)
        self.assertAlmostEqual(
            self.app.state.result.snapshots[self.app.state.current_step].time_min, 0.0
        )

        # 1. Al seleccionar tubería muestra diámetro actual y conserva el menú durante reproducción
        self.app.network_canvas.select_pipe("P31")
        self.app._on_pipe_selected("P31")
        self.assertIn('8"', self.app.inspector_panel.lbl_diam_current.text())
        self.app.inspector_panel.set_diameter_override_text('16"')
        self.app._action_apply_intervention(
            float(self.app.inspector_panel.scale_obstruction.value()),
            self.app.inspector_panel.combo_diam_override.currentText(),
        )
        _pump(80)
        self.assertIn('16"', self.app.inspector_panel.lbl_diam_current.text())
        self.assertTrue(self.app.inspector_panel.pipe_intervention_card.isVisible())

        self.app.toggle_play_pause()
        _pump(260)
        self.assertTrue(self.app.inspector_panel.pipe_intervention_card.isVisible())
        self.assertEqual(self.app.state.selected_pipe_id, "P31")
        self.app.toggle_play_pause()

        # 2. Cirugía cartográfica: obstrucción 100% en P3 (C -> 31) y perfil longitudinal
        self.app.network_canvas.select_pipe("P3")
        self.app._on_pipe_selected("P3")
        self.app.inspector_panel.set_obstruction_pct(100.0)
        self.app._action_apply_intervention(
            100.0,
            self.app.inspector_panel.combo_diam_override.currentText(),
        )
        _pump(100)
        self.assertIn("C", self.app.state.isolated_nodes)
        self.assertIsNotNone(self.app.state.previous_result)

        self.app.temporal_charts.set_subtab("profile")
        _pump(80)
        self.assertEqual(self.app.temporal_charts._subtab, "profile")
        self.app.temporal_charts.set_subtab("hydro")

        self.app._action_restore_all_interventions()
        self.assertEqual(len(self.app.state.isolated_nodes), 0)
        self.assertEqual(self.app.state.current_step, 0)

        self.app.network_canvas.select_pipe("P31")
        self.app._on_pipe_selected("P31")
        self.app._action_toggle_basin_isolation()
        self.assertTrue(self.app.network_canvas._basin_active)
        self.assertIn("P31", self.app.network_canvas._basin_pipes)
        self.app._action_toggle_basin_isolation()
        self.assertFalse(self.app.network_canvas._basin_active)

        self.app._set_step(45)
        self.app.controls_panel.combo_bfs_start.setCurrentText("10")
        self.app.controls_panel.combo_bfs_target.setCurrentText("31")
        self.app.state.last_traversal_alg = "BFS"
        self.app._action_toggle_traversal_anim()
        _pump(120)
        final_fr = self.app.state.anim_frames[-1]
        self.app.network_canvas.set_traversal_frame(final_fr)
        _pump(40)
        pipes_by_id = {pv.pipe_id: pv for pv in self.app.network_canvas.current_scene.pipes}
        for pid in ("P35", "P51"):
            self.assertNotEqual(pipes_by_id[pid].color.upper(), theme.ACCENT_PRIMARY.upper())
        self.app._stop_traversal_anim(clear_canvas=True)
        self.app.state.last_traversal_alg = "DFS"
        self.app._action_toggle_traversal_anim()
        _pump(120)
        self.app._stop_traversal_anim(clear_canvas=True)

    def test_scenario_switch_while_paused_and_chart_dpi_fit(self) -> None:
        self.app._set_step(25)
        self.assertFalse(self.app.state.is_playing)
        self.assertEqual(self.app.state.result.config.scenario_id, 3)

        # Cambiar de escenario en el selector estando pausado -> actualiza enseguida desde t=0
        self.app.controls_panel.combo_scenario.setCurrentIndex(4)
        _pump(120)
        self.assertEqual(self.app.state.result.config.scenario_id, 5)
        self.assertEqual(self.app.state.current_step, 0)
        self.assertAlmostEqual(self.app.state.result.snapshots[0].time_min, 0.0)

        # Verificar ajuste exacto de figuras Matplotlib al contenedor Qt sin saltos DPI
        self.app.right_tabs.setCurrentIndex(3)
        _wait_tasks(self.app)
        comp_c = self.app.comparison_charts.canvas
        comp_fig = self.app.comparison_charts.figure
        self.assertGreaterEqual(comp_c.width(), 180)
        self.assertAlmostEqual(
            comp_fig.get_figwidth() * comp_fig.dpi,
            comp_c.width() * comp_c.devicePixelRatioF(),
            delta=4.0,
        )
        self.assertAlmostEqual(
            comp_fig.get_figheight() * comp_fig.dpi,
            comp_c.height() * comp_c.devicePixelRatioF(),
            delta=4.0,
        )

        self.app.right_tabs.setCurrentIndex(2)
        _wait_tasks(self.app)
        tmp_c = self.app.temporal_charts.canvas
        tmp_fig = self.app.temporal_charts.figure
        self.assertGreaterEqual(tmp_c.width(), 180)
        self.assertAlmostEqual(
            tmp_fig.get_figwidth() * tmp_fig.dpi,
            tmp_c.width() * tmp_c.devicePixelRatioF(),
            delta=4.0,
        )
        self.assertAlmostEqual(
            tmp_fig.get_figheight() * tmp_fig.dpi,
            tmp_c.height() * tmp_c.devicePixelRatioF(),
            delta=4.0,
        )

    def test_guided_tour_source_attribution_and_stress_map_mode(self) -> None:
        # 1. Guía de sustentación: botón visible, 4 hallazgos + enfoque + cierre
        self.assertTrue(self.app.top_bar.btn_guided_tour.isVisible())
        self.app.toggle_guided_tour()
        _pump(280)
        self.assertTrue(self.app.state.tour_active)
        self.assertTrue(self.app.center_panel.tour_card.isVisible())
        self.assertAlmostEqual(
            self.app.state.result.snapshots[self.app.state.current_step].time_min, 5.0
        )

        for target_min in (25.0, 40.0, 65.0):
            self.app._go_tour_stop(self.app.state.tour_step + 1)
            _pump(260)
            self.assertAlmostEqual(
                self.app.state.result.snapshots[self.app.state.current_step].time_min, target_min
            )

        self.app._close_guided_tour()
        _pump(240)
        self.assertFalse(self.app.state.tour_active)
        self.assertFalse(self.app.center_panel.tour_card.isVisible())

        # 2. Trazabilidad por fuente aportante en el inspector
        self.app.right_tabs.setCurrentIndex(0)
        self.app.network_canvas.select_pipe("P31")
        self.app._on_pipe_selected("P31")
        _pump(80)
        self.assertTrue(self.app.inspector_panel.source_attribution_card.isVisible())
        self.assertIn("F17: 100.0%", self.app.inspector_panel.lbl_source_breakdown.text())

        self.app.network_canvas.select_pipe("P25")
        self.app._on_pipe_selected("P25")
        _pump(80)
        self.assertGreater(len(self.app.inspector_panel.current_source_shares()), 1)

        # 3. Modo Mapa de Estrés Acumulado (Instantáneo | Pico Máximo | Minutos en Sobrecarga)
        self.app._set_map_mode("peak")
        _pump(80)
        self.assertEqual(self.app.network_canvas._map_mode, "peak")

        self.app._set_map_mode("overload_minutes")
        _pump(80)
        self.assertEqual(self.app.network_canvas._map_mode, "overload_minutes")
        self.assertIn("sobrecarga", self.app.controls_panel.sec_legend.title().lower())

        self.app._set_map_mode("instant")
        _pump(60)

    def test_left_panel_scroll_clamping_no_blank_gap(self) -> None:
        sb = self.app.controls_panel.scroll_area.verticalScrollBar()

        # 1. Ventana alta: el scroll permanece en 0 y no crea espacio en blanco superior
        self.app.resize(1400, 1400)
        _pump(180)
        self.assertEqual(sb.value(), 0)
        self.assertEqual(self.app.controls_panel.stack.pos().y(), 0)
        sb.setValue(-10)
        _pump(60)
        self.assertEqual(sb.value(), 0)

        # 2. Ventana baja: permite bajar y al agrandar regresa a 0
        self.app.resize(1200, 560)
        _pump(180)
        if sb.maximum() > 0:
            sb.setValue(40)
            _pump(60)
            self.assertGreater(sb.value(), 0)
            self.app.resize(1400, 1400)
            _pump(180)
            self.assertEqual(sb.value(), 0)

        # 3. Cambiar entre pestañas del panel izquierdo conserva scroll en 0
        self.app.controls_panel.switch_rail_tab("trav")
        _pump(80)
        self.assertEqual(sb.value(), 0)
        self.app.controls_panel.switch_rail_tab("sim")
        _pump(80)
        self.assertEqual(sb.value(), 0)

    def test_guided_tour_per_scenario_and_autoplay_on_execute(self) -> None:
        combo = self.app.controls_panel.combo_scenario
        self.assertEqual(combo.count(), 6)

        self.app.toggle_guided_tour()
        _pump(180)
        self.assertTrue(self.app.state.tour_active)

        seen_titles = set()
        for idx in range(1, 6):
            combo.setCurrentIndex(idx - 1)
            _pump(180)

            self.assertIn(f"Esc. {idx}", self.app.top_bar.btn_guided_tour.text())
            self.assertIn(f"ESC. {idx}", self.app.center_panel.tour_card.lbl_hdr.text())
            self.assertIn(
                f"Escenario {idx}:", self.app.center_panel.tour_card.lbl_scenario.text()
            )
            stops = build_tour_stops(
                self.app.state.dataset, self.app.state.result, self.app._selected_scenario_obj()
            )
            self.assertEqual(len(stops), 4)
            seen_titles.add(stops[1].title)

        self.assertEqual(len(seen_titles), 5)

        # Al presionar "Ejecutar simulación", cierra la guía y reproduce automáticamente
        self.app.center_panel.combo_speed.setCurrentText("10x")
        self.app.controls_panel.btn_run_sim.click()
        _pump(180)
        self.assertFalse(self.app.state.tour_active)
        self.assertTrue(self.app.state.is_playing)
        self.assertGreater(self.app.state.current_step, 0)
        self.app.pause()

        # Validación robusta ante entradas fuera de rango
        self.app.controls_panel.spin_duration.setValue(0.0)
        with self.assertRaises(ValueError):
            self.app._build_sim_config()
        self.app._on_params_changed()
        self.app.controls_panel.spin_duration.setValue(90.0)
        _pump(160)

    def test_stress_map_modes_frozen_global_and_pause_on_select(self) -> None:
        # 1. Minutos en Sobrecarga muestra totales globales 0–90 min incluso en t = 0
        self.app._set_step(0)
        self.app._set_map_mode("overload_minutes")
        _pump(80)
        expected_p25_ov = self.app.state.result.pipe_overloaded_minutes.get("P25", 0.0)
        self.assertGreater(expected_p25_ov, 0.0)
        self.assertAlmostEqual(
            self.app.network_canvas._overload_minutes_map.get("P25", 0.0),
            expected_p25_ov,
            places=3,
        )
        self.assertIn("0–90 min", self.app.network_canvas._stamp_lbl.text())
        self.assertIn("0–90 min", self.app.controls_panel.sec_legend.title())
        self.assertIn("0–90", self.app.center_panel.lbl_clock.text())
        self.assertEqual(self.app.state.current_step, 0)

        # 2. En Pico Máximo desde t = 0 muestra el pico global completo y KPI coherente
        self.app._set_map_mode("peak")
        _pump(80)
        expected_p30_peak = self.app.state.result.peak_pipe_utilization.get("P30", 0.0)
        expected_max_peak = max(
            self.app.state.result.peak_pipe_utilization.values(), default=0.0
        )
        self.assertAlmostEqual(
            self.app.network_canvas._peak_util_map.get("P30", 0.0),
            expected_p30_peak,
            places=2,
        )
        self.assertIn("0–90 min", self.app.network_canvas._stamp_lbl.text())
        self.assertIn("0–90 min", self.app.controls_panel.sec_legend.title())
        self.assertEqual(
            self.app.center_panel.kpi_cards["max_util"].value_text(),
            f"{expected_max_peak:.1f}%",
        )

        # 3. Al reproducir y pulsar Pico Máximo, pausa y conserva current_step al volver
        self.app.center_panel.combo_speed.setCurrentText("10x")
        self.app.controls_panel.btn_run_sim.click()
        _pump(180)
        self.assertEqual(self.app.state.map_mode, "instant")
        self.assertTrue(self.app.state.is_playing)
        self.app._set_map_mode("peak")
        _pump(80)
        self.assertFalse(self.app.state.is_playing)
        saved_step = self.app.state.current_step
        self.assertGreater(saved_step, 0)
        self.assertAlmostEqual(
            self.app.network_canvas._peak_util_map.get("P30", 0.0),
            expected_p30_peak,
            places=2,
        )
        self.app._set_map_mode("instant")
        _pump(60)
        self.assertEqual(self.app.state.current_step, saved_step)
        self.assertAlmostEqual(
            self.app.network_canvas.snapshot.time_min,
            self.app.state.result.snapshots[saved_step].time_min,
            places=3,
        )

        # 4. Avanzar paso (+1) o Reproducir desde Minutos en Sobrecarga regresa a Instantáneo
        self.app._set_map_mode("overload_minutes")
        _pump(60)
        self.app._player_step(1)
        _pump(60)
        self.assertEqual(self.app.state.map_mode, "instant")
        self.assertEqual(
            self.app.state.current_step,
            min(len(self.app.state.result.snapshots) - 1, saved_step + 1),
        )

        self.app._set_map_mode("overload_minutes")
        _pump(60)
        self.app.toggle_play_pause()
        _pump(120)
        self.assertEqual(self.app.state.map_mode, "instant")
        self.assertTrue(self.app.state.is_playing)
        self.app.pause()

        # En t=40 redraw conserva la etiqueta de P25 y _hide_tooltip limpia _last_hover_key
        self.app._set_step(40)
        self.app.network_canvas.redraw()
        pipe_label_ids = {
            b.entity_id
            for b in self.app.network_canvas.current_scene.badges
            if b.kind == "pipe_label"
        }
        self.assertIn("P25", pipe_label_ids)
        self.app.network_canvas._last_hover_key = "node:31"
        self.app.network_canvas._hide_tooltip()
        self.assertIsNone(self.app.network_canvas._last_hover_key)

        # Iniciar BFS con Guía activa cierra la guía automáticamente para mostrar la ruta
        self.app.toggle_guided_tour()
        self.assertTrue(self.app.state.tour_active)
        self.app.controls_panel.combo_bfs_start.setCurrentText("6")
        self.app.controls_panel.combo_bfs_target.setCurrentText("31")
        self.app._run_traversal("BFS")
        self.assertFalse(self.app.state.tour_active)
        self.assertFalse(self.app.network_canvas._tour_active)
        self.assertIn("31", self.app.network_canvas.highlight_node_ids)

    def test_u1_u2_u3_u4_ui_fixes(self) -> None:
        # U1: toggle Aguas arriba / Aguas abajo solo en el Inspector (segundo clic limpia)
        self.app.network_canvas.select_node("20")
        self.app._on_node_selected("20")
        _pump(60)
        self.app.inspector_panel.btn_insp_downstream.click()
        _pump(60)
        self.assertEqual(self.app.state.inspector_trace_state, ("20", "down"))
        self.assertGreater(len(self.app.network_canvas.highlight_pipe_ids), 0)
        self.app.inspector_panel.btn_insp_downstream.click()
        _pump(60)
        self.assertIsNone(self.app.state.inspector_trace_state)
        self.assertEqual(len(self.app.network_canvas.highlight_pipe_ids), 0)

        # U3: filtros excluyentes en Tuberías Críticas (>75-100% vs >100% vs <=75%)
        self.app._set_step(30)
        self.app.right_tabs.setCurrentIndex(1)
        _pump(80)
        self.app.critical_panel.set_filter("critical")
        self.app._refresh_critical_table()
        _pump(60)
        for pid in self.app.critical_panel.row_pipe_ids():
            u_txt = self.app.critical_panel.row_utilization_text(pid).split("%")[0].strip()
            u_val = float(u_txt)
            self.assertGreater(u_val, 75.0)
            self.assertLessEqual(u_val, 100.0)
        self.app.critical_panel.set_filter("overloaded")
        self.app._refresh_critical_table()
        _pump(60)
        for pid in self.app.critical_panel.row_pipe_ids():
            u_txt = self.app.critical_panel.row_utilization_text(pid).split("%")[0].strip()
            self.assertGreater(float(u_txt), 100.0)
        self.app.critical_panel.set_filter("rest")
        self.app._refresh_critical_table()
        _pump(60)
        for pid in self.app.critical_panel.row_pipe_ids():
            u_txt = self.app.critical_panel.row_utilization_text(pid).split("%")[0].strip()
            self.assertLessEqual(float(u_txt), 75.0)

        # U2: Comparación actualiza timestamp y marca sucio al cambiar parámetros
        self.app.right_tabs.setCurrentIndex(3)
        _wait_tasks(self.app)
        self.assertIn("Al día", self.app.comparison_panel.lbl_comp_hint.text())
        self.app.controls_panel.spin_ingress_pct.setValue(2.5)
        _pump(220)
        self.assertIn(
            "Parámetros modificados", self.app.comparison_panel.lbl_comp_hint.text()
        )
        self.app.comparison_panel.btn_compare.click()
        _wait_tasks(self.app)
        self.assertIn("Al día", self.app.comparison_panel.lbl_comp_hint.text())
        self.app.controls_panel.apply_preset(100.0, 0.0)
        _pump(80)

        # U2 tabla completa + scroll horizontal en Comparación (sin recorte en panel mediano)
        self.app.resize(1080, 680)
        self.app.right_tabs.setCurrentIndex(3)
        _wait_tasks(self.app)
        comp_tbl = self.app.comparison_panel.table
        self.assertEqual(comp_tbl.item(2, 0).text(), "E3 Lluvia moderada")
        self.assertEqual(comp_tbl.item(4, 0).text(), "E5 Lluvia extrema")
        total_comp_w = sum(comp_tbl.columnWidth(c) for c in range(comp_tbl.columnCount()))
        self.assertGreater(total_comp_w, comp_tbl.viewport().width())
        self.assertGreater(comp_tbl.horizontalScrollBar().maximum(), 0)

        # U4: PauseOnOpenComboBox pausa reproducción al desplegar sin perder el valor
        self.assertEqual(self.app.controls_panel.combo_scenario.count(), 5)
        for combo_attr in ("combo_split_rule", "combo_source_dist", "combo_scenario"):
            widget = getattr(self.app.controls_panel, combo_attr)
            before_txt = widget.currentText()
            self.assertTrue(bool(before_txt))
            self.app.toggle_play_pause()
            self.assertTrue(self.app.state.is_playing)
            widget.aboutToShowPopup.emit()
            self.assertFalse(self.app.state.is_playing)
            self.assertEqual(widget.currentText(), before_txt)

    def test_network_canvas_compact_hidpi_no_node_or_badge_overlap(self) -> None:
        for width, height, dpi_scale, zoom, expect_all_texts in (
            (652, 378, 1.5, 1.0, True),
            (652, 378, 1.0, 1.0, True),
            (644, 374, 1.5, 0.55, False),
        ):
            canvas = NetworkCanvas(
                ui_font=self.app.ui_font,
                mono_font=self.app.mono_font,
                dpi_scale=dpi_scale,
            )
            canvas.resize(width, height)
            canvas.show()
            _pump(40)
            canvas.set_graph(self.app.state.dataset.graph)
            canvas._zoom = zoom
            canvas.redraw()
            _pump(40)

            scene = canvas.current_scene
            self.assertEqual(len(scene.nodes), 46)
            visible_node_labels = [n for n in scene.nodes if n.show_label]
            if expect_all_texts:
                self.assertEqual(len(visible_node_labels), 46)
            else:
                self.assertLessEqual(len(visible_node_labels), 2)

            # Ningún par de nodos debe solaparse
            for i in range(len(scene.nodes)):
                a = scene.nodes[i]
                ax0, ay0, ax1, ay1 = a.x - a.radius, a.y - a.radius, a.x + a.radius, a.y + a.radius
                for j in range(i + 1, len(scene.nodes)):
                    b = scene.nodes[j]
                    bx0, by0, bx1, by1 = b.x - b.radius, b.y - b.radius, b.x + b.radius, b.y + b.radius
                    overlaps = not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1)
                    self.assertFalse(
                        overlaps,
                        f"Nodos solapados {a.node_id}-{b.node_id} en zoom={zoom}",
                    )

            # Las etiquetas internas visibles deben caber dentro de su círculo
            for nv in visible_node_labels:
                f = QFont(self.app.ui_font)
                f.setPixelSize(nv.font_px)
                f.setBold(True)
                fm = QFontMetricsF(f)
                rect = fm.tightBoundingRect(nv.node_id)
                self.assertLessEqual(rect.width(), nv.radius * 2.0 + 2.0)
                self.assertLessEqual(rect.height(), nv.radius * 2.0 + 2.0)

            # El cartel PTAR no debe invadir otros nodos ni overlays
            ptar_badges = [b for b in scene.badges if b.kind == "sink"]
            self.assertEqual(len(ptar_badges), 1)
            pb = ptar_badges[0]
            for nv in scene.nodes:
                if nv.node_id == "31":
                    continue
                nx0, ny0, nx1, ny1 = nv.x - nv.radius, nv.y - nv.radius, nv.x + nv.radius, nv.y + nv.radius
                self.assertFalse(
                    not (pb.x1 < nx0 or pb.x0 > nx1 or pb.y1 < ny0 or pb.y0 > ny1)
                )

            ov_boxes = canvas.overlay_boxes()
            for fb in [b for b in scene.badges if b.kind == "source"]:
                for ov_box in ov_boxes:
                    self.assertFalse(
                        not (
                            fb.x1 < ov_box[0]
                            or fb.x0 > ov_box[2]
                            or fb.y1 < ov_box[1]
                            or fb.y0 > ov_box[3]
                        )
                    )

            canvas.close_overlays()
            canvas.close()
            canvas.deleteLater()
            _pump(20)

    def test_charts_baseline_persistence_symlog_profile_and_comparison(self) -> None:
        # 1. Múltiples intervenciones seguidas conservan siempre la base original sin intervenciones
        self.app.network_canvas.select_pipe("P29")
        self.app._on_pipe_selected("P29")
        self.app.inspector_panel.set_obstruction_pct(50.0)
        self.app._action_apply_intervention(
            50.0, self.app.inspector_panel.combo_diam_override.currentText()
        )
        _pump(80)
        base_ref = self.app.state.baseline_result
        self.assertIsNotNone(base_ref)
        self.assertEqual(len(base_ref.config.interventions), 0)
        self.assertIs(self.app.state.previous_result, base_ref)

        self.app.inspector_panel.set_obstruction_pct(80.0)
        self.app._action_apply_intervention(
            80.0, self.app.inspector_panel.combo_diam_override.currentText()
        )
        _pump(80)
        self.assertIs(self.app.state.previous_result, base_ref)
        self.assertEqual(len(self.app.state.previous_result.config.interventions), 0)

        # 2. En pestaña Evolución muestra el banner de impacto y ticks symlog explícitos (>2 marcas)
        self.app.right_tabs.setCurrentIndex(2)
        _wait_tasks(self.app)
        self.assertTrue(self.app.temporal_charts._banner_visible)
        self.assertGreaterEqual(len(self.app.temporal_charts.ax_util.get_yticks()), 4)

        # 3. Restaurar todo oculta el banner y limpia previous_result
        self.app._action_restore_all_interventions()
        _pump(120)
        self.assertIsNone(self.app.state.previous_result)
        self.assertFalse(self.app.temporal_charts._banner_visible)

        # 4. Escenario 5 (tope 120% F_max): Perfil longitudinal en ruta crítica (P25) en '% Uso' y 'Caudal m³/s'
        self.app.controls_panel.combo_scenario.setCurrentIndex(4)
        self.app.network_canvas.select_pipe("P25")
        self.app._on_pipe_selected("P25")
        _pump(140)
        self.app._set_step(25)
        self.app.temporal_charts.set_subtab("profile")
        _pump(120)
        self.assertEqual(self.app.temporal_charts._profile_mode, "pct")
        ytick_labels = [
            t.get_text() for t in self.app.temporal_charts.ax_profile.get_yticklabels()
        ]
        self.assertTrue(any("Rebose" in lbl for lbl in ytick_labels))
        self.app.temporal_charts.set_profile_mode("flow")
        _pump(80)
        self.assertEqual(self.app.temporal_charts._profile_mode, "flow")
        self.app.temporal_charts.set_profile_mode("pct")
        self.app.temporal_charts.set_subtab("hydro")

        # 5. Comparación de 5 escenarios permite alternar entre Rebose (m³) y Descarga PTAR 31
        self.app.right_tabs.setCurrentIndex(3)
        _wait_tasks(self.app)
        self.assertEqual(self.app.comparison_charts._metric_mode, "flood")
        self.app.comparison_charts.set_metric_mode("ptar")
        _pump(100)
        self.assertEqual(self.app.comparison_charts._metric_mode, "ptar")
        self.app.comparison_charts.set_metric_mode("flood")

    def test_async_charts_spinner_and_visible_guided_tour_buttons(self) -> None:
        # 1. Una sola entrada del Tour Guiado (barra superior) que activa/desactiva el recorrido
        self.assertTrue(self.app.top_bar.btn_guided_tour.isVisible())
        self.assertIn("Tour Guiado", self.app.top_bar.btn_guided_tour.text())
        self.assertFalse(hasattr(self.app.center_panel, "btn_tour_quick"))

        self.app.top_bar.btn_guided_tour.click()
        _pump(120)
        self.assertTrue(self.app.state.tour_active)
        self.assertTrue(self.app.center_panel.tour_card.isVisible())
        self.assertEqual(self.app.top_bar.btn_guided_tour.property("variant"), "dark_primary")

        self.app.top_bar.btn_guided_tour.click()
        _pump(120)
        self.assertFalse(self.app.state.tour_active)
        self.assertEqual(self.app.top_bar.btn_guided_tour.property("variant"), "dark_tour")

        # 2. Al seleccionar tuberías estando en Inspector, no redibuja Evolución innecesariamente
        t0 = time.perf_counter()
        self.app.network_canvas.select_pipe("P29")
        self.app._on_pipe_selected("P29")
        self.app.network_canvas.select_pipe("P31")
        self.app._on_pipe_selected("P31")
        select_elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertLess(select_elapsed_ms, 250.0)
        self.assertTrue(self.app._charts_tab_dirty)

        # 3. Al abrir Evolución activa el spinner brevemente y luego lo oculta al completar
        self.app.right_tabs.setCurrentIndex(2)
        self.assertTrue(self.app.temporal_charts.loading_overlay.isVisible())
        _wait_tasks(self.app)
        self.assertFalse(self.app.temporal_charts.loading_overlay.isVisible())
        self.assertFalse(self.app._charts_tab_dirty)

        # 4. Al abrir Comparación devuelve el control de UI rápido con spinner animándose
        self.app.controls_panel.apply_preset(100.0, 0.0)
        self.app.state.comparisons = []
        self.app.state.comparisons_dirty = False
        spinner_angles = [self.app.comparison_panel.loading_overlay.spinner._angle]
        loop = QEventLoop(self.app)
        probe_timer = QTimer()
        probe_timer.setInterval(30)

        def _probe_tick() -> None:
            spinner_angles.append(
                self.app.comparison_panel.loading_overlay.spinner._angle
            )
            if not self.app.is_comparison_running():
                loop.quit()

        probe_timer.timeout.connect(_probe_tick)
        QTimer.singleShot(8000, loop.quit)

        t_sw = time.perf_counter()
        self.app.right_tabs.setCurrentIndex(3)
        switch_ms = (time.perf_counter() - t_sw) * 1000.0
        self.assertLess(switch_ms, 250.0)
        self.assertTrue(self.app.comparison_panel.loading_overlay.isVisible())
        self.assertFalse(self.app.comparison_panel.btn_compare.isEnabled())

        probe_timer.start()
        loop.exec()
        probe_timer.stop()
        _wait_tasks(self.app)

        self.assertGreaterEqual(len(set(spinner_angles)), 4)
        self.assertFalse(self.app.comparison_panel.loading_overlay.isVisible())
        self.assertTrue(self.app.comparison_panel.btn_compare.isEnabled())
        self.assertEqual(self.app.comparison_panel.table.rowCount(), 5)

    def test_ford_fulkerson_tab_configurable_cap_and_fmax_simulation(self) -> None:
        # 1. Cambiar tope físico a 130% y recalcular escenario actual (E5)
        self.app.controls_panel.combo_scenario.setCurrentIndex(4)
        _pump(120)
        self.assertAlmostEqual(self.app.state.result.system_max_flow_m3s, 0.35914566, places=5)
        self.assertAlmostEqual(self.app.state.result.utilization_cap_pct, 120.0, places=5)
        self.assertAlmostEqual(self.app.state.result.peak_pipe_utilization["P31"], 120.0, places=4)

        self.app.controls_panel.set_util_cap_pct(130.0)
        _pump(120)
        self.assertAlmostEqual(self.app.state.result.utilization_cap_pct, 130.0, places=5)
        self.assertAlmostEqual(self.app.state.result.peak_system_utilization_pct, 130.0, places=5)
        self.assertIn("sys_fmax", self.app.center_panel.kpi_cards)

        # Restaurar tope 120%
        self.app.controls_panel.set_util_cap_pct(120.0)
        _pump(120)

        # 2. Botón Corte Mín. FF resalta aristas del corte mínimo en el canvas
        self.app.controls_panel.btn_ford_fulkerson.click()
        _pump(80)
        self.assertTrue(self.app.network_canvas.highlight_pipe_ids)
        for pid in ("P3", "P28", "P43", "P53"):
            self.assertIn(pid, self.app.network_canvas.highlight_pipe_ids)

        # 3. Pestaña Flujo Máx. (índice 4): cálculo asíncrono + tabla + doble clic para simular % F_max
        self.app.right_tabs.setCurrentIndex(4)
        deadline = time.monotonic() + 10.0
        while self.app.is_max_flow_running() and time.monotonic() < deadline:
            _pump(25)
        _pump(100)
        self.assertFalse(self.app.is_max_flow_running())
        self.assertEqual(self.app.max_flow_panel.table.rowCount(), 9)
        self.assertIsNotNone(self.app.state.max_flow_result)

        # Escenario Extra "% de F_max" a 150% + Ejecutar (debe topar uso del sistema en 120%)
        extra_idx = self.app.controls_panel.combo_scenario.findText(
            self.app.controls_panel.EXTRA_FMAX_SCENARIO_LABEL
        )
        self.assertGreaterEqual(extra_idx, 0)
        self.app.controls_panel.combo_scenario.setCurrentIndex(extra_idx)
        _pump(60)
        self.assertTrue(self.app.controls_panel.fmax_target_row.isVisible())
        self.assertFalse(self.app.controls_panel.spin_ingress_pct.isEnabled())
        self.app.controls_panel.spin_target_fmax_pct.setValue(150)
        self.app.controls_panel.btn_run_sim.click()
        _pump(120)
        self.assertIn("150% F_max", self.app.controls_panel.btn_run_sim.text())
        self.assertAlmostEqual(self.app.state.active_target_fmax_pct, 150.0, places=4)
        self.assertAlmostEqual(self.app.state.result.peak_system_utilization_pct, 120.0, places=4)
        self.assertAlmostEqual(self.app.state.result.peak_pipe_utilization["P31"], 120.0, places=4)
        self.assertIn("Sim. 150% F_max", self.app.center_panel.lbl_clock.text())

        # 4. Preset Calibrado F_max (E3 = 100%)
        self.app.controls_panel.combo_scenario.setCurrentIndex(2)
        _pump(100)
        self.assertEqual(self.app.controls_panel.demand_mode(), "rain")
        self.assertIsNone(self.app.state.active_target_fmax_pct)
        self.assertTrue(self.app.controls_panel.btn_fmax_preset.isEnabled())
        self.app.controls_panel.btn_fmax_preset.click()
        _pump(120)
        self.assertEqual(self.app.controls_panel.combo_scenario.currentIndex(), 2)
        self.assertIsNone(self.app.state.active_target_fmax_pct)
        self.assertAlmostEqual(
            self.app.controls_panel.spin_ingress_pct.value(), 1.48, places=2
        )
        self.assertAlmostEqual(
            self.app.state.result.peak_system_utilization_pct, 100.0, delta=0.5
        )
        self.app.pause()
        self.app.controls_panel.apply_preset(100.0, 0.0)
        self.app.right_tabs.setCurrentIndex(0)
        _pump(80)

    def test_traversal_finish_handoff_to_live_playback_with_particles_and_transitions(self) -> None:
        # 1. Ejecutar animación BFS 6 -> 31 hasta el último fotograma
        self.app.controls_panel.combo_bfs_start.setCurrentText("6")
        self.app.controls_panel.combo_bfs_target.setCurrentText("31")
        self.app.state.last_traversal_alg = "BFS"
        self.app._action_toggle_traversal_anim()
        self.assertIsNotNone(self.app.network_canvas._traversal_frame)
        # Avanzar al último paso para activar el temporizador de transición
        self.app.state.anim_idx = len(self.app.state.anim_frames) - 1
        self.app._step_traversal_anim()
        self.assertFalse(self.app.state.is_animating_traversal)
        self.assertGreater(len(self.app.network_canvas.current_scene.route_tracks), 0)

        # 2. Pulsar Reproducir debe consolidar el recorrido a flujo hidráulico en vivo
        self.app.toggle_play_pause()
        self.assertTrue(self.app.state.is_playing)
        self.assertIsNone(self.app.network_canvas._traversal_frame)
        self.assertGreater(len(self.app.network_canvas.highlight_pipe_ids), 0)
        self.assertGreater(len(self.app.network_canvas._ordered_route_pipes), 0)
        self.assertLess(self.app.network_canvas._route_transition_t, 1.0)

        # Bombear eventos para completar la ola de transición y generar partículas hidráulicas
        self.app._set_step(25)
        self.assertTrue(self.app.state.is_playing)
        _pump(520)
        self.assertAlmostEqual(self.app.network_canvas._route_transition_t, 1.0, places=2)

        scene = self.app.network_canvas.current_scene
        focus_tracks = [tr for tr in scene.pulse_tracks if tr.is_focus]
        self.assertGreater(len(focus_tracks), 0)
        self.assertTrue(all(tr.route_offset_px >= 0.0 for tr in focus_tracks))
        self.assertTrue(self.app.network_canvas._pulse_timer.isActive())

        # Los tramos del recorrido mantienen el color hidráulico en vivo (cambian de t=0 a t=40)
        self.app.pause()
        self.app._set_step(0)
        colors_t0 = {
            pv.pipe_id: pv.color
            for pv in self.app.network_canvas.current_scene.pipes
            if pv.is_focus
        }
        self.app._set_step(40)
        self.assertLess(self.app.network_canvas._color_lerp_t, 1.0)
        colors_t40 = {
            pv.pipe_id: pv.color
            for pv in self.app.network_canvas.current_scene.pipes
            if pv.is_focus
        }
        self.assertTrue(any(colors_t0[pid] != colors_t40[pid] for pid in colors_t0))
        self.assertTrue(all(col.upper() != theme.ACCENT_PRIMARY.upper() for col in colors_t40.values()))

        # Limpiar resaltados apaga la ruta suavemente
        self.app._clear_highlights()
        self.assertEqual(len(self.app.network_canvas.highlight_pipe_ids), 0)
        self.assertEqual(len(self.app.network_canvas._ordered_route_pipes), 0)


if __name__ == "__main__":
    unittest.main()
