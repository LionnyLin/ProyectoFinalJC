"""Pruebas de los paneles de Evolución (ChartsPanel) y Comparación (ComparisonPanel) con datos reales."""

import os
import tkinter as tk
import unittest
from types import SimpleNamespace

from src.gui import theme
from src.gui.charts_panel import ChartsPanel, ComparisonChartsPanel
from src.gui.comparison_panel import ComparisonPanel
from src.io.data_loader import load_dataset
from src.simulation.comparison import compare_all_scenarios
from src.simulation.engine import SewerSimulationEngine
from src.simulation.models import PipeIntervention, SimulationConfig, compute_symlog_ticks

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


def _has_display() -> bool:
    try:
        r = tk.Tk(); r.withdraw(); r.destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(_has_display(), "requiere display")
class _PanelBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset(DATA_XLSX)
        cls.graph = cls.dataset.graph
        cls.engine = SewerSimulationEngine(cls.graph, cls.dataset.basin)
        cls.cfg = SimulationConfig(5, "Extreme rain", 100.0, duration_min=90.0, storm_duration_min=60.0)
        cls.base = cls.engine.run(cls.cfg)
        cls.after = cls.engine.run(SimulationConfig(
            5, "Extreme rain", 100.0, duration_min=90.0, storm_duration_min=60.0,
            interventions={"P31": PipeIntervention("P31", 50.0)}))
        cls.comps = compare_all_scenarios(cls.dataset, cls.cfg)
        cls.root = tk.Tk()
        cls.root.geometry("520x760+0+0")
        cls.fonts = theme.resolve_fonts(cls.root)
        theme.apply_ttk_theme(cls.root, cls.fonts)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def _pack(self, panel: tk.Widget) -> None:
        panel.pack(fill=tk.BOTH, expand=True)
        self.root.update()
        self.addCleanup(panel.destroy)


