"""Pruebas del Inspector, intervenciones en vivo, composición por fuente, críticas y búsqueda (G8, G15, G16)."""

import os
import tkinter as tk
from tkinter import font as tkfont, ttk
import unittest
from types import SimpleNamespace

from src.gui import app as gui_app

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


def _has_display() -> bool:
    try:
        root = tk.Tk(); root.withdraw(); root.destroy()
        return True
    except tk.TclError:
        return False


class TestInspectorFeatures(unittest.TestCase):
    def setUp(self) -> None:
        if not _has_display():
            self.skipTest("Entorno headless sin display X11 disponible")
        self.app = gui_app.BicentenarioSewerApp(initial_data_path=DATA_XLSX)
        self.app.withdraw()
        self.app.controls.select_scenario_by_id(5)
        self.app.run_simulation()
        self.app.update()
        self.insp = self.app.inspector_tab
        self.g = self.app.dataset.graph

    def tearDown(self) -> None:
        if hasattr(self, "app") and self.app is not None:
            self.app._on_close()

    def _apply(self, pid: str, obst: float, diam=None) -> None:
        self.app.select_entity("pipe", pid)
        self.insp.var_obst.set(obst)
        self.insp.var_diam.set("Original" if diam is None else f'{diam:g}"')
        self.insp._emit_apply()
        self.app.update()

    def _busy_pipe(self) -> str:
        """Tubería con mayor pico de utilización (siempre tiene flujo)."""
        pk = self.app.result.peak_pipe_utilization
        return max(pk, key=pk.get)

    def test_obstruction_resimulates_keeps_baseline_and_isolates(self) -> None:
        pid = "P30"
        edge = self.g.get_pipe(pid)
        base = self.app.result
        self.assertIsNone(self.app.previous_result)
        self._apply(pid, 100.0)
        self.assertIn(pid, self.app.interventions)
        self.assertTrue(self.app.interventions[pid].is_closed)
        self.assertIs(self.app.result.config.interventions[pid], self.app.interventions[pid])
        self.assertIsNotNone(self.app.previous_result)
        self.assertIs(self.app.previous_result, base)  # la línea base original se conserva
        self.assertTrue(self.app.isolated_nodes)
        self.assertEqual(self.app.network_canvas._isolated_nodes, self.app.isolated_nodes)
        self.assertEqual(self.app.network_canvas._isolated_pipes, self.app.isolated_pipes)
        self.assertEqual(self.insp.entity_values()["Q conducido"].split()[0], "CERRADA")
        self.assertIn("Intervenciones", self.insp.summary_values())
        # segunda intervención: la línea base sigue siendo la original
        other = next(p.pipe_id for p in self.g.pipes() if p.pipe_id not in (pid,) and p.from_node != edge.from_node)
        self._apply(other, 50.0)
        self.assertIs(self.app.previous_result, base)
        self.assertEqual(set(self.app.interventions), {pid, other})

    def test_diameter_change_updates_effective_qmax(self) -> None:
        pid = "P30"
        self.app.select_entity("pipe", pid)
        self.app.update()
        q0 = float(self.insp.entity_values()["Q_max"].split()[0])
        bigger = self.g.get_pipe(pid).diameter_in * 2
        self._apply(pid, 0.0, bigger)
        vals = self.insp.entity_values()
        self.assertGreater(float(vals["Q_max"].split()[0]), q0)
        self.assertIn("Q_max base", vals)
        self.assertEqual(self.app.interventions[pid].diameter_in_override, bigger)
        # el selector queda sincronizado con la intervención vigente
        self.assertEqual(self.insp.var_diam.get(), f'{bigger:g}"')

    def test_restore_pipe_and_restore_network(self) -> None:
        self._apply("P30", 40.0)
        self._apply("P31", 60.0)
        self.assertEqual(len(self.app.interventions), 2)
        self.app.select_entity("pipe", "P30")
        self.assertEqual(self.insp.var_obst.get(), 40.0)  # sincroniza controles con la intervención vigente
        self.insp._cb("restore_pipe")
        self.assertEqual(set(self.app.interventions), {"P31"})
        self.assertIsNotNone(self.app.previous_result)
        self.insp._cb("restore_all")
        self.assertEqual(self.app.interventions, {})
        self.assertIsNone(self.app.previous_result)
        self.assertEqual(self.app.network_canvas._interventions, {})
        self.assertEqual(self.app.isolated_nodes, set())

    def test_invalid_intervention_shows_spanish_error(self) -> None:
        self.app.select_entity("pipe", "P30")
        self.insp.var_diam.set("abc")
        self.insp._emit_apply()
        self.assertIn("Diámetro inválido", self.insp.lbl_int_error.cget("text"))
        self.insp.var_diam.set('500"')
        self.insp._emit_apply()
        self.assertIn("120", self.insp.lbl_int_error.cget("text"))
        self.assertEqual(self.app.interventions, {})

    def test_comparison_is_invalidated_by_intervention_and_carries_it(self) -> None:
        self.app.run_comparison()
        self.assertIsNotNone(self.app.cached_comparisons)
        self._apply("P30", 100.0)
        self.assertIsNone(self.app.cached_comparisons)
        sums = self.app.run_comparison()
        self.assertTrue(all("P30" in s.result.config.interventions for s in sums))

    def test_load_data_clears_intervention_state(self) -> None:
        self._apply("P30", 100.0)
        self.app._action_toggle_basin()
        self.app.load_data(DATA_XLSX)
        self.assertEqual(self.app.interventions, {})
        self.assertIsNone(self.app.previous_result)
        self.assertFalse(self.app.basin_focus_active)
        self.assertFalse(self.app.network_canvas._basin_active)

    def test_basin_and_trace_toggles_set_and_clear_focus(self) -> None:
        cv = self.app.network_canvas
        self.app.select_entity("node", "17")
        self.app.update()
        self.assertTrue(self.insp.btn_up.winfo_manager() and self.insp.btn_down.winfo_manager())
        self.app._action_toggle_basin()
        self.assertTrue(cv._basin_active)
        self.assertIn("17", cv._basin_nodes); self.assertIn("31", cv._basin_nodes)
        self.app._action_toggle_basin()
        self.assertFalse(cv._basin_active)
        # selección de tubería: incluye la propia tubería
        self.app.select_entity("pipe", "P30")
        self.assertFalse(self.insp.btn_up.winfo_manager())
        self.app._action_toggle_basin()
        self.assertIn("P30", cv._basin_pipes)
        self.app.select_entity("node", "6")  # el foco sigue a la selección
        self.assertTrue(cv._basin_active); self.assertIn("6", cv._basin_nodes)
        self.app._clear_basin()
        # trazas aguas arriba / abajo
        self.app._action_toggle_inspector_trace("up")
        self.assertEqual(cv._traversal_mode, "upstream")
        self.assertEqual(self.app._inspector_trace, ("6", "up"))
        self.app._action_toggle_inspector_trace("down")
        self.assertEqual(cv._traversal_mode, "downstream")
        self.app._action_toggle_inspector_trace("down")
        self.assertIsNone(cv._traversal_mode)
        self.assertIsNone(self.app._inspector_trace)

    def test_escape_clears_basin_focus_selection_and_traversal(self) -> None:
        self.app.select_entity("node", "17")
        self.app._action_toggle_basin()
        self.app._action_toggle_inspector_trace("up")
        self.assertTrue(self.app.network_canvas._basin_active)
        self.app._shortcut_escape()
        self.assertFalse(self.app.network_canvas._basin_active)
        self.assertIsNone(self.app.selected_id)
        self.assertIsNone(self.app.network_canvas._traversal_mode)
        self.assertFalse(self.insp.btn_focus.winfo_manager())

    def test_source_composition_sums_to_100_and_follows_selection(self) -> None:
        self.app.go_to_step(30)
        self.app.select_entity("node", "31")
        self.app.update()
        shares = self.insp.source_shares
        self.assertGreater(len(shares), 1)
        self.assertAlmostEqual(sum(f for _, f in shares), 1.0, places=6)
        self.assertIn("%", self.insp.lbl_source_text.cget("text"))
        self.assertIn("PTAR", self.insp.lbl_source_entity.cget("text"))
        self.assertGreater(len(self.insp.source_bar.find_all()), 2)
        self.app.select_entity("pipe", self._busy_pipe())
        self.assertAlmostEqual(sum(f for _, f in self.insp.source_shares), 1.0, places=6)
        self.assertIn("Tramo", self.insp.lbl_source_entity.cget("text"))

    def test_source_composition_is_throttled_while_playing(self) -> None:
        self.app.select_entity("node", "31")
        self.app.go_to_step(10)
        calls = []
        import src.gui.app as mod
        orig = mod.compute_source_attribution
        mod.compute_source_attribution = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
        try:
            self.app.is_playing = True
            for step in range(11, 20):
                self.app.go_to_step(step)
            self.assertLessEqual(len(calls), 1)
            self.app.is_playing = False
            self.app._stop_playback()
            self.assertGreaterEqual(len(calls), 1)  # al pausar se recalcula con el paso vigente
        finally:
            mod.compute_source_attribution = orig

    def test_summary_block_and_pipe_node_details(self) -> None:
        self.app.go_to_step(40)
        self.app.select_entity("pipe", self._busy_pipe())
        summ = self.insp.summary_values()
        for key in ("Escenario", "Cuenca", "Ingreso / Fuent.", "Entrada acum.", "Descarga PTAR 31 (pico)", "Pozos / Tránsito",
                    "Rebose superf.", "Error balance", "Críticas (>75–100%)", "Sobrec. (>100%)"):
            self.assertIn(key, summ)
            self.assertNotEqual(summ[key], "—")
        self.assertNotIn("Intervenciones", summ)
        ent = self.insp.entity_values()
        for key in ("De → A", "Q_max", "Tiempo tránsito", "Q demanda", "Utilización", "Pico utilización", "Estrés >100%"):
            self.assertIn(key, ent)
        self.assertIn("×Qmax", ent["Q demanda"])
        self.app.select_entity("node", "31")
        ent = self.insp.entity_values()
        for key in ("Tipo", "Entradas", "Cap. saliente", "Q ent. / sal.", "Vol. en pozo", "Rebose sup."):
            self.assertIn(key, ent)

    def test_critical_filters_are_consistent_with_snapshot(self) -> None:
        step = next(i for i, s in enumerate(self.app.result.snapshots) if s.near_capacity_pipe_ids and s.overloaded_pipe_ids)
        self.app.go_to_step(step)
        self.app.notebook.select(1)
        self.app.update()
        snap, tab = self.app.result.snapshots[step], self.app.critical_tab
        n_all = len(snap.pipe_states)
        counts = {}
        for mode in ("Todas", "Resto (≤75%)", "Críticas (>75–100%)", "Sobrec. (>100%)"):
            tab._filter_var.set(mode)
            tab._render()
            counts[mode] = len(tab._tree.get_children())
            utils = [float(str(tab._tree.item(i, "values")[5]).rstrip("%")) for i in tab._tree.get_children()]
            if mode.startswith("Resto"): self.assertTrue(all(u <= 75.0 for u in utils))
            if mode.startswith("Cr"): self.assertTrue(all(75.0 < u <= 100.0 for u in utils))
            if mode.startswith("Sobrec"): self.assertTrue(all(u > 100.0 for u in utils))
        self.assertEqual(counts["Todas"], n_all)
        self.assertEqual(counts["Críticas (>75–100%)"], len(snap.near_capacity_pipe_ids))
        self.assertEqual(counts["Sobrec. (>100%)"], len(snap.overloaded_pipe_ids))
        self.assertEqual(counts["Resto (≤75%)"] + counts["Críticas (>75–100%)"] + counts["Sobrec. (>100%)"], n_all)
        self.assertEqual(self.app.notebook.tab(self.app.critical_tab, "text"), "Tuberías Críticas")

    def test_critical_closed_pipe_reports_closed_state(self) -> None:
        self._apply("P30", 100.0)
        self.app.go_to_step(30)
        self.app.notebook.select(1)
        self.app.update()
        tab = self.app.critical_tab
        iid = tab._pipe_to_iid["P30"]
        self.assertIn(tab._tree.item(iid, "values")[7], ("Cerrada 100%", "Cerr."))
        self.assertEqual(next(v for v in tab._rows_full if v[1] == "P30")[7], "Cerrada 100%")

    def test_double_click_on_critical_row_moves_camera(self) -> None:
        self.app.go_to_step(30)
        self.app.notebook.select(1)
        self.app.update()
        tab, cv = self.app.critical_tab, self.app.network_canvas
        cv.reset_view()
        before = (cv._zoom, cv._pan_x, cv._pan_y)
        pid = next(p for p in tab._pipe_to_iid if p != "P1")
        tab.select_pipe(pid)
        tab._on_double_click(SimpleNamespace(y=0))
        self.app.update()
        self.assertEqual(self.app.selected_id, pid)
        self.assertNotEqual((cv._zoom, cv._pan_x, cv._pan_y), before)

    def test_substring_search_selects_first_node_and_centers(self) -> None:
        cv = self.app.network_canvas
        cv.reset_view()
        before = (cv._zoom, cv._pan_x, cv._pan_y)
        self.app._action_search("PTAR")  # solo coincide con la etiqueta «31 (PTAR)»
        self.app.update()
        self.assertEqual((self.app.selected_kind, self.app.selected_id), ("node", "31"))
        self.assertNotEqual((cv._zoom, cv._pan_x, cv._pan_y), before)
        self.assertIn("Nodo 31", self.app.controls._search_feedback.cget("text"))

    def test_substring_search_reports_count_and_prefers_nodes(self) -> None:
        self.app._action_search("(S)")
        self.assertEqual(self.app.selected_kind, "node")
        self.assertRegex(self.app.controls._search_feedback.cget("text"), r"\d+ coincidencias")
        self.app._action_search("P3")  # subcadena de tuberías (ninguna coincide exacta)
        self.assertEqual(self.app.selected_kind, "pipe") if not self.app.dataset.graph.has_node("P3") else None

    def test_exact_search_still_wins_and_centers(self) -> None:
        cv = self.app.network_canvas
        cv.reset_view()
        before = (cv._zoom, cv._pan_x, cv._pan_y)
        self.app._action_search("p30")
        self.assertEqual((self.app.selected_kind, self.app.selected_id), ("pipe", "P30"))
        self.assertIn("P30", self.app.controls._search_feedback.cget("text"))
        self.assertNotEqual((cv._zoom, cv._pan_x, cv._pan_y), before)


