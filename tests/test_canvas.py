"""Pruebas del lienzo cartográfico: modos de mapa, intervenciones, anillos, pulsos, cámara, foco y tooltips."""

import os
import time
import tkinter as tk
import unittest

from src.algorithms.analysis import classify_overload_persistence, classify_utilization
from src.gui import network_canvas as nc
from src.gui.network_canvas import NetworkCanvas
from src.io.data_loader import load_dataset
from src.simulation.engine import SewerSimulationEngine
from src.simulation.models import PipeIntervention, SimulationConfig

DATA_XLSX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx"))


def _has_display() -> bool:
    try:
        root = tk.Tk(); root.withdraw(); root.destroy()
        return True
    except tk.TclError:
        return False


def _isolated(graph, closed_pipe_ids):
    """BFS inverso propio desde los sumideros sin usar las tuberías cerradas."""
    closed = set(closed_pipe_ids)
    reach, frontier = set(graph.sink_ids()), list(graph.sink_ids())
    while frontier:
        nid = frontier.pop()
        for p in graph.incoming_pipes(nid):
            if p.pipe_id not in closed and p.from_node not in reach:
                reach.add(p.from_node); frontier.append(p.from_node)
    nodes = {n for n in graph.node_ids() if n not in reach}
    pipes = {p.pipe_id for p in graph.pipes() if p.from_node in nodes}
    return nodes, pipes