class TestChartsPanel(_PanelBase):
    def test_legacy_calls_still_work(self) -> None:
        p = ChartsPanel(self.root, self.fonts)
        self._pack(p)
        p.set_result(self.base, "P30", is_visible=True)
        p.update_cursor(10.0, is_visible=True)
        p.mark_visible()
        p._cancel_cursor_timer()
        self.assertEqual(p._focus_pipe, "P30")

    def test_before_curve_only_with_baseline_and_banner(self) -> None:
        p = ChartsPanel(self.root, self.fonts)
        self._pack(p)
        p.set_result(self.base, None, graph=self.graph)
        labels = [t.get_text() for t in p.ax_hydro.get_legend().get_texts()]
        self.assertFalse(any("Antes" in t for t in labels))
        self.assertIn("Entrada total", " ".join(labels))
        self.assertFalse(p._banner_visible)
        p.set_result(self.after, "P31", previous_result=self.base, graph=self.graph)
        labels = [t.get_text() for t in p.ax_hydro.get_legend().get_texts()]
        self.assertTrue(any("Antes" in t for t in labels))
        self.assertTrue(p._banner_visible)
        self.assertIn("P31", p._lbl_impact_title.cget("text"))
        self.assertIn("Obstr. 50%", p._lbl_impact_title.cget("text"))
        self.assertIn("PTAR", p._lbl_impact_metrics.cget("text"))
        util = [t.get_text() for t in p.ax_util.get_legend().get_texts()]
        self.assertTrue(any("Antes" in t for t in util))
        p.set_result(self.after, "P31", previous_result=None)
        self.assertFalse(p._banner_visible)

    def test_top3_vs_selected_pipe(self) -> None:
        p = ChartsPanel(self.root, self.fonts)
        self._pack(p)
        p.set_result(self.base, None)
        self.assertEqual(len(p._focus_pipes()), 3)
        self.assertIn("Top 3", p.ax_util.get_title(loc="left"))
        ranked = sorted(self.base.peak_pipe_utilization.items(), key=lambda kv: kv[1], reverse=True)
        self.assertEqual(p._focus_pipes()[0], ranked[0][0])
        p.set_result(self.base, "P30")
        self.assertEqual(p._focus_pipes(), ["P30"])
        self.assertIn("P30", p.ax_util.get_title(loc="left"))

    def test_symlog_axis_and_ticks(self) -> None:
        p = ChartsPanel(self.root, self.fonts)
        self._pack(p)
        top = max(self.base.peak_pipe_utilization.values())
        self.assertGreater(top, 250.0)
        p.set_result(self.base, None)
        self.assertEqual(p.ax_util.get_yscale(), "symlog")
        self.assertEqual(list(p.ax_util.get_yticks()), compute_symlog_ticks(top))
        low = self.engine.run(SimulationConfig(2, "Light rain", 0.1, duration_min=60.0, storm_duration_min=30.0))
        p.set_result(low, None)
        self.assertEqual(p.ax_util.get_yscale(), "linear")

    def test_longitudinal_profile_route_and_modes(self) -> None:
        p = ChartsPanel(self.root, self.fonts)
        self._pack(p)
        p.set_result(self.base, None, graph=self.graph)
        p.set_subtab("profile")
        self.root.update()
        route = p._resolve_route()
        self.assertTrue(route)
        self.assertEqual(route[-1].to_node, "31")
        p.set_result(self.base, "P10", graph=self.graph)
        self.assertEqual(p._resolve_route()[-1].to_node, "31")
        self.assertIn("P10", [r.pipe_id for r in p._resolve_route()])
        p.set_result(self.base, None, graph=self.graph, focus_node_id="N")
        self.assertEqual(p._resolve_route()[-1].to_node, "31")
        n_texts = len(p.ax_profile.texts)
        self.assertGreaterEqual(n_texts, len(route) - 2)
        self.assertIn("% Uso", p.ax_profile.get_ylabel())
        p.set_profile_mode("flow")
        self.assertIn("Caudal", p.ax_profile.get_ylabel())
        p.set_profile_mode("pct")
        self.assertIn("% Uso", p.ax_profile.get_ylabel())
        p.set_profile_mode("invalido")
        self.assertEqual(p._profile_mode, "pct")
        # paso con sobrecarga -> anotación de demanda
        peak_idx = max(range(len(self.base.snapshots)), key=lambda i: self.base.snapshots[i].total_sink_discharge_m3s)
        p.update_cursor(self.base.snapshots[peak_idx].time_min, step_index=peak_idx)
        p._redraw_profile()
        self.assertTrue(any("Dem." in t.get_text() for t in p.ax_profile.texts))
        self.assertIn(f"t={self.base.snapshots[peak_idx].time_min:.0f}", p.ax_profile.get_title(loc="left"))

    def test_profile_step_index_fallback_to_nearest_time(self) -> None:
        p = ChartsPanel(self.root, self.fonts)
        self._pack(p)
        p.set_result(self.base, None, graph=self.graph)
        p.update_cursor(25.2)
        self.assertEqual(p._step_index, self.base.snapshots[p._step_index].step_index)
        self.assertAlmostEqual(self.base.snapshots[p._step_index].time_min, 25.0)

    def test_cursor_moves_without_full_redraw(self) -> None:
        p = ChartsPanel(self.root, self.fonts)
        self._pack(p)
        p.set_result(self.base, None)
        cur = p._cursor_hydro
        p.update_cursor(33.0)
        self.root.update()
        self.assertEqual(list(p._cursor_hydro.get_xdata()), [33.0, 33.0])
        self.assertEqual(list(p._cursor_util.get_xdata()), [33.0, 33.0])
        self.assertIs(p._cursor_hydro, cur)
        self.assertFalse(p._dirty)

    def test_deferred_render_when_hidden(self) -> None:
        p = ChartsPanel(self.root, self.fonts)
        self._pack(p)
        p.set_result(None, None, is_visible=False)
        p.set_result(self.base, "P30", is_visible=False)
        self.assertTrue(p._dirty)
        self.assertIsNone(p._cursor_hydro)
        p.update_cursor(40.0, is_visible=False)
        self.assertTrue(p._cursor_dirty)
        p.mark_visible()
        self.assertFalse(p._dirty)
        self.assertIsNotNone(p._cursor_hydro)
        self.assertEqual(list(p._cursor_hydro.get_xdata()), [40.0, 40.0])
        p.set_subtab("profile")
        p.set_result(self.base, None, graph=self.graph, is_visible=False)
        self.assertTrue(p._profile_dirty)
        p.mark_visible()
        self.assertFalse(p._profile_dirty)
        self.assertGreater(len(p.ax_profile.patches), 0)