class TestInspectorLayoutRegressions(unittest.TestCase):
    """Regresiones visuales: ranuras vacías, indicador de masa compacto y columnas de críticas."""

    def setUp(self) -> None:
        if not _has_display():
            self.skipTest("Entorno headless sin display X11 disponible")
        self.app = gui_app.BicentenarioSewerApp(initial_data_path=DATA_XLSX)
        self.app.withdraw()
        self.app.controls.select_scenario_by_id(5)
        self.app.run_simulation(auto_play=False)
        self.app.update()

    def tearDown(self) -> None:
        self.app._on_close()

    def _assert_slots_collapsed(self) -> None:
        tab = self.app.inspector_tab
        self.app.update()
        for slot in (tab._actions_slot, tab._ent_slot, tab._interv_slot, tab._source_slot):
            if not slot.pack_slaves():
                self.assertFalse(slot.winfo_manager(), "ranura vacía debe salir del layout")
                self.assertLessEqual(slot.winfo_height() if slot.winfo_manager() else 0, 2)

    def test_empty_inspector_slots_collapse_after_deselect_and_kind_change(self) -> None:
        app, tab = self.app, self.app.inspector_tab
        app.select_entity("pipe", "P29"); app.update()
        self.assertTrue(tab._interv_slot.winfo_manager() and tab._source_slot.winfo_manager())
        app.select_entity(None, None)
        self._assert_slots_collapsed()
        self.assertFalse(tab._actions_slot.winfo_manager())
        self.assertFalse(tab._interv_slot.winfo_manager())
        self.assertFalse(tab._source_slot.winfo_manager())
        app.select_entity("pipe", "P29"); app.update()
        app.select_entity("node", app.dataset.graph.node_ids()[3]); self.app.update()
        self.assertFalse(tab._interv_slot.winfo_manager(), "un nodo no muestra la tarjeta de intervención")
        self._assert_slots_collapsed()
        order = [str(w) for w in tab._inner.pack_slaves()]
        slots = [str(sl) for sl in (tab._actions_slot, tab._ent_slot, tab._source_slot)]
        self.assertEqual([o for o in order if o in slots], slots, "las ranuras conservan el orden")
        app.select_entity(None, None); app.update()
        self.assertLessEqual(tab._inner.winfo_reqheight(), 600)

    def test_mass_indicator_never_exceeds_available_width(self) -> None:
        app = self.app
        app.go_to_step(10)
        for width in (330, 420, 520, 640, 900):
            app._on_player_configure(type("E", (), {"width": width})())
            app._update_mass_label()
            need = tkfont.Font(font=app.fonts["mono_bold"]).measure(app._mass_lbl.cget("text")) + 2 * (8 + 1 + 2)
            avail = app._mass_available_width()
            self.assertTrue(need <= avail or app._mass_lbl.cget("text") in ("OK", "ERROR"), (width, need, avail))
        app._on_player_configure(type("E", (), {"width": 900})())
        self.assertTrue(app._mass_lbl.cget("text").startswith("Balance masa OK"))
        row1 = app._mass_lbl.master
        app._on_player_configure(type("E", (), {"width": 460})())
        self.assertNotIn("Balance", app._mass_lbl.cget("text"))
        used = sum(w.winfo_reqwidth() for w in row1.pack_slaves() if w is not app._mass_lbl)
        self.assertLessEqual(app._mass_lbl.winfo_reqwidth() + used, 460)

    def test_critical_columns_fit_longest_content(self) -> None:
        app = self.app
        tab = app.critical_tab
        app.go_to_step(40); app.notebook.select(1); app.update()
        longest = max((v[5] for v in tab._rows_full), key=len)
        body = tkfont.Font(font=ttk.Style().lookup("Treeview", "font") or "TkDefaultFont")
        self.assertGreaterEqual(int(tab._tree.column("Util. %", "width")), body.measure(longest) + 8)
        self.assertGreaterEqual(int(tab._tree.column("Util. %", "minwidth")), body.measure(longest) + 8)


if __name__ == "__main__":
    unittest.main()
