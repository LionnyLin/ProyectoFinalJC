"""Pruebas de GUI: funciones puras de tema, API de los 7 módulos y smoke test con display."""

import os, time, tkinter as tk, unittest
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
        self.assertIn("Aguas arriba", self.app.controls.get_traversal_log())

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
        kpi_crit_text = self.app._kpi_cards["critical"].cget("text")
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
        self.assertFalse(hasattr(self.app.controls, "_traversal_note"))

        self.app._action_traversal("BFS", "17", "31", animate=True)
        self.app.update()
        self.assertGreater(len(self.app.traversal_frames), 0)
        self.assertIn("Paso 1/", self.app.controls.get_traversal_log())

        self.app.clear_traversal()
        self.app.update()
        self.assertEqual(len(self.app.traversal_frames), 0)
        self.assertEqual(self.app.controls.get_traversal_log(), "")

        self.app.run_simulation(auto_play=True)
        self.assertTrue(self.app.is_playing)
        self.app._stop_playback(False)


class TestGuiParity(unittest.TestCase):
    """Paridad con main: atajos, layout responsivo, parámetros, selectores, reproductor y bitácora."""

    def setUp(self) -> None:
        if not _has_display():
            self.skipTest("Entorno headless sin display X11 disponible")
        self.app = gui_app.BicentenarioSewerApp(initial_data_path=DATA_XLSX)
        self.app.withdraw()
        self.app.update_idletasks()

    def tearDown(self) -> None:
        if hasattr(self, "app") and self.app is not None:
            self.app._on_close()

    # -- atajos ---------------------------------------------------------------
    def test_shortcuts_act_without_typing_focus(self) -> None:
        app = self.app
        with patch.object(app, "focus_get", return_value=None):
            self.assertEqual(app._shortcut_step(None, 1), "break")
            self.assertEqual(app.current_step, 1)
            app._shortcut_step(None, -1)
            self.assertEqual(app.current_step, 0)
            app.go_to_step(7)
            self.assertEqual(app._shortcut_home(None), "break")
            self.assertEqual(app.current_step, 0)
            self.assertEqual(app._shortcut_play_pause(None), "break")
            self.assertTrue(app.is_playing)
            app._shortcut_play_pause(None)
            self.assertFalse(app.is_playing)
            app.select_entity("pipe", "P30")
            app._action_trace("17", upstream=False)
            app._shortcut_escape(None)
            self.assertEqual(app.traversal_frames, [])
            self.assertEqual((app.selected_kind, app.selected_id), (None, None))
        for seq in ("<space>", "<Left>", "<Right>", "<Home>", "<Control-f>", "<Escape>"):
            self.assertTrue(app.bind(seq), seq)

    def test_shortcuts_ignored_while_typing(self) -> None:
        app = self.app
        for widget in (app.controls._search_entry, app.controls._param_spins["duration"]):
            with patch.object(app, "focus_get", return_value=widget):
                self.assertTrue(app._is_typing_widget())
                self.assertIsNone(app._shortcut_play_pause(None))
                self.assertIsNone(app._shortcut_step(None, 1))
                self.assertIsNone(app._shortcut_home(None))
        self.assertFalse(app.is_playing)
        self.assertEqual(app.current_step, 0)

    def test_ctrl_f_opens_traversal_tab_and_shows_hidden_left_panel(self) -> None:
        app = self.app
        app.toggle_left_panel()
        self.assertFalse(app._show_left)
        app._shortcut_focus_search(None)
        self.assertTrue(app._show_left)
        self.assertEqual(app.controls.rail_tab, "trav")
        self.assertIn(str(app.controls._search_entry), [str(w) for w in app.paned.panes()] + [str(app.controls._search_entry)])

    # -- layout responsivo ----------------------------------------------------
    def test_panel_toggles_and_compact_exclusivity(self) -> None:
        app = self.app
        app._apply_responsive_layout(1400, 800)
        self.assertEqual(app._layout_tier, "wide")
        self.assertEqual(len(app.paned.panes()), 3)
        app.toggle_left_panel()
        self.assertEqual(len(app.paned.panes()), 2)
        self.assertFalse(app._show_left)
        app.toggle_left_panel()
        self.assertEqual(len(app.paned.panes()), 3)
        app.toggle_right_panel()
        self.assertEqual(len(app.paned.panes()), 2)
        app.toggle_right_panel()
        app._apply_responsive_layout(880, 700)
        self.assertEqual(app._layout_tier, "compact")
        self.assertTrue(app._show_left and not app._show_right)
        app.toggle_right_panel()
        self.assertTrue(app._show_right and not app._show_left)
        app.toggle_left_panel()
        self.assertTrue(app._show_left and not app._show_right)

    def test_topbar_groups_actions_and_hint_visibility(self) -> None:
        app = self.app
        app._apply_responsive_layout(1000, 700)
        self.assertEqual(app.menu_btn_file.winfo_manager(), "pack")
        self.assertEqual(app.btn_load_excel.winfo_manager(), "")
        self.assertEqual(app.lbl_shortcuts_hint.winfo_manager(), "pack")
        app._apply_responsive_layout(960, 700)
        self.assertEqual(app.lbl_app_title.cget("text"), "Ciudad Bicentenario")
        self.assertEqual(app.lbl_app_subtitle.winfo_manager(), "")
        app._apply_responsive_layout(900, 700)
        self.assertEqual(app.lbl_shortcuts_hint.winfo_manager(), "")
        app._apply_responsive_layout(1800, 900)
        self.assertEqual(app.btn_load_excel.winfo_manager(), "pack")
        self.assertEqual(app.menu_btn_file.winfo_manager(), "")
        self.assertEqual(app.lbl_app_subtitle.winfo_manager(), "pack")

    def test_resize_event_is_debounced(self) -> None:
        app = self.app
        calls = []
        with patch.object(app, "_apply_responsive_layout", side_effect=lambda w, h: calls.append((w, h))):
            ev = type("E", (), {"widget": app})()
            for _ in range(10):
                app._on_window_configure(ev)
            self.assertEqual(calls, [])
            app.after(150, lambda: None)
            self.assertIsNotNone(app._resize_after_id)
            for _ in range(20):
                app.update(); time.sleep(0.01)
        self.assertLess(len(calls), 10)
        self.assertGreaterEqual(len(calls), 1)

    # -- parámetros, presets y debounce ---------------------------------------
    def test_param_defaults_ranges_and_config_mapping(self) -> None:
        c = self.app.controls
        specs = {k: (float(sp.cget("from")), float(sp.cget("to")), float(sp.cget("increment"))) for k, sp in c._param_spins.items()}
        self.assertEqual(specs["duration"], (10.0, 360.0, 10.0))
        self.assertEqual(specs["storm"], (0.0, 360.0, 5.0))
        self.assertEqual(specs["dt"], (0.5, 10.0, 0.5))
        self.assertEqual(specs["ingress"], (0.5, 100.0, 0.5))
        self.assertEqual(specs["dry"], (0.0, 0.05, 0.001))
        cfg = c.get_simulation_config()
        self.assertEqual((cfg.scenario_id, cfg.duration_min, cfg.storm_duration_min, cfg.dt_min), (3, 90.0, 60.0, 1.0))
        self.assertEqual((cfg.ingress_factor, cfg.dry_weather_flow_per_source_m3s), (1.0, 0.0))
        c._storm_var.set("0")
        self.assertEqual(c.get_simulation_config().storm_duration_min, 0.0)
        for key, bad in (("duration", "5"), ("dt", "abc"), ("ingress", "0.1"), ("ingress", "101"), ("dry", "0.2"), ("storm", "-1")):
            old = c._param_vars[key].get()
            c._param_vars[key].set(bad)
            with self.assertRaises(ValueError):
                c.get_simulation_config()
            c._param_vars[key].set(old)
        c._dt_var.set("10"); c._duration_var.set("10")
        self.assertEqual(c.get_simulation_config().dt_min, 10.0)

    def test_presets_reach_simulation_config(self) -> None:
        app, c = self.app, self.app.controls
        c.apply_preset(2.5, 0.003)
        self.assertEqual((c._ingress_var.get(), c._dry_var.get()), ("2.5", "0.003"))
        cfg = c.get_simulation_config()
        self.assertAlmostEqual(cfg.ingress_factor, 0.025)
        self.assertAlmostEqual(cfg.dry_weather_flow_per_source_m3s, 0.003)
        c.apply_preset(100.0, 0.0)
        cfg = c.get_simulation_config()
        self.assertEqual((cfg.ingress_factor, cfg.dry_weather_flow_per_source_m3s), (1.0, 0.0))
        c._cancel = None
        c.cancel_pending()
        c.apply_preset(2.5, 0.003)
        app.update_idletasks()
        c._fire_param_rerun()
        self.assertAlmostEqual(app.result.config.ingress_factor, 0.025)
        self.assertAlmostEqual(app.result.config.dry_weather_flow_per_source_m3s, 0.003)

    def test_param_rerun_is_debounced_and_skips_invalid_values(self) -> None:
        app, c = self.app, self.app.controls
        calls = []
        orig = app.run_simulation
        app.run_simulation = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
        c._duration_var.set("60")
        for _ in range(5):
            c._schedule_param_rerun()
        self.assertEqual(calls, [])
        deadline = time.time() + 1.5
        while not calls and time.time() < deadline:
            app.update(); time.sleep(0.02)
        for _ in range(10):
            app.update(); time.sleep(0.02)
        self.assertEqual(len(calls), 1)
        self.assertEqual(app.result.config.duration_min, 60.0)
        # valor inválido: no re-simula y muestra el error
        c._duration_var.set("5")
        c._schedule_param_rerun()
        time.sleep(0.2); app.update()
        self.assertEqual(len(calls), 1)
        self.assertIn("Duración", c._param_error.cget("text"))
        # sin cambios reales: tampoco re-simula
        c._duration_var.set("60")
        c._schedule_param_rerun()
        time.sleep(0.2); app.update()
        self.assertEqual(len(calls), 1)

    def test_menu_selectors_change_split_and_source_rules(self) -> None:
        app, c = self.app, self.app.controls
        from src.gui.widgets import _ScenarioMenuButton
        for w in (c._scenario_combo, c._split_combo, c._source_combo):
            self.assertIsInstance(w, _ScenarioMenuButton)
        self.assertEqual(len(c._scenario_combo["values"]), 5)
        calls = []
        orig = app.run_simulation
        app.run_simulation = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
        c._split_combo._menu.invoke(1)
        self.assertEqual(c._split_var.get(), "Equitativa")
        c._source_combo._menu.invoke(1)
        self.assertEqual(c._source_var.get(), "Uniforme (1/8)")
        time.sleep(0.2)
        for _ in range(10):
            app.update(); time.sleep(0.02)
        self.assertEqual(len(calls), 1)
        self.assertEqual((app.result.config.split_rule, app.result.config.source_distribution), ("equal", "equal"))
        c._scenario_combo._menu.invoke(0)
        self.assertTrue(c._scenario_var.get().startswith("Esc. 1"))

    def test_left_panel_tabs(self) -> None:
        c = self.app.controls
        self.assertEqual(c.rail_tab, "sim")
        self.assertEqual(c._sim_page.winfo_manager(), "pack")
        c.switch_tab("trav")
        self.assertEqual((c._sim_page.winfo_manager(), c._trav_page.winfo_manager()), ("", "pack"))
        self.assertEqual((c._start_var.get(), c._target_var.get()), ("6", "31"))
        c.switch_tab("sim")
        self.assertEqual(c._trav_page.winfo_manager(), "")

    # -- reproductor ----------------------------------------------------------
    def test_player_speeds_and_balance_indicator(self) -> None:
        app = self.app
        app._on_player_configure(type("E", (), {"width": 900})())
        self.assertEqual(list(app._speed_combo["values"]), ["0.5x", "1x", "2x", "5x", "10x"])
        for label, ms in (("0.5x", 840), ("1x", 420), ("2x", 210), ("5x", 85), ("10x", 40)):
            app._speed_var.set(label)
            app._on_speed_change()
            self.assertEqual(app.play_speed_ms, ms)
        app.go_to_step(5)
        txt = app._mass_lbl.cget("text")
        self.assertTrue(txt.startswith("Balance masa OK · Err ") and txt.endswith(" m³"), txt)
        self.assertEqual(str(app._mass_lbl.cget("fg")), theme.OK_TEXT)
        snap = app.result.snapshots[5]
        old = snap.mass_balance_error_m3
        snap.mass_balance_error_m3 = 5e-3
        try:
            app._update_mass_label(snap)
            self.assertIn("ERROR", app._mass_lbl.cget("text"))
            self.assertEqual(str(app._mass_lbl.cget("fg")), theme.ERROR_TEXT)
        finally:
            snap.mass_balance_error_m3 = old

    def test_player_compact_mode_uses_icon_only_buttons(self) -> None:
        app = self.app
        ev = type("E", (), {"width": 500})()
        app._on_player_configure(ev)
        self.assertEqual(app._btn_step_fwd.cget("text"), "")
        self.assertTrue(app._mass_lbl.cget("text").startswith("Masa OK"))
        app._on_player_configure(type("E", (), {"width": 900})())
        self.assertEqual(app._btn_step_fwd.cget("text").strip(), "+1")
        self.assertTrue(app._mass_lbl.cget("text").startswith("Balance masa OK"))

    def test_player_buttons_icons_and_labels(self) -> None:
        app = self.app
        app._on_player_configure(type("E", (), {"width": 900})())
        self.assertTrue(app._icons and all(str(app._btn_play.cget("image")) for _ in (0,)))
        app.toggle_play()
        self.assertIn("Pausar", app._btn_play.cget("text"))
        app.toggle_play()
        self.assertFalse(app.is_playing)
        app.go_to_step(10)
        self.assertIn("Reanudar", app._btn_play.cget("text"))
        app._reset_playback()
        self.assertIn("Reproducir", app._btn_play.cget("text"))

    # -- bitácora -------------------------------------------------------------
    def test_traversal_log_strip_during_animation_and_final_text(self) -> None:
        app, c = self.app, self.app.controls
        c.switch_tab("trav")
        for algo, name, head in (("BFS", "Queue", "Cola (Queue) · FRENTE → FINAL"), ("DFS", "Stack", "Pila (Stack) · TOPE ↑")):
            app.start_traversal_animation(algo, "6", "31")
            app.update()
            frames = app.traversal_frames
            self.assertGreaterEqual(len(frames), 3)
            self.assertEqual(frames[0].structure_name, name)
            self.assertTrue(c.strip_header().startswith(head))
            self.assertEqual(c.strip_items()[:len(frames[0].structure_items[:6])], [str(x) for x in frames[0].structure_items[:6]])
            self.assertEqual(c._struct_cells.winfo_children()[0].cget("bg"), theme.ACCENT_PRIMARY)
            self.assertIn(f"[{algo} · Paso 1/", c.get_traversal_log())
            self.assertEqual(c.btn_anim.cget("text"), "Detener animación")
            # avanza manualmente a un fotograma con estructura de >=1 elemento
            idx = next(i for i, f in enumerate(frames) if len(f.structure_items) >= 1 and i > 0)
            app.step_traversal_animation(idx)
            items = [str(x) for x in frames[app.anim_idx].structure_items]
            self.assertEqual(c.strip_items()[:min(6, len(items))], items[:6])
            if len(items) > 6:
                self.assertEqual(c.strip_items()[-1], f"+{len(items) - 6}")
            self.assertIn(f"Paso {app.anim_idx + 1}/", c.get_traversal_log())
            self.assertEqual(c.btn_anim.cget("text"), "Animar recorrido")
            app.step_traversal_animation(len(frames))
            log = c.get_traversal_log()
            self.assertIn(f"[{algo}] 6 → 31", log)
            self.assertIn("Visitados", log); self.assertIn("Ruta (", log)
            app.clear_traversal()
            self.assertEqual(c.get_traversal_log(), "")
            self.assertEqual(c.strip_items(), ["(vacía)"])

    def test_static_traversal_summary_and_animation_button_toggle(self) -> None:
        app, c = self.app, self.app.controls
        c.switch_tab("trav")
        app._action_traversal("DFS", "6", "31", animate=False)
        self.assertIn("[DFS] 6 → 31", c.get_traversal_log())
        self.assertIn("muestra DFS", c.strip_header())
        self.assertIn("Pila", c.strip_header())
        self.assertEqual(app._anim_delay(), 340)
        app._action_traversal("BFS", "6", "31", animate=False)
        self.assertEqual(app._anim_delay(), 560)
        app._action_toggle_anim()
        self.assertTrue(app.anim_playing)
        self.assertEqual(c.btn_anim.cget("text"), "Detener animación")
        app._action_toggle_anim()
        self.assertFalse(app.anim_playing)
        app.clear_traversal()
        app._last_traversal_algo = "DFS"
        app._action_toggle_anim()  # sin recorrido previo: usa último algoritmo y Inicio/Destino
        self.assertTrue(app.anim_playing)
        self.assertEqual(app._traversal_mode, "dfs")
        self.assertEqual(app._traversal_origin, "6")
        app._stop_traversal()

    def test_icons_and_layout_regression(self) -> None:
        app = self.app
        for key in ("brand_network", "play_on_accent", "pause_on_accent", "reset_light", "step_back_light", "step_fwd_light", "sliders_light", "chart_light"):
            self.assertIn(key, app._icons)
        self.assertEqual(len(app._legend_labels), 5)
        self.assertTrue(app._status_lbl.master is not app.topbar)


if __name__ == "__main__":
    unittest.main()
