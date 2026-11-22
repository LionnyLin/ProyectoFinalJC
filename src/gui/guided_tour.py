"""Recorrido guiado (4 hallazgos por escenario): controlador con ficha flotante sobre el lienzo.

El controlador no posee el estado de simulación: lee `app.result`/`app.dataset`, llama a `app.go_to_step` y al lienzo
(`set_tour_focus`, `animate_focus_region`, `animate_reset_view`). Todas las cifras se derivan del `SimulationResult`.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

from src.simulation import SimulationResult, TimeStepSnapshot

from . import theme

if TYPE_CHECKING:
    from .app import BicentenarioSewerApp

_TOUR_MINUTES = (5.0, 25.0, 40.0, 65.0)
_HEAD_NODES = ("17", "19", "20")
_TITLES = {
    1: ("Tiempo seco: sin escorrentía en las fuentes", "Cabeceras de 8\" en reposo hidráulico",
        "Convergencia sin congestión en el tramo P25", "Balance verificado hacia PTAR Punta Canoa"),
    2: ("Escorrentía ligera en las fuentes", "Cabeceras de 8\" bajo lluvia ligera",
        "Convergencia máxima en el colector P25", "Recesión hacia PTAR Punta Canoa"),
    3: ("Inyección en las alcantarillas fuente", "Exigencia inicial en tuberías de 8\"",
        "Convergencia en el tramo P25", "Amortiguación y descarga en PTAR Punta Canoa"),
    4: ("Aporte intenso en las fuentes", "Cabeceras de 8\" y 10\" (P31, P39, P43, P1, P2)",
        "Cuello en cascada: P23, P25 y P28", "Límite de entrega en PTAR 31 y balance de rebose"),
    5: ("Aporte extremo en las fuentes", "Presurización en cabeceras (P31, P39, P43, P12, P13)",
        "Saturación troncal en P25, P23, P28 y P3", "Descarga tope en PTAR 31 y volumen rebosado"),
}
_EXTRA_HEAD = {4: ("P1", "P2"), 5: ("P12", "P13")}
_MID_PIPES = {1: ("P25",), 2: ("P25",), 3: ("P25",), 4: ("P23", "P25", "P28"), 5: ("P23", "P25", "P28", "P3")}


@dataclass(slots=True)
class TourStop:
    """Parada del recorrido: instante, subgrafo en foco y textos calculados del resultado."""

    title: str
    target_min: float
    step_idx: int
    nodes: Set[str]
    pipes: Set[str]
    desc: str
    metrics: str
    extra: dict = field(default_factory=dict)


def _band(u: float) -> str:
    return ("banda verde (0–25 %)" if u <= 25 else "banda amarilla (25–50 %)" if u <= 50 else
            "banda naranja (50–75 %)" if u <= 75 else "banda roja (75–100 %)" if u <= 100 else "sobre su capacidad (>100 %)")


class GuidedTourController:
    """Gestiona botón, ficha flotante, paradas y foco del recorrido guiado."""

    def __init__(self, app: "BicentenarioSewerApp") -> None:
        self.app = app
        self.active = False
        self.step = 0
        self.stops: List[TourStop] = []
        self.card: Optional[tk.Frame] = None
        self._fit_after: Optional[str] = None

    # ── Botón de la topbar ──────────────────────────────────────────────────

    def scenario_id(self) -> int:
        app = self.app
        if app.result is not None:
            return app.result.config.scenario_id
        sc = app.controls._label_to_scenario.get(app.controls._scenario_var.get()) if hasattr(app, "controls") else None
        return sc.scenario_id if sc is not None else 3

    def button_label(self, tier: str) -> str:
        """`Recorrido guiado` en ancho amplio; `Guía Esc. N` en medio/compacto."""
        return "Recorrido guiado" if tier == "wide" else f"Guía Esc. {self.scenario_id()}"

    def update_button(self) -> None:
        app = self.app
        if hasattr(app, "btn_guided_tour"):
            app.btn_guided_tour.configure(text=self.button_label(app._layout_tier or "wide"))

    def style_button(self) -> None:
        self.app._restyle_btn(self.app.btn_guided_tour, "dark_primary" if self.active else "dark")

    # ── Ficha flotante ──────────────────────────────────────────────────────

    def build_card(self, parent: tk.Misc) -> None:
        app, f = self.app, self.app.fonts
        self.card = card = tk.Frame(parent, bg=theme.PAPER_BG, highlightthickness=1, highlightbackground=theme.DOCK_BORDER)
        hdr = tk.Frame(card, bg=theme.ACCENT_PRIMARY)
        hdr.pack(fill=tk.X)
        self.lbl_hdr = tk.Label(hdr, text="", bg=theme.ACCENT_PRIMARY, fg=theme.ACCENT_INK, font=(f["mono_bold"][0], 8, "bold"),
                                padx=9, pady=4, anchor="w")
        self.lbl_hdr.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(hdr, text="×", command=self.close, bg=theme.ACCENT_PRIMARY, fg=theme.ACCENT_INK, activebackground=theme.ACCENT_HOVER,
                  activeforeground=theme.ACCENT_INK, relief="flat", bd=0, padx=8, pady=2, font=(f["body"][0], 10, "bold"),
                  cursor="hand2").pack(side=tk.RIGHT)
        body = tk.Frame(card, bg=theme.PAPER_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        mk = lambda font, fg=theme.INK_PRIMARY, bg=theme.PAPER_BG, **kw: tk.Label(
            body, text="", bg=bg, fg=fg, font=font, anchor="w", justify="left", wraplength=280, **kw)
        self.lbl_scenario = mk((f["mono_bold"][0], 7, "bold"), theme.ACCENT_TEXT_ON_LIGHT)
        self.lbl_title = mk((f["title"][0], 9, "bold"))
        self.lbl_desc = mk((f["body"][0], 8))
        self.lbl_metrics = mk((f["mono_bold"][0], 8, "bold"), bg=theme.PAPER_SUBTLE, padx=6, pady=3,
                              highlightthickness=1, highlightbackground=theme.PAPER_BORDER)
        self.lbl_scenario.pack(fill=tk.X, pady=(0, 2)); self.lbl_title.pack(fill=tk.X, pady=(0, 2))
        self.lbl_desc.pack(fill=tk.X, pady=(0, 4)); self.lbl_metrics.pack(fill=tk.X)
        tk.Frame(card, bg=theme.PAPER_BORDER, height=1).pack(fill=tk.X)
        ftr = tk.Frame(card, bg=theme.PAPER_SUBTLE)
        ftr.pack(fill=tk.X, padx=8, pady=4)
        self.btn_prev = app._btn(ftr, "Anterior", lambda: self.go_to(self.step - 1), "light", padx=7, pady=2)
        self.btn_next = app._btn(ftr, "Siguiente hallazgo", lambda: self.go_to(self.step + 1), "primary", padx=8, pady=2)
        self.lbl_count = tk.Label(ftr, text="", bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=(f["mono_bold"][0], 8, "bold"))
        self.btn_prev.pack(side=tk.LEFT); self.btn_next.pack(side=tk.LEFT, padx=(5, 0))
        app._btn(ftr, "Cerrar", self.close, "light", padx=7, pady=2).pack(side=tk.RIGHT)
        self.lbl_count.pack(side=tk.RIGHT, padx=(0, 8))
        parent.bind("<Configure>", self._on_canvas_configure, add="+")

    def _on_canvas_configure(self, _e: tk.Event) -> None:
        if self.active and self._fit_after is None and not self.app._closing:
            self._fit_after = self.app.after(90, self._deferred_fit)

    def _deferred_fit(self) -> None:
        self._fit_after = None
        if self.active:
            self.fit_card()

    def cancel_timers(self) -> None:
        if self._fit_after is not None:
            try: self.app.after_cancel(self._fit_after)
            except tk.TclError: pass
            self._fit_after = None

    def fit_card(self) -> int:
        """Ajusta el ancho de la ficha al lienzo disponible y devuelve el ancho efectivo."""
        cw = self.app.network_canvas.winfo_width()
        cw = cw if cw > 1 else 680
        card_w = max(200, min(cw - 20, max(290, min(int(round(310 * self.app._dpi_scale)), int(cw * 0.54)))))
        wrap = max(175, card_w - 24)
        for lbl in (self.lbl_scenario, self.lbl_title, self.lbl_desc):
            lbl.configure(wraplength=wrap)
        self.lbl_metrics.configure(wraplength=max(168, wrap - 10))
        if self.card.winfo_manager():
            self.card.place_configure(width=card_w)
        return card_w

    # ── Paradas ─────────────────────────────────────────────────────────────

    def build_stops(self) -> List[TourStop]:
        """Cuatro paradas del escenario vigente con métricas calculadas del `SimulationResult`."""
        app = self.app
        res: Optional[SimulationResult] = app.result
        if app.dataset is None or res is None or not res.snapshots:
            return []
        g, snaps, cfg = app.dataset.graph, res.snapshots, res.config
        sid = cfg.scenario_id

        def snap_at(m: float) -> Tuple[int, TimeStepSnapshot]:
            i = min(range(len(snaps)), key=lambda k: abs(snaps[k].time_min - m))
            return i, snaps[i]

        def pipes_of(*ids: str) -> List[str]:
            return [p for p in ids if g.has_pipe(p)]

        def ends(pids) -> Set[str]:
            out: Set[str] = set()
            for p in pids:
                e = g.get_pipe(p)
                if e is not None:
                    out.update((e.from_node, e.to_node))
            return out

        def stat(s: TimeStepSnapshot, pids) -> Tuple[float, float, int]:
            """(utilización máx %, demanda máx ×Qmax, nº de tuberías >100 %)."""
            st = [s.pipe_states[p] for p in pids if p in s.pipe_states]
            return (max((x.utilization_pct for x in st), default=0.0), max((x.demand_ratio_pct for x in st), default=0.0) / 100.0,
                    sum(1 for x in st if x.utilization_pct > 100.0))

        def nsum(s: TimeStepSnapshot, nids, attr: str) -> float:
            return sum(getattr(s.node_states[n], attr) for n in nids if n in s.node_states)

        src_ids = list(g.source_ids())
        src_pipes = [e.pipe_id for s in src_ids for e in g.outgoing_pipes(s)]
        t_tr = [e.transit_time_min for e in g.pipes()]
        sink = g.sink_ids()
        ptar_pipes = pipes_of("P29", "P30")
        n_ptar = ({"31"} if g.has_node("31") else set(sink)) | ends(ptar_pipes)
        head = pipes_of("P31", "P39", "P43", *_EXTRA_HEAD.get(sid, ()))
        mid = pipes_of(*_MID_PIPES.get(sid, ()))
        if sid not in _TITLES:  # escenario no estándar: tramos más exigidos del resultado
            ranked = [p for p, _ in sorted(res.peak_pipe_utilization.items(), key=lambda kv: (-kv[1], -res.peak_pipe_demand_ratio.get(kv[0], 0.0)))]
            head, mid = ranked[:3] or head, ranked[3:6] or ranked[:3]
        titles = _TITLES.get(sid) or (f"Inyección inicial en fuentes ({cfg.intensity_mm_h:.0f} mm/h)", "Tramos de mayor exigencia temprana",
                                      "Propagación y convergencia intermedia", "Entrega final en el sumidero PTAR")
        t3 = _TOUR_MINUTES[2]
        if sid == 2 and g.has_pipe("P25"):  # lluvia ligera: instante de máxima exigencia de P25
            t3 = max(snaps, key=lambda s: s.pipe_states["P25"].flow_m3s if "P25" in s.pipe_states else 0.0).time_min
        (i1, s1), (i2, s2), (i3, s3), (i4, s4) = (snap_at(m) for m in (_TOUR_MINUTES[0], _TOUR_MINUTES[1], t3, _TOUR_MINUTES[3]))
        heads_nodes = [n for n in _HEAD_NODES if g.has_node(n)] or sorted(ends(head))

        # Parada 1: fuentes
        u1, _, n_over1 = stat(s1, src_pipes)
        if cfg.intensity_mm_h <= 0 and s1.total_source_inflow_m3s <= 1e-12:
            d1 = f"Con I = 0 mm/h el Método Racional no genera escorrentía en las {len(src_ids)} fuentes; solo el caudal sanitario opcional (Q_san) puede aportar."
        else:
            d1 = (f"Las {len(src_ids)} fuentes inyectan el aporte del Método Racional con {cfg.intensity_mm_h:.0f} mm/h; "
                  + (f"{n_over1} de {len(src_pipes)} tuberías de cabecera ya superan su Qmax." if n_over1
                     else f"las tuberías de cabecera operan por debajo de Qmax (máx. {u1:.1f} %)."))
        m1 = (f"Q_in = {s1.total_source_inflow_m3s:.4f} m³/s  ·  Tránsito: {min(t_tr, default=0):.2f}–{max(t_tr, default=0):.2f} min"
              if sid in (1, 3) else f"Q_in = {s1.total_source_inflow_m3s:.4f} m³/s  ·  Pozos: {s1.total_manhole_storage_m3:.1f} m³  ·  Rebose: {s1.total_surface_flooding_m3:.1f} m³")
        # Parada 2: cabeceras
        u2, d2x, n_over2 = stat(s2, head)
        stor2, flood2 = nsum(s2, heads_nodes, "stored_volume_m3"), nsum(s2, heads_nodes, "surface_flooding_m3")
        d2 = (f"Tramos {', '.join(head)}: utilización máxima {u2:.1f} % ({_band(u2)}); {n_over2} de {len(head)} superan su Qmax. "
              + (f"Los pozos asociados acumulan {stor2:.2f} m³ y rebosan {flood2:.2f} m³." if (stor2 or flood2) else "Sin acumulación en pozos ni rebose superficial."))
        m2 = f"Util. máx: {u2:.1f}% ({d2x:.2f}×)  ·  Pozo/Rebose: {stor2:.2f}/{flood2:.2f} m³"
        # Parada 3: convergencia
        u3, d3x, n_over3 = stat(s3, mid)
        q25 = s3.pipe_states["P25"].flow_m3s if "P25" in s3.pipe_states else 0.0
        d3 = (f"Convergencia en {', '.join(mid)} (t = {s3.time_min:.0f} min): utilización máxima {u3:.1f} % ({_band(u3)}), "
              f"demanda {d3x:.2f}× Qmax; rebose acumulado de la red {s3.total_surface_flooding_m3:.1f} m³.")
        m3 = f"{'P25: Q = %.4f m³/s  ·  ' % q25 if 'P25' in mid else ''}Util. máx: {u3:.1f}% ({d3x:.2f}×)  ·  Sobrec.: {n_over3}"
        # Parada 4: PTAR
        u4, _, _ = stat(s4, ptar_pipes)
        err = res.max_mass_balance_error_m3
        d4 = (f"Los colectores {', '.join(ptar_pipes) or 'troncales'} entregan {s4.total_sink_discharge_m3s:.4f} m³/s a la PTAR (utilización {u4:.1f} %, {_band(u4)}). "
              f"La auditoría de masa cierra con error máximo {err:.1e} m³.")
        m4 = f"PTAR 31 = {s4.total_sink_discharge_m3s:.4f} m³/s  ·  Rebose: {s4.total_surface_flooding_m3:.1f} m³  ·  Err = {err:.1e} m³"
        return [
            TourStop(titles[0], _TOUR_MINUTES[0], i1, set(src_ids), set(src_pipes), d1, m1),
            TourStop(titles[1], _TOUR_MINUTES[1], i2, ends(head), set(head), d2, m2),
            TourStop(titles[2], t3, i3, ends(mid), set(mid), d3, m3),
            TourStop(titles[3], _TOUR_MINUTES[3], i4, n_ptar, set(ptar_pipes), d4, m4),
        ]

    # ── Navegación ──────────────────────────────────────────────────────────

    def toggle(self) -> None:
        app = self.app
        if app.dataset is None or app.result is None:
            return
        if self.active:
            self.close()
            return
        if app.basin_focus_active:
            app._clear_basin()
        app._ensure_instant()
        self.active = True
        self.style_button()
        self.go_to(0)

    def go_to(self, idx: int, animate_cam: bool = True) -> None:
        app = self.app
        if app.result is None or not app.result.snapshots or self.card is None:
            return
        self.stops = self.build_stops()
        if not self.stops:
            return
        if idx >= len(self.stops):
            self.close()
            return
        self.step = idx = max(0, idx)
        stop = self.stops[idx]
        app._stop_playback(True)
        app._stop_traversal()
        app.go_to_step(stop.step_idx)
        app.network_canvas.set_tour_focus(stop.nodes, stop.pipes)
        cfg = app.result.config
        full, short = theme.translate_scenario_name(cfg.scenario_name), theme.translate_scenario_name(cfg.scenario_name, short=True)
        n = len(self.stops)
        t_real = app.result.snapshots[app.current_step].time_min
        self.lbl_hdr.configure(text=f"ESC. {cfg.scenario_id} ({short.upper()}) · HALLAZGO {idx + 1}/{n} · MIN {t_real:.0f}")
        self.lbl_scenario.configure(text=f"Escenario {cfg.scenario_id}: {full} ({cfg.intensity_mm_h:.0f} mm/h)")
        self.lbl_title.configure(text=stop.title)
        self.lbl_desc.configure(text=stop.desc)
        self.lbl_metrics.configure(text=stop.metrics)
        self.lbl_count.configure(text=f"{idx + 1} / {n}")
        app._set_btn_enabled(self.btn_prev, idx > 0)
        self.btn_next.configure(text="Finalizar" if idx == n - 1 else "Siguiente hallazgo")
        card_w = self.fit_card()
        self.card.place(relx=0.0, rely=1.0, x=12, y=-12, width=card_w, anchor="sw")
        self.card.lift()
        if animate_cam:
            cw = app.network_canvas.winfo_width()
            app.network_canvas.animate_focus_region(stop.nodes, stop.pipes, left_reserve_px=(card_w + 20) if cw >= 520 else 0)
        app._status_lbl.configure(text=f"Guía Esc. {cfg.scenario_id} ({full}) · Parada {idx + 1}/{n}: {stop.title}", fg=theme.SHELL_TEXT_MUTED)

    def close(self, reset_view: bool = True) -> None:
        """Oculta la ficha, limpia el foco del lienzo y (opcional) restaura el encuadre general."""
        if not self.active:
            return
        app = self.app
        self.active = False
        self.cancel_timers()
        if self.card is not None:
            self.card.place_forget()
        self.style_button()
        self.stops = []
        if not app._closing:
            app.network_canvas.set_tour_focus(None, None)
            if reset_view:
                app.network_canvas.animate_reset_view()
            app._status_lbl.configure(text="Recorrido guiado cerrado · Encuadre general restaurado.", fg=theme.SHELL_TEXT_MUTED)

    def on_result(self, auto_play: bool, prev_scenario_id: Optional[int]) -> None:
        """Tras una simulación: con auto-play cierra el recorrido; si no, recalcula las paradas del escenario vigente."""
        if not self.active:
            return
        if auto_play:
            self.close()
            return
        changed = prev_scenario_id is not None and self.app.result is not None and prev_scenario_id != self.app.result.config.scenario_id
        self.go_to(0 if changed else self.step, animate_cam=changed)