class TestComparisonPanel(_PanelBase):
    def _panel(self):
        calls = {"recalc": 0, "activated": []}
        holder = {}

        def recalc():
            calls["recalc"] += 1
            holder["p"].set_comparisons(self.comps, elapsed_ms=123.0, is_visible=True)

        p = ComparisonPanel(self.root, self.fonts, recalc, calls["activated"].append)
        holder["p"] = p
        self._pack(p)
        return p, calls

    def test_dirty_flow_and_auto_recalc_on_visible(self) -> None:
        p, calls = self._panel()
        p.set_comparisons(None, is_visible=False)
        p.mark_visible()                       # sin datos -> recalcula
        self.assertEqual(calls["recalc"], 1)
        self.assertFalse(p.is_dirty)
        self.assertEqual(len(p.tree.get_children()), 5)
        self.assertNotIn("*", p._btn.cget("text"))
        p.mark_visible()                       # al día -> no recalcula
        self.assertEqual(calls["recalc"], 1)
        p.invalidate()
        self.assertTrue(p.is_dirty)
        self.assertIn("*", p._btn.cget("text"))
        self.assertEqual(p._btn.cget("bg"), theme.ACCENT_PRIMARY)
        p.mark_visible()
        self.assertEqual(calls["recalc"], 2)
        self.assertFalse(p.is_dirty)
        self.assertIn("123 ms", p._hint.cget("text"))
        self.root.update()
        self.assertIn("123 ms", p._hint.cget("text"))   # no se sobrescribe al redimensionar
        p.set_dirty(True)
        self.assertTrue(p.is_dirty)
        p._btn.invoke()
        self.assertEqual(calls["recalc"], 3)

    def test_deferred_render_when_hidden(self) -> None:
        p, calls = self._panel()
        p.set_comparisons(self.comps, elapsed_ms=50.0, is_visible=False)
        self.assertEqual(len(p.tree.get_children()), 0)
        p.mark_visible()
        self.assertEqual(calls["recalc"], 0)
        self.assertEqual(len(p.tree.get_children()), 5)

    def test_table_columns_scrollbars_and_activation(self) -> None:
        p, calls = self._panel()
        p.set_comparisons(self.comps, elapsed_ms=50.0)
        cols = p.tree["columns"]
        self.assertGreaterEqual(len(cols), 8)
        heads = [p.tree.heading(c, "text") for c in cols]
        self.assertIn("Rebose (m³)", heads)
        self.assertIn("Razón Máx", heads)
        self.assertTrue(p._xscroll.winfo_exists() and p._yscroll.winfo_exists())
        self.assertEqual(p._xscroll.grid_info()["row"], 1)
        # el nombre del escenario más largo cabe en su columna
        longest = max((p.tree.set(i, "esc") for i in p.tree.get_children()), key=len)
        self.assertGreaterEqual(int(p.tree.column("esc", "width")), p._cell_font.measure(longest))
        first = p.tree.get_children()[2]
        p.tree.selection_set(first)
        p._on_row_activate(None)
        self.assertEqual(calls["activated"], [self.comps[2].scenario_id])
        self.assertEqual(p.tree.set(first, "flood").replace(",", "").split(".")[0].isdigit(), True)

    def test_shift_wheel_scrolls_horizontally(self) -> None:
        p, _ = self._panel()
        p.set_comparisons(self.comps)
        self.root.update()
        total = sum(int(p.tree.column(c, "width")) for c in p.tree["columns"])
        if total <= p.tree.winfo_width():       # forzar contenido más ancho que el visor
            p.tree.column("flood", width=p.tree.winfo_width() + 400)
            self.root.update()
        self.assertEqual(p.tree.xview()[0], 0.0)
        self.assertEqual(p._on_shift_wheel(SimpleNamespace(delta=-120)), "break")
        self.root.update()
        self.assertGreater(p.tree.xview()[0], 0.0)
        p._on_shift_wheel(SimpleNamespace(delta=120))
        self.root.update()

    def test_metric_selector_and_reflow(self) -> None:
        p, _ = self._panel()
        p.set_comparisons(self.comps)
        ch = p.charts
        self.assertEqual(ch.metric_mode, "flood")
        self.assertIn("Rebose", ch.ax_series.get_title(loc="left"))
        self.assertEqual(len(ch.ax_series.lines), 5)
        ch.set_metric_mode("ptar")
        self.assertIn("PTAR", ch.ax_series.get_title(loc="left"))
        self.assertEqual(len(ch.ax_series.lines), 5)
        ch.set_metric_mode("nada")
        self.assertEqual(ch.metric_mode, "ptar")
        legend = [t.get_text() for t in ch.ax_bar.get_legend().get_texts()]
        self.assertEqual(legend, ["Críticas (>75–100%)", "Sobrec. (>100%)"])
        self.assertEqual(len(ch.ax_bar.patches), 10)
        self.assertEqual(ComparisonChartsPanel.layout_for(400, 400), "stacked")
        self.assertEqual(ComparisonChartsPanel.layout_for(400, 344), "stacked")
        self.assertEqual(ComparisonChartsPanel.layout_for(800, 400), "side")
        ch._reflow(800, 400)
        self.assertEqual(ch.layout_mode, "side")
        self.assertEqual(ch.ax_bar.get_subplotspec().colspan, range(0, 1))
        self.assertEqual(len(ch.ax_series.lines), 5)
        ch._reflow(400, 500)
        self.assertEqual(ch.layout_mode, "stacked")
        self.assertEqual(ch.ax_series.get_subplotspec().rowspan, range(1, 2))


if __name__ == "__main__":
    unittest.main()
