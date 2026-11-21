"""Módulo del Recorrido Guiado (4 Hallazgos por escenario) sobre NetworkCanvas."""

import tkinter as tk
from typing import Dict, List, Optional, Set, Tuple

from src.simulation import TimeStepSnapshot
from . import theme


class GuidedTourMixin:
    """Gestiona la ficha flotante y las paradas dinámicas del Recorrido Guiado."""

    def _guided_tour_button_label(self, width: Optional[int] = None) -> str:
        w = width if width is not None else max(self.winfo_width(), self.winfo_reqwidth())
        sc = self._selected_scenario_obj()
        sid = sc.scenario_id if sc is not None else (self.result.config.scenario_id if self.result else 3)
        if w >= 1220:
            return f"Guía Esc. {sid} (4 Hallazgos)"
        return f"Guía Esc. {sid}"

    def _update_guided_tour_button_label(self) -> None:
        if hasattr(self, "btn_guided_tour") and self.btn_guided_tour.winfo_exists():
            lbl = self._guided_tour_button_label()
            self.btn_guided_tour.configure(text=lbl)

    def _build_tour_card(self) -> None:
        self._tour_card = tk.Frame(
            self.network_canvas,
            bg=theme.PAPER_BG,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )

        hdr = tk.Frame(self._tour_card, bg=theme.ACCENT_PRIMARY)
        hdr.pack(fill=tk.X)
        self._lbl_tour_hdr = tk.Label(
            hdr,
            text="ESC. 3 · HALLAZGO 1/4 · MIN 5",
            bg=theme.ACCENT_PRIMARY,
            fg=theme.ACCENT_INK,
            font=(self.mono_font, 8, "bold"),
            padx=9,
            pady=4,
            anchor="w",
        )
        self._lbl_tour_hdr.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_x = tk.Button(
            hdr,
            text="×",
            command=self._close_guided_tour,
            bg=theme.ACCENT_PRIMARY,
            fg=theme.ACCENT_INK,
            activebackground=theme.ACCENT_HOVER,
            activeforeground=theme.ACCENT_INK,
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            font=(self.ui_font, 10, "bold"),
            cursor="hand2",
        )
        btn_x.pack(side=tk.RIGHT)

        body = tk.Frame(self._tour_card, bg=theme.PAPER_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        self._lbl_tour_scenario = tk.Label(
            body,
            text="",
            bg=theme.PAPER_BG,
            fg=theme.ACCENT_TEXT_ON_LIGHT,
            font=(self.mono_font, 7, "bold"),
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._lbl_tour_scenario.pack(fill=tk.X, pady=(0, 2))

        self._lbl_tour_title = tk.Label(
            body,
            text="",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.display_font, 9, "bold"),
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._lbl_tour_title.pack(fill=tk.X, pady=(0, 2))

        self._lbl_tour_desc = tk.Label(
            body,
            text="",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._lbl_tour_desc.pack(fill=tk.X, pady=(0, 4))

        self._lbl_tour_metrics = tk.Label(
            body,
            text="",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_PRIMARY,
            font=(self.mono_font, 8, "bold"),
            anchor="w",
            justify="left",
            padx=6,
            pady=3,
            highlightthickness=1,
            highlightbackground=theme.PAPER_BORDER,
            wraplength=272,
        )
        self._lbl_tour_metrics.pack(fill=tk.X)

        tk.Frame(self._tour_card, bg=theme.PAPER_BORDER, height=1).pack(fill=tk.X)
        ftr = tk.Frame(self._tour_card, bg=theme.PAPER_SUBTLE)
        ftr.pack(fill=tk.X, padx=8, pady=4)
        self._btn_tour_prev = self._make_btn(
            ftr,
            "Anterior",
            lambda: self._go_tour_stop(self._tour_step - 1),
            variant="light_secondary",
            padx=7,
            pady=2,
            font_size=8,
        )
        self._btn_tour_prev.pack(side=tk.LEFT)
        self._btn_tour_next = self._make_btn(
            ftr,
            "Siguiente",
            lambda: self._go_tour_stop(self._tour_step + 1),
            variant="primary",
            padx=8,
            pady=2,
            font_size=8,
        )
        self._btn_tour_next.pack(side=tk.LEFT, padx=(5, 0))
        self._make_btn(
            ftr,
            "Cerrar",
            self._close_guided_tour,
            variant="dock_secondary",
            padx=7,
            pady=2,
            font_size=8,
        ).pack(side=tk.RIGHT)

    def _fit_tour_card_geometry(self) -> int:
        """Ajusta el ancho de la ficha flotante según el lienzo disponible y retorna el ancho efectivo."""
        cw = self.network_canvas.winfo_width()
        if cw <= 1:
            cw = 680
        preferred = max(290, min(self._px(310), int(cw * 0.54)))
        card_w = max(200, min(cw - 20, preferred))
        wrap_w = max(175, card_w - 24)
        self._lbl_tour_scenario.configure(wraplength=wrap_w)
        self._lbl_tour_title.configure(wraplength=wrap_w)
        self._lbl_tour_desc.configure(wraplength=wrap_w)
        self._lbl_tour_metrics.configure(wraplength=max(168, wrap_w - 10))
        if self._tour_card.winfo_manager():
            self._tour_card.place_configure(width=card_w)
        return card_w

    def _build_tour_stops(self) -> List[Dict[str, object]]:
        if self.dataset is None:
            return []
        g = self.dataset.graph

        def _snap_for_min(target_m: float) -> Tuple[int, Optional[TimeStepSnapshot]]:
            if not self.result or not self.result.snapshots:
                return (0, None)
            best_i = min(
                range(len(self.result.snapshots)),
                key=lambda i: abs(self.result.snapshots[i].time_min - target_m),
            )
            return (best_i, self.result.snapshots[best_i])

        def _endpoints(pipe_ids: List[str]) -> Set[str]:
            nodes: Set[str] = set()
            for pid in pipe_ids:
                e = g.get_pipe(pid)
                if e is not None:
                    nodes.update((e.from_node, e.to_node))
            return nodes

        def _existing_pipes(*candidates: str) -> List[str]:
            return [pid for pid in candidates if g.has_pipe(pid)]

        def _max_util(snap: Optional[TimeStepSnapshot], pipe_ids: List[str]) -> float:
            if snap is None:
                return 0.0
            return max((snap.pipe_states[p].utilization_pct for p in pipe_ids if p in snap.pipe_states), default=0.0)

        def _max_dem(snap: Optional[TimeStepSnapshot], pipe_ids: List[str]) -> float:
            if snap is None:
                return 0.0
            return max((snap.pipe_states[p].demand_ratio_pct / 100.0 for p in pipe_ids if p in snap.pipe_states), default=0.0)

        def _sum_storage(snap: Optional[TimeStepSnapshot], node_ids: Tuple[str, ...]) -> float:
            if snap is None:
                return 0.0
            return sum((snap.node_states[n].stored_volume_m3 for n in node_ids if n in snap.node_states), 0.0)

        def _sum_flood(snap: Optional[TimeStepSnapshot], node_ids: Tuple[str, ...]) -> float:
            if snap is None:
                return 0.0
            return sum((snap.node_states[n].surface_flooding_m3 for n in node_ids if n in snap.node_states), 0.0)

        def _pipe_qud(snap: Optional[TimeStepSnapshot], pid: str) -> Tuple[float, float, float]:
            if snap is None or pid not in snap.pipe_states:
                return (0.0, 0.0, 0.0)
            ps = snap.pipe_states[pid]
            return (ps.flow_m3s, ps.utilization_pct, ps.demand_ratio_pct / 100.0)

        cfg = self.result.config if self.result else None
        sc_id = cfg.scenario_id if cfg else self._selected_scenario_obj().scenario_id
        intensity = cfg.intensity_mm_h if cfg else self._selected_scenario_obj().intensity_mm_h

        src_ids = g.source_ids()
        src_pipes = [e.pipe_id for s in src_ids for e in g.outgoing_pipes(s)]
        t_vals = [e.transit_time_s / 60.0 for e in g.pipes()]
        t_min_r = min(t_vals) if t_vals else 0.81
        t_max_r = max(t_vals) if t_vals else 18.05
        err4 = self.result.max_mass_balance_error_m3 if self.result else 0.0

        p_head8 = _existing_pipes("P31", "P39", "P43")
        n_head8 = _endpoints(p_head8)
        p_25 = _existing_pipes("P25")
        n_25 = _endpoints(p_25)
        p_ptar = _existing_pipes("P29", "P30")
        n_ptar = ({"31"} if g.has_node("31") else set(g.sink_ids())) | _endpoints(p_ptar)

        idx1, s1 = _snap_for_min(5.0)
        q_in1 = s1.total_source_inflow_m3s if s1 else 0.0
        stor1 = s1.total_manhole_storage_m3 if s1 else 0.0
        flood1 = s1.total_surface_flooding_m3 if s1 else 0.0

        idx2, s2 = _snap_for_min(25.0)
        u2_max = _max_util(s2, p_head8)
        d2_max = _max_dem(s2, p_head8)
        v2_stor = _sum_storage(s2, ("17", "19", "20"))
        v2_flood = _sum_flood(s2, ("17", "19", "20"))

        idx4, s4 = _snap_for_min(65.0)
        q_ptar4 = s4.total_sink_discharge_m3s if s4 else 0.0
        u_ptar4 = _max_util(s4, p_ptar)
        stor4 = s4.total_manhole_storage_m3 if s4 else 0.0
        flood4 = s4.total_surface_flooding_m3 if s4 else 0.0

        if sc_id == 1:
            idx3, s3 = _snap_for_min(40.0)
            q25, u25, _d25 = _pipe_qud(s3, "P25")
            return [
                {
                    "title": "Tiempo seco sin escorrentía en las 8 fuentes (0 mm/h)",
                    "target_min": 5.0,
                    "step_idx": idx1,
                    "nodes": set(src_ids),
                    "pipes": set(src_pipes),
                    "desc": (
                        "Con I = 0 mm/h y Q_san = 0 por defecto, el Método Racional genera caudal nulo "
                        "en las 8 fuentes (puede activarse Q_san opcional desde el panel izquierdo)."
                    ),
                    "metrics": f"Q_in = {q_in1:.4f} m³/s  ·  Tránsito: {t_min_r:.2f}–{t_max_r:.2f} min",
                },
                {
                    "title": "Cabeceras de 8\" en reposo hidráulico",
                    "target_min": 25.0,
                    "step_idx": idx2,
                    "nodes": n_head8,
                    "pipes": set(p_head8),
                    "desc": (
                        "Las tuberías iniciales P31, P39 y P43 (8\") permanecen en banda verde (0%–25%), "
                        "sin acumulación en pozos ni rebose superficial."
                    ),
                    "metrics": f"Util. máx: {u2_max:.2f}%  ·  Pozo/Rebose: {v2_stor:.2f}/{v2_flood:.2f} m³",
                },
                {
                    "title": "Convergencia sin congestión en tramo P25",
                    "target_min": 40.0,
                    "step_idx": idx3,
                    "nodes": n_25,
                    "pipes": set(p_25),
                    "desc": (
                        "Al confluir las subcuencas sobre el pozo 23 hacia J (P25, 12\"), toda la red "
                        "mantiene 100% de reserva hidráulica."
                    ),
                    "metrics": f"P25: Q = {q25:.5f} m³/s  ·  Utilización = {u25:.2f}%",
                },
                {
                    "title": "Balance nulo verificado hacia PTAR Punta Canoa",
                    "target_min": 65.0,
                    "step_idx": idx4,
                    "nodes": n_ptar,
                    "pipes": set(p_ptar),
                    "desc": (
                        "Los colectores troncales P29 y P30 (20\") hacia el Nodo sumidero 31 verifican "
                        "conservación exacta de masa sin aportes no contabilizados."
                    ),
                    "metrics": f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  P29/P30: {u_ptar4:.2f}%  ·  Err = {err4:.1e} m³",
                },
            ]

        if sc_id == 2:
            idx3, s3 = _snap_for_min(50.0)
            q25, u25, d25 = _pipe_qud(s3, "P25")
            return [
                {
                    "title": "Escorrentía ligera (10 mm/h) en las 8 fuentes",
                    "target_min": 5.0,
                    "step_idx": idx1,
                    "nodes": set(src_ids),
                    "pipes": set(src_pipes),
                    "desc": (
                        "La lluvia ligera activa el Método Racional (C=0.75, A=388 ha) ponderado por "
                        "capacidad instalada o 1/8 más el caudal sanitario base."
                    ),
                    "metrics": f"Q_in = {q_in1:.4f} m³/s  ·  Pozo/Rebose: {stor1:.1f}/{flood1:.1f} m³",
                },
                {
                    "title": "Cabeceras de 8\" sin congestión severa",
                    "target_min": 25.0,
                    "step_idx": idx2,
                    "nodes": n_head8,
                    "pipes": set(p_head8),
                    "desc": (
                        "Con reparto por capacidad, P31, P39 y P43 (8\") operan cerca del 48%–96% sin "
                        "desbordar sus pozos (17, 19 y 20)."
                    ),
                    "metrics": f"Util. máx: {u2_max:.2f}% ({d2_max:.2f}×)  ·  Rebose: {v2_flood:.2f} m³",
                },
                {
                    "title": "Convergencia máxima en colector P25 (23 → J)",
                    "target_min": 50.0,
                    "step_idx": idx3,
                    "nodes": n_25,
                    "pipes": set(p_25),
                    "desc": (
                        "La suma de aportes aguas arriba lleva a P25 (12\") al punto de mayor exigencia "
                        "de toda la red en lluvia ligera, marcando el primer cuello local."
                    ),
                    "metrics": f"P25: Q = {q25:.4f} m³/s  ·  Util. física = {u25:.1f}% (Dem. {d25:.2f}×)",
                },
                {
                    "title": "Recesión limpia hacia PTAR Punta Canoa",
                    "target_min": 65.0,
                    "step_idx": idx4,
                    "nodes": n_ptar,
                    "pipes": set(p_ptar),
                    "desc": (
                        "Al cesar la lluvia, los colectores troncales P29 y P30 (20\") evacuan la onda "
                        "descendente hacia el Nodo 31 sin saturar la troncal principal."
                    ),
                    "metrics": f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  P29/P30: {u_ptar4:.1f}%  ·  Rebose red: {flood4:.1f} m³",
                },
            ]

        if sc_id == 4:
            p2_pipes = _existing_pipes("P31", "P39", "P43", "P1", "P2")
            n2_nodes = _endpoints(p2_pipes)
            u_p12 = _max_util(s2, _existing_pipes("P1", "P2"))
            d_p12 = _max_dem(s2, _existing_pipes("P1", "P2"))
            p3_pipes = _existing_pipes("P23", "P25", "P28")
            n3_nodes = _endpoints(p3_pipes)
            idx3, s3 = _snap_for_min(40.0)
            _, u25, d25 = _pipe_qud(s3, "P25")
            _, u23, _ = _pipe_qud(s3, "P23")
            _, u28, _ = _pipe_qud(s3, "P28")
            p4_pipes = _existing_pipes("P29", "P30", "P3")
            n4_nodes = n_ptar | _endpoints(p4_pipes)
            return [
                {
                    "title": "Sobrecarga temprana en las 8 fuentes (60 mm/h)",
                    "target_min": 5.0,
                    "step_idx": idx1,
                    "nodes": set(src_ids),
                    "pipes": set(src_pipes),
                    "desc": (
                        "Con 60 mm/h, las cabeceras superan el 100% de su capacidad Qmax y "
                        "llenan los pozos de 4 m³, iniciando rebose superficial en vía."
                    ),
                    "metrics": f"Q_in = {q_in1:.4f} m³/s  ·  Pozos: {stor1:.1f} m³  ·  Rebose: {flood1:.1f} m³",
                },
                {
                    "title": "Tope físico en 8\" y 10\" (P1, P2) con rebose",
                    "target_min": 25.0,
                    "step_idx": idx2,
                    "nodes": n2_nodes,
                    "pipes": set(p2_pipes),
                    "desc": (
                        "Las cabeceras conducen al límite Qmax mientras la demanda racional "
                        "supera con holgura su capacidad, derivando el excedente a rebose superficial."
                    ),
                    "metrics": f"8\": {u2_max:.1f}% ({d2_max:.2f}×)  ·  P1/P2: {u_p12:.1f}% ({d_p12:.2f}×)  ·  Rebose: {v2_flood:.0f} m³",
                },
                {
                    "title": "Cuello en cascada: P23, P25 y P28 (16\")",
                    "target_min": 40.0,
                    "step_idx": idx3,
                    "nodes": n3_nodes,
                    "pipes": set(p3_pipes),
                    "desc": (
                        "La congestión avanza sobre los colectores de 16\" (P23 y P28) mientras el tramo "
                        "P25 (12\") concentra la mayor restricción hidráulica del eje central."
                    ),
                    "metrics": f"P25: {u25:.1f}% ({d25:.2f}×)  ·  P23: {u23:.1f}%  ·  P28: {u28:.1f}%",
                },
                {
                    "title": "Límite de entrega en PTAR 31 y balance de rebose",
                    "target_min": 65.0,
                    "step_idx": idx4,
                    "nodes": n4_nodes,
                    "pipes": set(p4_pipes),
                    "desc": (
                        "P3 y P29/P30 sostienen la descarga máxima posible hacia la PTAR 31 mientras la "
                        "masa no absorbida por la red queda contabilizada exactamente como rebose en vía."
                    ),
                    "metrics": f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  Rebose: {flood4:.0f} m³  ·  Err = {err4:.1e} m³",
                },
            ]

        if sc_id == 5:
            p2_pipes = _existing_pipes("P31", "P39", "P43", "P12", "P13")
            n2_nodes = _endpoints(p2_pipes)
            _, u_p13, d_p13 = _pipe_qud(s2, "P13")
            p3_pipes = _existing_pipes("P23", "P25", "P28", "P3")
            n3_nodes = _endpoints(p3_pipes)
            idx3, s3 = _snap_for_min(40.0)
            _, u25, d25 = _pipe_qud(s3, "P25")
            _, u_p3, _ = _pipe_qud(s3, "P3")
            flood3 = s3.total_surface_flooding_m3 if s3 else 0.0
            p4_pipes = _existing_pipes("P29", "P30", "P3")
            n4_nodes = n_ptar | _endpoints(p4_pipes)
            return [
                {
                    "title": "Aporte extremo en las 8 fuentes (100 mm/h)",
                    "target_min": 5.0,
                    "step_idx": idx1,
                    "nodes": set(src_ids),
                    "pipes": set(src_pipes),
                    "desc": (
                        "El evento extremo satura de inmediato las cabeceras por encima de Qmax "
                        "llenando los pozos y generando escorrentía superficial por rebose."
                    ),
                    "metrics": f"Q_in = {q_in1:.4f} m³/s  ·  Pozos: {stor1:.1f} m³  ·  Rebose: {flood1:.1f} m³",
                },
                {
                    "title": "Presurización en cabeceras (8\", 10\" y 14\")",
                    "target_min": 25.0,
                    "step_idx": idx2,
                    "nodes": n2_nodes,
                    "pipes": set(p2_pipes),
                    "desc": (
                        "Los tubos conducen exactamente hasta Qmax mientras la utilización de demanda "
                        "supera ampliamente el 100%; el exceso rebosa en superficie sin romper la masa."
                    ),
                    "metrics": f"8\": {u2_max:.1f}% ({d2_max:.2f}×)  ·  P13: {u_p13:.1f}% ({d_p13:.2f}×)  ·  Rebose: {v2_flood:.0f} m³",
                },
                {
                    "title": "Saturación troncal en P25, P23, P28 y P3",
                    "target_min": 40.0,
                    "step_idx": idx3,
                    "nodes": n3_nodes,
                    "pipes": set(p3_pipes),
                    "desc": (
                        "Los ejes colectores hacia PTAR 31 operan a capacidad física plena mientras la "
                        "vía absorbe el excedente superficial acumulado durante el aguacero."
                    ),
                    "metrics": f"P25: {u25:.1f}% ({d25:.2f}×)  ·  P3: {u_p3:.1f}%  ·  Rebose red: {flood3:.0f} m³",
                },
                {
                    "title": "Descarga tope en PTAR 31 y volumen rebosado",
                    "target_min": 65.0,
                    "step_idx": idx4,
                    "nodes": n4_nodes,
                    "pipes": set(p4_pipes),
                    "desc": (
                        "Finalizada la tormenta, PTAR 31 mantiene su caudal máximo laminado mientras la "
                        "ecuación de masa audita exactamente descarga + pozos + tránsito + rebose."
                    ),
                    "metrics": f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  Rebose: {flood4:.0f} m³  ·  Err = {err4:.1e} m³",
                },
            ]

        if sc_id == 3:
            idx3, s3 = _snap_for_min(40.0)
            q25, u25, d25 = _pipe_qud(s3, "P25")
            return [
                {
                    "title": "Inyección en las 8 alcantarillas fuente",
                    "target_min": 5.0,
                    "step_idx": idx1,
                    "nodes": set(src_ids),
                    "pipes": set(src_pipes),
                    "desc": (
                        "Los 8 nodos fuente (1, 6, 9, 17, 18, 19, 20 y 27) inyectan el aporte del Método "
                        "Racional (C=0.75, A=388 ha) más el caudal sanitario según Manning."
                    ),
                    "metrics": f"Q_in = {q_in1:.4f} m³/s  ·  Tránsito: {t_min_r:.2f}–{t_max_r:.2f} min",
                },
                {
                    "title": "Saturación física inicial en tuberías de 8\"",
                    "target_min": 25.0,
                    "step_idx": idx2,
                    "nodes": n_head8,
                    "pipes": set(p_head8),
                    "desc": (
                        "Los tramos iniciales P31, P39 y P43 (8\") operan en sobrecarga (>100% de Qmax), "
                        "llenan la capacidad de sus pozos y generan rebose superficial controlado."
                    ),
                    "metrics": f"Util. fís: {u2_max:.1f}% ({d2_max:.2f}×)  ·  Pozo/Rebose: {v2_stor:.1f}/{v2_flood:.0f} m³",
                },
                {
                    "title": "Convergencia crítica en el tramo P25",
                    "target_min": 40.0,
                    "step_idx": idx3,
                    "nodes": n_25,
                    "pipes": set(p_25),
                    "desc": (
                        "La unión de varias subcuencas sobre el pozo 23 hacia J (P25) lleva el tubo al "
                        "límite presurizado mientras la demanda supera más del doble de Qmax."
                    ),
                    "metrics": f"P25: Q_fís = {q25:.4f} m³/s  ·  Util. = {u25:.1f}% (Dem. {d25:.2f}×)",
                },
                {
                    "title": "Amortiguación y descarga en PTAR Punta Canoa",
                    "target_min": 65.0,
                    "step_idx": idx4,
                    "nodes": n_ptar,
                    "pipes": set(p_ptar),
                    "desc": (
                        "Los colectores troncales de 20\" (P29 y P30) reciben la onda laminada aguas arriba "
                        "y estabilizan la entrega al Nodo sumidero 31."
                    ),
                    "metrics": f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  Rebose: {flood4:.0f} m³  ·  Err = {err4:.1e} m³",
                },
            ]

        ranked = sorted(
            (self.result.peak_pipe_utilization.items() if self.result else []),
            key=lambda kv: (
                -kv[1],
                -(self.result.peak_pipe_demand_ratio.get(kv[0], 0.0) if self.result else 0.0),
            ),
        )
        top_head = [pid for pid, _ in ranked[:3]] or p_head8
        top_mid = [pid for pid, _ in ranked[3:6]] or p_25 or top_head
        idx3, s3 = _snap_for_min(40.0)
        return [
            {
                "title": f"Inyección inicial en fuentes ({intensity:.0f} mm/h)",
                "target_min": 5.0,
                "step_idx": idx1,
                "nodes": set(src_ids),
                "pipes": set(src_pipes),
                "desc": "Ingreso inicial por las fuentes activas de la red según el escenario seleccionado.",
                "metrics": f"Q_in = {q_in1:.4f} m³/s  ·  Almacenado: {stor1:.2f} m³",
            },
            {
                "title": "Tramos de mayor exigencia temprana",
                "target_min": 25.0,
                "step_idx": idx2,
                "nodes": _endpoints(top_head),
                "pipes": set(top_head),
                "desc": f"Evaluación de los tramos más exigidos ({', '.join(top_head)}) durante el desarrollo de la onda.",
                "metrics": f"Util. máx: {_max_util(s2, top_head):.2f}%  ·  Almacenado: {s2.total_manhole_storage_m3 if s2 else 0.0:.2f} m³",
            },
            {
                "title": "Propagación y convergencia intermedia",
                "target_min": 40.0,
                "step_idx": idx3,
                "nodes": _endpoints(top_mid),
                "pipes": set(top_mid),
                "desc": f"Seguimiento de la convergencia hidráulica en {', '.join(top_mid)} cerca del pico de tormenta.",
                "metrics": f"Util. máx: {_max_util(s3, top_mid):.2f}%  ·  Almacenado: {s3.total_manhole_storage_m3 if s3 else 0.0:.2f} m³",
            },
            {
                "title": "Entrega final en sumidero PTAR",
                "target_min": 65.0,
                "step_idx": idx4,
                "nodes": n_ptar,
                "pipes": set(p_ptar),
                "desc": "Estabilización y descarga final hacia el sumidero de la red con auditoría de masa.",
                "metrics": f"PTAR = {q_ptar4:.4f} m³/s  ·  Almacenado: {stor4:.2f} m³  ·  Err = {err4:.1e} m³",
            },
        ]

    def toggle_guided_tour(self) -> None:
        if self.dataset is None or self.result is None:
            return
        if self._tour_active:
            self._close_guided_tour()
        else:
            if self._basin_isolated:
                self._basin_isolated = False
                self._apply_basin_isolation()
                self._refresh_inspector()
            if self._map_mode != "instant":
                self._set_map_mode("instant")
            self._tour_active = True
            self._set_btn_variant(self.btn_guided_tour, "dark_primary")
            self._go_tour_stop(0, animate_cam=True)

    def _go_tour_stop(self, stop_idx: int, animate_cam: bool = True) -> None:
        if self.result is None or not self.result.snapshots:
            return
        stops = self._build_tour_stops()
        if not stops:
            return
        if stop_idx >= len(stops):
            self._close_guided_tour()
            return
        stop_idx = max(0, stop_idx)
        self._tour_step = stop_idx
        stop = stops[stop_idx]

        self._player_pause()
        self._stop_traversal_anim(clear_canvas=False)
        self._set_step(int(stop["step_idx"]))  # type: ignore[arg-type]

        focus_nodes: Set[str] = set(stop["nodes"])  # type: ignore[arg-type]
        focus_pipes: Set[str] = set(stop["pipes"])  # type: ignore[arg-type]
        self.network_canvas.set_tour_focus(focus_nodes, focus_pipes)

        cfg = self.result.config
        scen_es = theme.translate_scenario_name(cfg.scenario_name, compact=False)
        scen_short = theme.translate_scenario_name(cfg.scenario_name, compact=True)
        t_real = self.result.snapshots[self.current_step].time_min
        self._lbl_tour_hdr.configure(
            text=f"ESC. {cfg.scenario_id} ({scen_short.upper()}) · HALLAZGO {stop_idx + 1}/{len(stops)} · MIN {t_real:.0f}"
        )
        self._lbl_tour_scenario.configure(
            text=f"Escenario {cfg.scenario_id}: {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
        )
        self._lbl_tour_title.configure(text=str(stop["title"]))
        self._lbl_tour_desc.configure(text=str(stop["desc"]))
        self._lbl_tour_metrics.configure(text=str(stop["metrics"]))
        self._btn_tour_prev.configure(state=tk.NORMAL if stop_idx > 0 else tk.DISABLED)
        self._btn_tour_next.configure(
            text="Finalizar" if stop_idx == len(stops) - 1 else "Siguiente hallazgo"
        )
        card_w = self._fit_tour_card_geometry()
        self._tour_card.place(relx=0.0, rely=1.0, x=12, y=-12, width=card_w, anchor="sw")
        self._tour_card.lift()

        if animate_cam:
            cw = self.network_canvas.winfo_width()
            self.network_canvas.animate_focus_region(
                focus_nodes,
                focus_pipes,
                left_reserve_px=(card_w + 20) if cw >= 520 else 0,
            )
        self.status_var.set(
            f"Guía Esc. {cfg.scenario_id} ({scen_es}) · Parada {stop_idx + 1}/{len(stops)}: {stop['title']}"
        )

    def _close_guided_tour(self, reset_view: bool = True) -> None:
        if not self._tour_active:
            return
        self._tour_active = False
        self._tour_card.place_forget()
        self._set_btn_variant(self.btn_guided_tour, "dark_secondary")
        self.network_canvas.set_tour_focus(None, None)
        if reset_view:
            self.network_canvas.animate_reset_view()
        self.status_var.set("Guía de Sustentación cerrada · Encuadre general restaurado.")
