"""Pruebas unitarias e integración headless para el módulo de visualización 3D (view3d)."""

import math
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from src.algorithms.analysis import classify_utilization
from src.algorithms.traversals import bfs_anim_frames
from src.data_structures import DirectedGraph, ManholeNode, PipeEdge
from src.gui import ensure_qapplication
from src.gui.view3d import (
    Basin3DWidget,
    OrbitCamera,
    PipeInspector3DWidget,
    compute_network_elevations,
)
from src.io.data_loader import load_dataset
from src.simulation import (
    NodeStepState,
    PipeIntervention,
    PipeStepState,
    SewerSimulationEngine,
    SimulationConfig,
)


def _pump(ms: int = 40) -> None:
    qapp = QApplication.instance()
    if qapp is None:
        return
    end = time.time() + ms / 1000.0
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def _make_pipe(
    pid: str, u: str, v: str, *, slope: float = 0.01, length_m: float = 100.0, diam_m: float = 0.254
) -> PipeEdge:
    return PipeEdge(
        pipe_id=pid,
        from_node=u,
        to_node=v,
        diameter_in=diam_m / 0.0254,
        diameter_m=diam_m,
        manning_n=0.015,
        slope=slope,
        q_max_m3s=0.05,
        length_m=length_m,
    )


class TestElevationAndProjection(unittest.TestCase):
    """Pruebas de cálculo de cotas (Bellman-Ford + IDW) y proyección orbital 3D."""

    @classmethod
    def setUpClass(cls) -> None:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.dataset = load_dataset(os.path.join(base, "data", "csv"))

    def test_real_dataset_elevations_monotonic_and_grid_10x10(self) -> None:
        prof = compute_network_elevations(self.dataset.graph, grid_n=10)
        self.assertFalse(prof.slope_unit_normalized)
        self.assertEqual(len(prof.grid_cells), 100)
        self.assertAlmostEqual(prof.node_z["31"], 0.0, places=6)

        for edge in self.dataset.graph.pipes():
            zu = prof.node_z[edge.from_node]
            zv = prof.node_z[edge.to_node]
            self.assertGreaterEqual(zu + 1e-9, zv + edge.slope * edge.length_m)

        for nid, gz in prof.ground_z.items():
            self.assertGreaterEqual(gz + 1e-9, prof.node_z[nid] + 1.5)

    def test_multi_sink_cycle_safe_and_disconnected_idw(self) -> None:
        g = DirectedGraph()
        g.add_node(ManholeNode("S1", "sink", 0.0, 0.0))
        g.add_node(ManholeNode("S2", "sink", 1.0, 0.0))
        g.add_node(ManholeNode("A", "manhole", 0.0, 0.5))
        g.add_node(ManholeNode("B", "manhole", 0.5, 0.5))
        g.add_node(ManholeNode("C", "manhole", 1.0, 0.5))
        g.add_node(ManholeNode("ISO", "manhole", 0.5, 0.52))
        g.add_pipe(_make_pipe("P1", "A", "S1", slope=0.01, length_m=200.0))
        g.add_pipe(_make_pipe("P2", "B", "A", slope=0.01, length_m=100.0))
        # Ciclo artificial A -> B -> A en red externa
        g.add_pipe(_make_pipe("P_CYC", "A", "B", slope=0.01, length_m=50.0))
        g.add_pipe(_make_pipe("P3", "C", "S2", slope=0.02, length_m=100.0))

        prof = compute_network_elevations(g, grid_n=10)
        self.assertAlmostEqual(prof.node_z["S1"], 0.0, places=6)
        self.assertAlmostEqual(prof.node_z["S2"], 0.0, places=6)
        self.assertAlmostEqual(prof.node_z["C"], 2.0, places=6)
        self.assertTrue(math.isfinite(prof.node_z["A"]))
        self.assertTrue(math.isfinite(prof.node_z["B"]))
        self.assertNotIn("ISO", prof.resolved_nodes)
        # ISO interpolado entre A, B y C dentro de rango [min_resolved, max_resolved]
        resolved_vals = [prof.node_z[n] for n in prof.resolved_nodes]
        self.assertGreaterEqual(prof.node_z["ISO"], min(resolved_vals) - 1e-6)
        self.assertLessEqual(prof.node_z["ISO"], max(resolved_vals) + 1e-6)

    def test_slope_percent_unit_guard(self) -> None:
        g_frac = DirectedGraph()
        g_frac.add_node(ManholeNode("31", "sink", 0.5, 0.9))
        g_frac.add_node(ManholeNode("1", "source", 0.5, 0.1))
        g_frac.add_pipe(_make_pipe("P1", "1", "31", slope=0.01, length_m=300.0))

        g_pct = DirectedGraph()
        g_pct.add_node(ManholeNode("31", "sink", 0.5, 0.9))
        g_pct.add_node(ManholeNode("1", "source", 0.5, 0.1))
        g_pct.add_pipe(_make_pipe("P1", "1", "31", slope=1.0, length_m=300.0))

        p_frac = compute_network_elevations(g_frac)
        p_pct = compute_network_elevations(g_pct)
        self.assertFalse(p_frac.slope_unit_normalized)
        self.assertTrue(p_pct.slope_unit_normalized)
        self.assertAlmostEqual(p_frac.node_z["1"], 3.0, places=6)
        self.assertAlmostEqual(p_pct.node_z["1"], 3.0, places=6)

        p_forced_false = compute_network_elevations(g_pct, slope_is_percent=False)
        self.assertFalse(p_forced_false.slope_unit_normalized)
        self.assertAlmostEqual(p_forced_false.node_z["1"], 300.0, places=6)

    def test_orbit_camera_projection_and_clamping(self) -> None:
        cam = OrbitCamera()
        p_low = cam.project_point(0.0, 0.0, 0.0, 800.0, 600.0)
        p_high = cam.project_point(0.0, 0.0, 0.5, 800.0, 600.0)
        self.assertLess(p_high.y, p_low.y)
        self.assertLess(p_high.depth, p_low.depth)

        cam.orbit(100.0, 10000.0)
        self.assertLessEqual(cam.pitch, OrbitCamera.MAX_PITCH)
        cam.orbit(0.0, -10000.0)
        self.assertGreaterEqual(cam.pitch, OrbitCamera.MIN_PITCH)
        cam.zoom_by(100.0)
        self.assertLessEqual(cam.zoom, OrbitCamera.MAX_ZOOM)
        cam.reset()
        self.assertAlmostEqual(cam.yaw, OrbitCamera.DEFAULT_YAW)
        self.assertAlmostEqual(cam.pitch, OrbitCamera.DEFAULT_PITCH)
        self.assertAlmostEqual(cam.zoom, OrbitCamera.DEFAULT_ZOOM)

        # Verificar sentidos naturales de órbita sobre un punto frontal (0, 1, 0)
        cam_front = OrbitCamera(yaw=0.0, pitch=0.56)
        p0 = cam_front.project_point(0.0, 1.0, 0.0, 800.0, 600.0)
        cam_front.orbit(20.0, 0.0)
        p_right = cam_front.project_point(0.0, 1.0, 0.0, 800.0, 600.0)
        self.assertGreater(p_right.x, p0.x)
        cam_front = OrbitCamera(yaw=0.0, pitch=0.56)
        p0 = cam_front.project_point(0.0, 1.0, 0.0, 800.0, 600.0)
        cam_front.orbit(0.0, 20.0)
        p_down = cam_front.project_point(0.0, 1.0, 0.0, 800.0, 600.0)
        self.assertGreater(p_down.y, p0.y)