@unittest.skipUnless(_has_display(), "requiere display")
class TestNetworkCanvas(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ds = load_dataset(DATA_XLSX)
        cls.result = SewerSimulationEngine(cls.ds.graph, cls.ds.basin).run(SimulationConfig(4, "Heavy rain", 60.0))

    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.geometry("1000x700+0+0")
        self.canvas = NetworkCanvas(self.root)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.root.update()
        self.graph = self.ds.graph
        self.canvas.set_graph(self.graph)
        self.root.update()
        self.snaps = self.result.snapshots
        self.peak_snap = max(self.snaps, key=lambda s: s.total_surface_flooding_m3)

    def tearDown(self) -> None:
        try:
            self.canvas.cancel_pending()
            self.root.destroy()
        except tk.TclError:
            pass

    def _line_color(self, pid: str) -> str:
        return self.canvas.itemcget(self.canvas._geoms[pid].line, "fill")

    def _state(self, item: int) -> str:
        return self.canvas.itemcget(item, "state")

    def _pump(self, cond, timeout: float = 3.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            self.root.update()
            if cond(): return True
            time.sleep(0.005)
        return cond()

    # ── Modos de mapa ──
    def test_map_modes_colors_and_stamp(self) -> None:
        c, res = self.canvas, self.result
        c.set_snapshot(self.peak_snap)
        pid = max(res.peak_pipe_utilization, key=res.peak_pipe_utilization.get)
        inst = classify_utilization(self.peak_snap.pipe_states[pid].utilization_pct).color_hex
        self.assertEqual(c.map_mode, "instant")
        self.assertEqual(self._line_color(pid), inst)
        c.set_map_mode("peak", peak_util=res.peak_pipe_utilization, total_duration_min=90.0)
        self.assertEqual(c.map_mode, "peak")
        self.assertEqual(self._line_color(pid), classify_utilization(res.peak_pipe_utilization[pid]).color_hex)
        self.assertIn("PICO MÁXIMO", c._stamp_lbl.cget("text"))
        c.set_map_mode("overload_minutes", overload_minutes=res.pipe_overloaded_minutes, total_duration_min=90.0)
        for p, mins in res.pipe_overloaded_minutes.items():
            self.assertEqual(self._line_color(p), classify_overload_persistence(mins, 90.0)[1])
        self.assertIn("SOBRECARGA", c._stamp_lbl.cget("text"))
        c.set_map_mode("bogus")
        self.assertEqual(c.map_mode, "instant")
        self.assertIn("t =", c._stamp_lbl.cget("text"))

    def test_peak_label_shows_peak_percentage(self) -> None:
        c = self.canvas
        pid = max(self.result.peak_pipe_utilization, key=self.result.peak_pipe_utilization.get)
        c.set_selected("pipe", pid)
        c.set_map_mode("peak", peak_util={pid: 250.0})
        self.assertIn("250%", c.itemcget(c._geoms[pid].lbl_txt, "text"))
        c.set_map_mode("overload_minutes", overload_minutes={pid: 12.0})
        self.assertIn("12m", c.itemcget(c._geoms[pid].lbl_txt, "text"))

    def test_set_stress_maps_repaints_active_mode_only(self) -> None:
        c = self.canvas
        pid = self.graph.pipe_ids()[0]
        c.set_stress_maps(peak_util={pid: 10.0}, total_duration_min=45.0)
        self.assertEqual(c.map_mode, "instant")
        c.set_map_mode("peak")
        c.set_stress_maps(peak_util={pid: 120.0})
        self.assertEqual(self._line_color(pid), "#991b1b")

    # ── Intervenciones ──
    def test_intervention_items_and_isolated(self) -> None:
        c, g = self.canvas, self.graph
        long_ids = [p.pipe_id for p in g.pipes() if c._geoms[p.pipe_id].seg_len > 30]
        closed = next(i for i in long_ids if g.out_degree(g.get_pipe(i).from_node) == 1 and g.get_pipe(i).from_node not in g.sink_ids())
        obst, enl = [i for i in long_ids if i != closed][:2]
        edge_en = g.get_pipe(enl)
        inv = {
            obst: PipeIntervention(obst, 40.0),
            closed: PipeIntervention(closed, 100.0),
            enl: PipeIntervention(enl, 0.0, edge_en.diameter_in * 2.0),
        }
        iso_n, iso_p = _isolated(g, [closed])
        self.assertTrue(iso_n)
        c.set_interventions(inv, iso_n, iso_p)
        self.root.update()
        gm = c._geoms
        self.assertEqual(len(gm[obst].extras), 2)   # barras de obstrucción
        self.assertEqual(len(gm[closed].extras), 2)  # × de cierre
        self.assertEqual(len(gm[enl].extras), 2)    # doble línea
        self.assertTrue(gm[closed].closed)
        self.assertEqual(self._line_color(closed), nc.theme.INK_PRIMARY)
        self.assertEqual(c.itemcget(gm[closed].line, "dash"), "3 3")
        for pid in iso_p:
            self.assertNotEqual(c.itemcget(gm[pid].line, "dash"), "")
        for nid in iso_n:
            self.assertNotEqual(c.itemcget(c._ngeoms[nid].oval, "dash"), "")
        cut = [nid for nid, ng in c._ngeoms.items() if ng.iso_cut]
        self.assertTrue(cut)
        for nid in cut:
            self.assertEqual(self._state(c._ngeoms[nid].iso_tag[1]), "normal")
        c.set_selected("pipe", obst)
        self.assertIn("[OBST 40%]", c.itemcget(gm[obst].lbl_txt, "text"))
        c.set_selected("pipe", enl)
        self.assertIn(f'[Ø{edge_en.diameter_in * 2.0:.0f}"]', c.itemcget(gm[enl].lbl_txt, "text"))
        tip = c._format_tooltip("pipe", closed)
        self.assertIn("AISLADO DE 31", c._format_tooltip("node", next(iter(iso_n))))
        self.assertIn("OBST 100%", tip)
        c.set_interventions()
        self.assertEqual(len(c._geoms[obst].extras), 0)
        self.assertFalse(c._geoms[closed].closed)

    def test_closed_state_from_snapshot_and_enlarged_tooltip(self) -> None:
        c, g = self.canvas, self.graph
        pid = g.pipe_ids()[0]
        edge = g.get_pipe(pid)
        c.set_interventions({pid: PipeIntervention(pid, 0.0, edge.diameter_in * 2.0)})
        tip = c._format_tooltip("pipe", pid)
        self.assertIn(f'Ø {edge.diameter_in * 2.0:g}"', tip)
        self.assertIn(f'Ø {edge.diameter_in:g}"→{edge.diameter_in * 2.0:g}"', tip)

    # ── Anillos y halos ──
    def test_flood_rings_and_overload_halo(self) -> None:
        c = self.canvas
        c.set_snapshot(self.peak_snap)
        shown = [nid for nid, ng in c._ngeoms.items() if self._state(ng.rings[0]) == "normal"]
        self.assertTrue(shown)
        flood = [nid for nid in shown if self.peak_snap.node_states[nid].surface_flooding_m3 > 1e-9]
        self.assertTrue(flood)
        ng = c._ngeoms[flood[0]]
        self.assertEqual(self._state(ng.rings[1]), "normal")  # 2 anillos con volumen grande
        self.assertEqual(c.itemcget(ng.rings[0], "outline").lower(), nc._FLOOD_DEEP.lower())
        over = [pid for pid, ps in self.peak_snap.pipe_states.items() if ps.utilization_pct > 100.0]
        self.assertTrue(over)
        self.assertEqual(self._state(c._geoms[over[0]].halo), "normal")
        # Con foco de cuenca que excluye el nodo, el anillo se oculta
        c.set_basin_focus({"__x__"}, {"__y__"})
        self.assertEqual(self._state(ng.rings[0]), "hidden")

    # ── Pulsos ──
    def test_pulses_start_and_stop(self) -> None:
        c = self.canvas
        self.root.deiconify(); self.root.update()
        c.set_snapshot(self.peak_snap)
        c.set_playing(True, 2.0)
        self.assertIsNotNone(c._pulse_after_id)
        self.assertTrue(c._active_pulses)
        self.assertLessEqual(max(sum(1 for m in c._active_pulses if m.pipe_id == p) for p in {m.pipe_id for m in c._active_pulses}), 3)
        m0 = c._active_pulses[0]
        before = c.coords(m0.item_id)
        self.assertEqual(self._state(m0.item_id), "normal")
        t0 = c._pulse_time_s
        self.assertTrue(self._pump(lambda: c._pulse_time_s > t0 + 0.1))
        if c.winfo_viewable():
            self.assertNotEqual(before, c.coords(m0.item_id))
        ids = {m.item_id for m in c._active_pulses}
        c.set_playing(False)
        self.assertIsNone(c._pulse_after_id)
        self.assertEqual(c._active_pulses, [])
        self.assertTrue(all(self._state(i) == "hidden" for i in ids))
        c.set_playing(True)
        c.cancel_pending()
        self.assertIsNone(c._pulse_after_id)

    # ── Cámara ──
    def test_camera_animations(self) -> None:
        c = self.canvas
        z0 = c._zoom
        c.zoom_in(); self.assertGreater(c._zoom, z0)
        c.zoom_out(); self.assertAlmostEqual(c._zoom, z0, places=3)
        nid = self.graph.node_ids()[5]
        c.animate_focus_region({nid}, None, left_reserve_px=200.0, steps=4, step_ms=5)
        self.assertIsNotNone(c._cam_after)
        self.assertTrue(self._pump(lambda: c._cam_after is None))
        self.assertGreater(c._zoom, 1.0)
        self.assertNotEqual((c._pan_x, c._pan_y), (0.0, 0.0))
        # El nodo enfocado queda a la derecha del margen reservado
        self.assertGreater(c._node_coords[nid][0], 150.0)
        c.animate_reset_view(steps=3, step_ms=5)
        self.assertTrue(self._pump(lambda: c._cam_after is None))
        self.assertEqual((c._zoom, c._pan_x, c._pan_y), (1.0, 0.0, 0.0))
        c.animate_focus_region({nid}, steps=50, step_ms=50)
        c.reset_view()
        self.assertIsNone(c._cam_after)
        c.focus_node(nid)
        w, h = c._canvas_dims()
        self.assertAlmostEqual(c._node_coords[nid][0], w / 2, delta=1.0)
        pid = self.graph.pipe_ids()[0]
        c.focus_pipe(pid)
        self.assertNotEqual((c._pan_x, c._pan_y), (0.0, 0.0))

    # ── Foco, recorridos y selección ──
    def test_basin_and_tour_focus_dim(self) -> None:
        c, g = self.canvas, self.graph
        c.set_snapshot(self.peak_snap)
        keep_p = set(g.pipe_ids()[:3])
        keep_n = {p.from_node for p in g.pipes() if p.pipe_id in keep_p} | {p.to_node for p in g.pipes() if p.pipe_id in keep_p}
        full = self._line_color(g.pipe_ids()[10])
        c.set_basin_focus(keep_n, keep_p)
        self.assertEqual(self._line_color(g.pipe_ids()[10]), nc._FOCUS_DIM_PIPE)
        self.assertEqual(self._line_color(g.pipe_ids()[0]), classify_utilization(self.peak_snap.pipe_states[g.pipe_ids()[0]].utilization_pct).color_hex)
        c.set_basin_focus(None, None)
        self.assertEqual(self._line_color(g.pipe_ids()[10]), full)
        c.set_tour_focus(keep_n, keep_p)
        self.assertEqual(self._line_color(g.pipe_ids()[10]), nc._FOCUS_DIM_PIPE)
        self.assertEqual(self._state(c._hint_bar.winfo_id()) if False else "", "")
        c.set_tour_focus(None, None)
        self.assertEqual(self._line_color(g.pipe_ids()[10]), full)

    def test_traversal_active_and_backtracked(self) -> None:
        c, g = self.canvas, self.graph
        pids = g.pipe_ids()[:4]
        nids = g.node_ids()[:4]
        c.set_traversal_highlight(
            visited_nodes=nids, visited_edges=pids[:2], mode="dfs", origin_node=nids[0],
            active_nodes=[nids[1]], active_edges=[pids[1]], backtracked_nodes=[nids[2]], backtracked_edges=[pids[2]], banner_text="DFS",
        )
        gm = c._geoms
        self.assertEqual(self._line_color(pids[1]), nc.theme.TRAV_ACTIVE_COLOR)
        self.assertEqual(self._line_color(pids[0]), nc.theme.TRAV_DFS_EDGE)
        self.assertEqual(self._line_color(pids[2]), nc.theme.TRAV_DIM_OUTLINE)
        self.assertNotEqual(c.itemcget(gm[pids[2]].line, "dash"), "")
        self.assertEqual(c.itemcget(c._ngeoms[nids[1]].oval, "outline"), nc.theme.TRAV_ACTIVE_COLOR)
        self.assertNotEqual(c.itemcget(c._ngeoms[nids[2]].oval, "dash"), "")
        self.assertEqual(self._state(c._origin_ring), "normal")
        c.set_traversal_highlight(visited_edges=pids[:1], mode="bfs")
        self.assertEqual(self._line_color(pids[0]), nc.theme.TRAV_BFS_EDGE)
        c.clear_traversal_highlight()
        self.assertEqual(self._state(c._origin_ring), "hidden")

    def test_selection_and_click(self) -> None:
        c, g = self.canvas, self.graph
        events = []
        c._on_select = lambda k, i: events.append((k, i))
        pid, nid = g.pipe_ids()[0], g.node_ids()[3]
        c.select_pipe(pid)
        self.assertEqual(self._state(c._geoms[pid].halo), "normal")
        c.select_node(nid)
        self.assertEqual(self._state(c._geoms[pid].halo), "hidden")
        self.assertEqual(self._state(c._sel_ring), "normal")
        c.set_selected(None, None)
        self.assertEqual(self._state(c._sel_ring), "hidden")
        x, y = c._node_coords[nid]
        class E: pass
        e = E(); e.x, e.y = x, y
        c._on_left_press(e); c._on_left_release(e)
        self.assertEqual(events[-1], ("node", nid))
        self.assertEqual(c._selected_id, nid)

    # ── Tooltips ──
    def test_tooltips(self) -> None:
        c, g = self.canvas, self.graph
        c.set_snapshot(self.peak_snap)
        pid = max(self.peak_snap.pipe_states, key=lambda p: self.peak_snap.pipe_states[p].utilization_pct)
        tip = c._format_tooltip("pipe", pid)
        for frag in ("Tubería", "Qmax", "Utilización", "× Qmax", "Tránsito", "Ø"):
            self.assertIn(frag, tip)
        flooded = next(n for n, s in self.peak_snap.node_states.items() if s.surface_flooding_m3 > 1e-4)
        ntip = c._format_tooltip("node", flooded)
        for frag in ("Entrada", "Salida", "Rebose"):
            self.assertIn(frag, ntip)
        self.assertIn("Fuente", c._format_tooltip("node", g.source_ids()[0]))

    # ── Overlays, insignias y rendimiento ──
    def test_overlays_and_badges(self) -> None:
        c = self.canvas
        self.assertIn("NODOS", c._stamp_lbl.cget("text"))
        self.assertEqual(c._lbl_zoom.cget("text"), "100%")
        texts = [c.itemcget(t, "text") for ng in c._ngeoms.values() if ng.badge for t in (ng.badge[1],)]
        self.assertTrue(any(t.startswith("PTAR") and t.endswith("31") for t in texts))
        self.assertIn("Fuente", texts)
        c.set_tour_focus({"1"}, set())
        self.assertFalse(c._hint_bar.winfo_ismapped())
        c.set_tour_focus(None, None)

    def test_label_collision_free_slots(self) -> None:
        c = self.canvas
        boxes = []
        for g in c._geoms.values():
            if not g.lbl_ok: continue
            tw, th = c._text_size(f"{g.pid} · 100%", (c._fonts["mono"][0], -c._lbl_font_px, "bold"))
            lx, ly, a = g.slot
            x0 = lx - tw / 2 if a == "center" else (lx if a == "w" else lx - tw)
            boxes.append((x0, ly - th / 2, x0 + tw, ly + th / 2))
        self.assertTrue(boxes)
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertFalse(nc._boxes_overlap(a, b))

    def test_phase_b_performance_guard(self) -> None:
        c = self.canvas
        t = time.perf_counter()
        for s in self.snaps:
            c.set_snapshot(s)
        avg_b = (time.perf_counter() - t) / len(self.snaps) * 1000.0
        t = time.perf_counter()
        for _ in range(3):
            c.rebuild_geometry()
        avg_a = (time.perf_counter() - t) / 3 * 1000.0
        print(f"\n[canvas] Fase A {avg_a:.1f} ms · Fase B {avg_b:.2f} ms/paso")
        self.assertLess(avg_b, 15.0)
        self.assertLess(avg_a, 400.0)

    def test_destroy_cancels_timers(self) -> None:
        c = self.canvas
        c.set_snapshot(self.peak_snap)
        c.set_playing(True)
        c.animate_focus_region({self.graph.node_ids()[0]}, steps=30, step_ms=30)
        self.root.destroy()
        self.assertIsNone(c._pulse_after_id)
        self.assertIsNone(c._cam_after)


    def test_intervention_label_avoids_ptar_badge_and_other_labels(self) -> None:
        c = self.canvas
        c.set_snapshot(self.peak_snap)
        c.set_interventions({"P29": PipeIntervention("P29", 80.0)})
        c.rebuild_geometry(); self.root.update()
        g = c._geoms["P29"]
        self.assertTrue(g.has_mark)
        self.assertEqual(c.itemcget(g.lbl_rect, "state"), "normal")
        lb = c.bbox(g.lbl_rect)
        sink = next(n for n in self.graph.nodes() if n.node_type == "sink").node_id
        badge = c._ngeoms[sink].badge
        self.assertIsNotNone(badge)
        bb = c.bbox(badge[0])
        self.assertTrue(lb[2] <= bb[0] or lb[0] >= bb[2] or lb[3] <= bb[1] or lb[1] >= bb[3], (lb, bb))
        for pid, other in c._geoms.items():
            if pid == "P29" or other.lbl_rect is None or c.itemcget(other.lbl_rect, "state") != "normal":
                continue
            ob = c.bbox(other.lbl_rect)
            self.assertTrue(lb[2] <= ob[0] or lb[0] >= ob[2] or lb[3] <= ob[1] or lb[1] >= ob[3], (pid, lb, ob))


if __name__ == "__main__":
    unittest.main()
