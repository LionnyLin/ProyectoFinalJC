"""Regresión de la auditoría E3: liberar focos al navegar, DPI, hint, tooltip diferido, API y exportación."""

import os, tkinter as tk, unittest
from unittest import mock

from src.algorithms import trace_downstream, trace_upstream
from src.gui import app as gui_app
from src.gui.network_canvas import NetworkCanvas
from src.io.data_loader import load_dataset

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


def _has_display() -> bool:
    try:
        root = tk.Tk(); root.withdraw(); root.destroy()
        return True
    except tk.TclError:
        return False


class TestTraceCompat(unittest.TestCase):
    def test_trace_downstream_unpacks_like_main(self) -> None:
        g = load_dataset(DATA_XLSX).graph
        res = trace_downstream(g, g.source_ids()[0])
        nodes, pipes = trace_downstream(g, g.source_ids()[0])
        self.assertEqual(nodes, res.visited_order)
        self.assertEqual(pipes, res.traversed_edges)
        self.assertTrue(len(nodes) > 1 and len(pipes) > 0)


@unittest.skipUnless(_has_display(), "requiere display")
class TestAppGaps(unittest.TestCase):
    def setUp(self) -> None:
        self.app = gui_app.BicentenarioSewerApp(initial_data_path=DATA_XLSX)
        self.app.withdraw(); self.app.update_idletasks()
        self.app.controls.select_scenario_by_id(5)
        self.app.run_simulation()

    def tearDown(self) -> None:
        self.app._on_close()

    def _start(self) -> str:
        return self.app.dataset.graph.source_ids()[0]

    def test_bfs_closes_guided_tour(self) -> None:
        app = self.app
        app.tour.toggle(); self.assertTrue(app.tour.active)
        app._action_traversal("BFS", self._start(), None, False)
        self.assertFalse(app.tour.active)
        self.assertFalse(app.network_canvas._tour_active)

    def test_bfs_releases_basin_focus(self) -> None:
        app = self.app
        app.select_entity("node", "17"); app._action_toggle_basin()
        self.assertTrue(app.network_canvas._basin_active)
        app._action_traversal("BFS", self._start(), None, False)
        self.assertFalse(app.basin_focus_active)
        self.assertFalse(app.network_canvas._basin_active)

    def test_search_and_trace_release_focus(self) -> None:
        app = self.app
        for act in (lambda: app._action_search("17"), lambda: app._action_trace("17", False), lambda: app._action_toggle_anim()):
            app.select_entity("node", "17")
            if not app.basin_focus_active: app._action_toggle_basin()
            app.tour.toggle() if not app.tour.active else None
            act()
            self.assertFalse(app.tour.active)
            self.assertFalse(app.network_canvas._basin_active)
            app._stop_traversal()

    def test_toggle_basin_closes_tour_but_keeps_basin(self) -> None:
        app = self.app
        app.select_entity("node", "17")
        app.tour.toggle(); self.assertTrue(app.tour.active)
        app.select_entity("node", "17")
        app._action_toggle_basin()
        self.assertFalse(app.tour.active)
        self.assertTrue(app.network_canvas._basin_active)

    def test_dpi_wiring_defaults_at_1x(self) -> None:
        app = self.app
        self.assertEqual(app.network_canvas.dpi_scale, max(1.0, app._dpi_scale))
        self.assertEqual(int(app.charts_panel.fig.dpi), app._mpl_dpi)
        self.assertEqual(int(app.comparison_panel.charts.fig.dpi), app._mpl_dpi)
        if app._dpi_scale <= 1.0: self.assertEqual(app._mpl_dpi, 96)

    def test_comparison_hint_text(self) -> None:
        app = self.app
        app.run_comparison()
        txt = app.comparison_panel._hint.cget("text")
        self.assertTrue(txt.startswith("Al día · "), txt)
        self.assertIn(" ms)" if "(" in txt else " ms", txt)
        self.assertTrue(txt.endswith("Doble clic activa"))

    def test_export_docx_failure_falls_back_to_markdown(self) -> None:
        app = self.app
        app.run_comparison()
        out = os.path.join(os.path.dirname(DATA_XLSX), "x.docx")
        with mock.patch.object(gui_app.filedialog, "asksaveasfilename", return_value=out), \
             mock.patch.object(gui_app, "generate_docx_report", side_effect=RuntimeError("boom")), \
             mock.patch.object(gui_app, "generate_markdown_report", return_value="/tmp/x.md") as md, \
             mock.patch.object(gui_app.messagebox, "showwarning") as warn, \
             mock.patch.object(gui_app.messagebox, "showerror") as err:
            app._action_export("docx")
        self.assertEqual(md.call_args[0][3], os.path.splitext(out)[0] + ".md")
        warn.assert_called_once(); err.assert_not_called()

    def test_export_md_error_shows_dialog_and_csv_confirms(self) -> None:
        app = self.app
        app.run_comparison()
        with mock.patch.object(gui_app.filedialog, "asksaveasfilename", return_value="/tmp/x.md"), \
             mock.patch.object(gui_app, "generate_markdown_report", side_effect=OSError("disk")), \
             mock.patch.object(gui_app.messagebox, "showerror") as err:
            app._action_export("md")
        err.assert_called_once()
        with mock.patch.object(gui_app.filedialog, "askdirectory", return_value="/tmp/csvout"), \
             mock.patch.object(gui_app, "export_to_csv_dir"), \
             mock.patch.object(gui_app.messagebox, "showinfo") as info:
            app._action_export_csv()
        info.assert_called_once()


@unittest.skipUnless(_has_display(), "requiere display")
class TestCanvasGaps(unittest.TestCase):
    def setUp(self) -> None:
        self.ds = load_dataset(DATA_XLSX)
        self.root = tk.Tk(); self.root.geometry("1000x700+0+0")
        self.canvas = NetworkCanvas(self.root); self.canvas.pack(fill=tk.BOTH, expand=True)
        self.root.update(); self.canvas.set_graph(self.ds.graph); self.root.update()

    def tearDown(self) -> None:
        self.canvas.cancel_pending(); self.root.destroy()

    def test_tooltip_is_delayed_cancelable_and_hidden_on_leave(self) -> None:
        c = self.canvas
        nid = self.ds.graph.source_ids()[0]
        x, y = c._node_coords[nid]
        e = type("E", (), {})(); e.x, e.y = x, y
        c._on_motion(e)
        self.assertIsNone(c._hover_entity)          # aún no visible
        self.assertIsNotNone(c._tip_after)
        c._show_tooltip()                           # vence el retardo
        self.assertEqual(c._hover_entity, ("node", nid))
        c._hide_tooltip()
        self.assertIsNone(c._hover_entity); self.assertIsNone(c._tip_after)
        c._on_motion(e); c._cancel_tip()            # salir antes de 220 ms cancela
        self.assertIsNone(c._tip_after); self.assertIsNone(c._hover_entity)

    def test_dpi_scale_grows_node_radius(self) -> None:
        c = self.canvas
        r1 = c._node_r
        c.dpi_scale = 1.3; c.rebuild_geometry()
        self.assertGreaterEqual(c._node_r, r1)
        self.assertEqual(NetworkCanvas(self.root, dpi_scale=0.5).dpi_scale, 1.0)


if __name__ == "__main__":
    unittest.main()