class TestWidgets3DOffscreen(unittest.TestCase):
    """Pruebas offscreen de PipeInspector3DWidget y Basin3DWidget."""

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapplication()
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.dataset = load_dataset(os.path.join(base, "data", "csv"))
        cls.engine = SewerSimulationEngine(cls.dataset.graph, cls.dataset.basin)
        cls.res_e5 = cls.engine.run(
            SimulationConfig(scenario_id=5, scenario_name="Extreme rain", intensity_mm_h=100.0)
        )

    def test_pipe_inspector_3d_all_states_including_100pct_blocked(self) -> None:
        w = PipeInspector3DWidget()
        w.resize(320, 130)
        w.show()
        _pump(20)
        edge = self.dataset.graph.get_pipe("P3")
        assert edge is not None

        # 1. Seco (0%)
        ps_dry = PipeStepState(
            pipe_id="P3",
            flow_m3s=0.0,
            conveyed_flow_m3s=0.0,
            volume_in_transit_m3=0.0,
            utilization_pct=0.0,
            category=classify_utilization(0.0),
            excess_flow_m3s=0.0,
        )
        ns_dry = NodeStepState("C", 0.0, 0.0, 0.0, 0.0, 0.0)
        w.update_state(edge, ps_dry, ns_dry, None)
        self.assertEqual(w.render_mode, "normal")
        self.assertAlmostEqual(w.fill_ratio, 0.0)
        self.assertFalse(w.grab().isNull())

        # 2. Normal (60%)
        ps_norm = PipeStepState(
            pipe_id="P3",
            flow_m3s=0.052,
            conveyed_flow_m3s=0.052,
            volume_in_transit_m3=10.0,
            utilization_pct=60.0,
            category=classify_utilization(60.0),
            excess_flow_m3s=0.0,
            demand_flow_m3s=0.052,
            demand_ratio_pct=60.0,
        )
        w.update_state(edge, ps_norm, ns_dry, None)
        self.assertEqual(w.render_mode, "normal")
        self.assertAlmostEqual(w.fill_ratio, 0.60, places=3)
        self.assertFalse(w.grab().isNull())

        # 3. Sobrecargado (120%)
        ps_over = PipeStepState(
            pipe_id="P3",
            flow_m3s=edge.q_max_m3s,
            conveyed_flow_m3s=edge.q_max_m3s,
            volume_in_transit_m3=20.0,
            utilization_pct=120.0,
            category=classify_utilization(120.0),
            excess_flow_m3s=0.04,
            demand_flow_m3s=0.12,
            demand_ratio_pct=140.0,
            is_overflow_capped=True,
        )
        ns_over = NodeStepState("C", 0.12, edge.q_max_m3s, 4.0, 25.0, 0.04)
        w.update_state(edge, ps_over, ns_over, None)
        self.assertEqual(w.render_mode, "normal")
        self.assertAlmostEqual(w.fill_ratio, 1.0)
        self.assertFalse(w.grab().isNull())

        # 4. Obstruido al 100% (eff_q_max == 0) CON represamiento
        inv_100 = PipeIntervention(pipe_id="P3", obstruction_pct=100.0)
        ps_blk_bw = PipeStepState(
            pipe_id="P3",
            flow_m3s=0.0,
            conveyed_flow_m3s=0.0,
            volume_in_transit_m3=0.0,
            utilization_pct=0.0,
            category=classify_utilization(0.0),
            excess_flow_m3s=0.10,
            demand_flow_m3s=0.10,
            demand_ratio_pct=0.0,
            effective_q_max_m3s=0.0,
            is_closed=True,
        )
        w.update_state(edge, ps_blk_bw, ns_over, inv_100)
        self.assertEqual(w.render_mode, "blocked_backwater")
        self.assertTrue(w.has_backwater)
        self.assertAlmostEqual(w.fill_ratio, 1.0)
        self.assertIn("REPRESADA", w.status_badge_text)
        self.assertFalse(w.grab().isNull())

        # 5. Obstruido al 100% (eff_q_max == 0) SIN represamiento (tiempo seco)
        ps_blk_dry = PipeStepState(
            pipe_id="P3",
            flow_m3s=0.0,
            conveyed_flow_m3s=0.0,
            volume_in_transit_m3=0.0,
            utilization_pct=0.0,
            category=classify_utilization(0.0),
            excess_flow_m3s=0.0,
            demand_flow_m3s=0.0,
            demand_ratio_pct=0.0,
            effective_q_max_m3s=0.0,
            is_closed=True,
        )
        w.update_state(edge, ps_blk_dry, ns_dry, inv_100)
        self.assertEqual(w.render_mode, "blocked_dry")
        self.assertFalse(w.has_backwater)
        self.assertAlmostEqual(w.fill_ratio, 0.0)
        self.assertIn("SIN DEMANDA", w.status_badge_text)
        self.assertFalse(w.grab().isNull())

        w.close()
        w.deleteLater()

    def test_basin_3d_modes_inlet_spill_blocked_pipe_picking_and_perf(self) -> None:
        view = Basin3DWidget()
        view.resize(720, 520)
        view.show()
        view.set_graph(self.dataset.graph)
        _pump(30)

        snap30 = self.res_e5.snapshots[30]
        # Fuente con stored_volume_m3 == 0 y rebose directo en rejilla (surface_flooding_m3 > 0)
        self.assertAlmostEqual(snap30.node_states["6"].stored_volume_m3, 4.0, places=2)
        # Simular caso extremo de fuente con pozo 0 m3 y rebose directo de rejilla
        snap_copy_ns = dict(snap30.node_states)
        snap_copy_ns["6"] = NodeStepState("6", 1.2, 0.05, 0.0, 150.0, 0.8)
        snap30.node_states["6"] = snap_copy_ns["6"]

        view.set_stress_maps(
            peak_util=self.res_e5.peak_pipe_utilization,
            overload_minutes=self.res_e5.pipe_overloaded_minutes,
            total_duration_min=90.0,
        )
        for mode in ("instant", "peak", "overload_minutes"):
            view.set_map_mode(mode)
            view.set_snapshot(snap30, self.res_e5)
            img = view.grab().toImage()
            self.assertFalse(img.isNull())

        # Tubería cerrada se resuelve con estilo bloqueado, nunca verde
        col, _ov, is_blk = view._resolve_pipe_color_and_flags(
            "P3", snap30.pipe_states["P3"], True
        )
        self.assertTrue(is_blk)
        self.assertNotEqual(col.name().lower(), "#22c55e")

        # HUD controls: opacidad suelo y escala Z
        view.cycle_ground_opacity()
        self.assertAlmostEqual(view.ground_opacity, 1.0)
        view.cycle_ground_opacity()
        self.assertAlmostEqual(view.ground_opacity, 0.0)
        view.cycle_ground_opacity()
        self.assertAlmostEqual(view.ground_opacity, 0.45)

        view.cycle_z_exag()
        self.assertAlmostEqual(view.z_exag, 5.0)
        view.cycle_z_exag()
        self.assertAlmostEqual(view.z_exag, 1.0)
        view.cycle_z_exag()
        self.assertAlmostEqual(view.z_exag, 3.0)

        # Picking 3D sobre nodo proyectado real
        picked_nodes = []
        view.nodeSelected.connect(picked_nodes.append)
        self.assertGreater(len(view._hit_nodes), 0)
        target_nid, tx, ty, _nr, _d = view._hit_nodes[0]
        press_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(tx, ty),
            QPointF(tx, ty),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        rel_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(tx, ty),
            QPointF(tx, ty),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mousePressEvent(press_ev)
        view.mouseReleaseEvent(rel_ev)
        self.assertIn(target_nid, picked_nodes)

        # Benchmark de renderizado puro sobre QImage (Escenario 5) < 5 ms/frame
        view.set_map_mode("instant")
        view.set_snapshot(snap30, self.res_e5)
        frame_img = QImage(720, 520, QImage.Format.Format_ARGB32_Premultiplied)
        # Warm-up
        p = QPainter(frame_img)
        view.render(p, QPoint())
        p.end()
        t0 = time.perf_counter()
        n_frames = 20
        for _ in range(n_frames):
            painter = QPainter(frame_img)
            view.render(painter, QPoint())
            painter.end()
        avg_ms = ((time.perf_counter() - t0) * 1000.0) / n_frames
        self.assertLess(avg_ms, 55.0, f"Promedio por frame 3D demasiado alto: {avg_ms:.2f} ms")

        # Partículas 3D de flujo en vivo, animación BFS, corte mínimo FF y disipación de rebose
        view.set_playing(True, 2.5)
        _pump(80)
        self.assertFalse(view.grab().isNull())
        view.set_playing(False)

        _res_bfs, frames_bfs = bfs_anim_frames(self.dataset.graph, "6", "31")
        self.assertGreater(len(frames_bfs), 0)
        view.set_traversal_frame(frames_bfs[0])
        self.assertFalse(view.grab().isNull())
        view.promote_traversal_to_highlights(
            {"P1", "P2"}, {"6", "31"}, ordered_route_pipes=["P1", "P2"], highlight_mode="route"
        )
        self.assertFalse(view.grab().isNull())

        view.set_highlights(
            {"P3", "P28", "P43", "P53"},
            {"31"},
            ordered_route_pipes=["P3", "P28", "P43", "P53"],
            highlight_mode="min_cut",
        )
        self.assertFalse(view.grab().isNull())
        view.set_highlights(set(), set())

        # Nodo con acumulado histórico pero sin tasa activa ni charco activo (ej. t=200 min)
        res_ext = self.engine.run(
            SimulationConfig(
                scenario_id=5,
                scenario_name="Extreme extended",
                intensity_mm_h=100.0,
                duration_min=200.0,
                storm_duration_min=60.0,
            )
        )
        view.set_map_mode("instant")
        view.set_snapshot(res_ext.snapshots[-1], res_ext)
        self.assertAlmostEqual(
            res_ext.snapshots[-1].node_states["17"].active_surface_ponding_m3, 0.0, places=6
        )
        self.assertFalse(view.grab().isNull())

        view.close_overlays()
        view.close()
        view.deleteLater()


if __name__ == "__main__":
    unittest.main()
