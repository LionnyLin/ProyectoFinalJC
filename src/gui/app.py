"""Ventana principal del Simulador de Alcantarillado — Ciudad Bicentenario."""

from __future__ import annotations

import os, time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

from src.algorithms import TraversalFrame, TraversalResult, bfs, dfs, search_entity, trace_downstream, trace_upstream
from src.io.data_loader import DataLoadError, NetworkDataset, export_to_csv_dir, load_dataset
from src.simulation import (
    MODEL_ASSUMPTIONS_TEXT, ScenarioSummary, SewerSimulationEngine, SimulationConfig,
    SimulationResult, TimeStepSnapshot, compare_all_scenarios, generate_docx_report, generate_markdown_report,
)
from . import theme
from .charts_panel import ChartsPanel
from .comparison_panel import ComparisonPanel
from .controls_panel import ControlsPanel
from .inspector_panel import CriticalPipesTab, InspectorTab
from .network_canvas import NetworkCanvas

_SPEED_MS: Dict[str, int] = {"0.5x": 500, "1x": 250, "2x": 120, "4x": 60}
_ANIM_MS = 420
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BTN_PAL = {
    "primary": (theme.ACCENT_PRIMARY, theme.ACCENT_HOVER, theme.ACCENT_INK, theme.ACCENT_HOVER, "label"),
    "dark": (theme.SHELL_ELEVATED, theme.SHELL_HOVER, theme.SHELL_TEXT, theme.SHELL_BORDER, "small"),
    "light": (theme.PAPER_SUBTLE, theme.PAPER_HOVER, theme.INK_PRIMARY, theme.PAPER_BORDER, "small"),
}


def _base_key(c: SimulationConfig) -> Tuple[float, float, float, str, str, float]:
    return (c.duration_min, c.storm_duration_min, c.dt_min, c.split_rule, c.source_distribution, c.max_manhole_storage_m3)


class BicentenarioSewerApp(tk.Tk):
    """Orquestador principal de la GUI: dueño único del estado y coordinación de paneles."""

    def __init__(self, initial_data_path: Optional[str] = None) -> None:
        super().__init__()
        self.title("Simulador de Alcantarillado — Ciudad Bicentenario")
        self.geometry("1320x780"); self.minsize(780, 540); self.configure(bg=theme.DOCK_BG)
        self.fonts = theme.resolve_fonts(self)
        self.style = theme.apply_ttk_theme(self, self.fonts)

        # Estado UI (dueño único)
        self.dataset: Optional[NetworkDataset] = None
        self.result: Optional[SimulationResult] = None
        self.current_step, self.is_playing, self.play_speed_ms = 0, False, 250
        self.selected_kind: Optional[str] = None; self.selected_id: Optional[str] = None
        self.traversal_frames: List[TraversalFrame] = []
        self.anim_idx, self.anim_playing = 0, False
        self.cached_comparisons: Optional[List[ScenarioSummary]] = None
        self._play_after_id: Optional[str] = None; self._anim_after_id: Optional[str] = None
        self._traversal_result: Optional[TraversalResult] = None
        self._base_compare_key: Optional[Tuple[float, float, float, str, str, float]] = None
        self._last_chart_pipe: Optional[str] = None; self._updating_slider = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        xlsx = os.path.join(_ROOT_DIR, "data", "DataSetBicentenario.xlsx")
        start_path = initial_data_path or (xlsx if os.path.exists(xlsx) else os.path.join(_ROOT_DIR, "data", "csv"))
        if start_path and os.path.exists(start_path): self.load_data(start_path)

    def _btn(self, parent: tk.Misc, text: str, cmd: Callable[[], None], style: str = "light", padx: int = 8, pady: int = 3) -> tk.Button:
        bg, hov, fg, bdr, fk = _BTN_PAL[style]
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=hov, activeforeground=fg,
                      relief="flat", bd=0, padx=padx, pady=pady, font=self.fonts[fk], cursor="hand2", highlightthickness=1, highlightbackground=bdr)
        b.bind("<Enter>", lambda _e, w=b, h=hov: w.configure(bg=h)); b.bind("<Leave>", lambda _e, w=b, c=bg: w.configure(bg=c))
        return b

    def _build_ui(self) -> None:
        self.topbar = tk.Frame(self, bg=theme.SHELL_BG); self.topbar.pack(side=tk.TOP, fill=tk.X)
        tk.Label(self.topbar, text="Simulador de Alcantarillado — Ciudad Bicentenario", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self.fonts["headline"], padx=12, pady=7).pack(side=tk.LEFT)
        self._status_lbl = tk.Label(self.topbar, text="Listo", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT_MUTED, font=self.fonts["small"], padx=10)
        self._status_lbl.pack(side=tk.RIGHT)
        for text, cmd in (("Supuestos", self._show_assumptions), ("Exportar Word", lambda: self._action_export("docx")), ("Exportar MD/CSV", lambda: self._action_export("md"))):
            self._btn(self.topbar, text, cmd, "dark").pack(side=tk.RIGHT, padx=(0, 5), pady=6)
        tk.Frame(self, bg=theme.SHELL_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        lbar = tk.Frame(self, bg=theme.PAPER_SUBTLE, pady=4, padx=10); lbar.pack(side=tk.TOP, fill=tk.X)
        self._legend_labels: List[Tuple[str, tk.Label]] = []
        for rng, hex_c, _ in theme.COLOR_SCALE_LEGEND:
            tk.Frame(lbar, bg=hex_c, width=11, height=11, highlightbackground=theme.INK_PRIMARY, highlightthickness=1).pack(side=tk.LEFT, padx=(0, 4))
            lbl = tk.Label(lbar, text=f"{rng}: 0", bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, font=self.fonts["mono"])
            lbl.pack(side=tk.LEFT, padx=(0, 12)); self._legend_labels.append((rng, lbl))
        self._btn(lbar, "Centrar vista", lambda: self.network_canvas.reset_view(), padx=7, pady=2).pack(side=tk.RIGHT)
        self._show_util_var, self._show_ids_var = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        for text, var in (("% Util.", self._show_util_var), ("IDs", self._show_ids_var)):
            tk.Checkbutton(lbar, text=text, variable=var, command=lambda: self.network_canvas.set_label_options(self._show_ids_var.get(), self._show_util_var.get()),
                           bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, activebackground=theme.PAPER_SUBTLE, selectcolor=theme.PAPER_BG, font=self.fonts["small"], cursor="hand2").pack(side=tk.RIGHT, padx=(0, 8))
        tk.Frame(self, bg=theme.DOCK_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=theme.DOCK_BORDER, sashwidth=4, bd=0, relief="flat")
        self.paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.controls = ControlsPanel(self.paned, self.fonts, {
            "load_excel": lambda: self._pick_and_load(False), "load_csv": lambda: self._pick_and_load(True), "export_csv": self._action_export_csv,
            "run_simulation": self.run_simulation, "search": self._action_search, "run_traversal": self._action_traversal,
            "trace_downstream": lambda s: self._action_trace(s, False), "trace_upstream": lambda s: self._action_trace(s, True),
            "clear_traversal": self.clear_traversal, "anim_prev": lambda: self.step_traversal_animation(-1),
            "anim_toggle": self.toggle_traversal_animation, "anim_next": lambda: self.step_traversal_animation(1),
        })
        self.paned.add(self.controls, width=290, minsize=240, stretch="never")

        center = tk.Frame(self.paned, bg=theme.DOCK_BG)
        self.network_canvas = NetworkCanvas(center, fonts=self.fonts, on_select=self.select_entity)
        self.network_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        pbar = tk.Frame(center, bg=theme.PAPER_SUBTLE, padx=8, pady=5); pbar.pack(side=tk.TOP, fill=tk.X)
        self._btn_play = self._btn(pbar, "▶ Iniciar", self.toggle_play, "primary", padx=9); self._btn_play.pack(side=tk.LEFT, padx=(0, 4))
        for text, cmd in (("◀ Paso", self.step_backward), ("Paso ▶", self.step_forward), ("↺ Reiniciar", self._reset_playback)):
            self._btn(pbar, text, cmd, padx=6).pack(side=tk.LEFT, padx=(0, 4))
        self._speed_var = tk.StringVar(value="1x")
        scb = ttk.Combobox(pbar, textvariable=self._speed_var, values=tuple(_SPEED_MS), state="readonly", width=4, font=self.fonts["mono"])
        scb.pack(side=tk.LEFT, padx=(2, 8)); scb.bind("<<ComboboxSelected>>", lambda _e: setattr(self, "play_speed_ms", _SPEED_MS.get(self._speed_var.get(), 250)))
        self._time_lbl = tk.Label(pbar, text="t = 0.0 / 90.0 min", bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, font=self.fonts["mono_bold"])
        self._time_lbl.pack(side=tk.RIGHT, padx=(8, 0))
        self._scale = ttk.Scale(pbar, from_=0, to=0, orient=tk.HORIZONTAL, command=self._on_slider_move); self._scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        kbar = tk.Frame(center, bg=theme.SHELL_BG, padx=10, pady=5); kbar.pack(side=tk.TOP, fill=tk.X)
        self._kpi_labels = {k: tk.Label(kbar, text=t, bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self.fonts["mono"])
                            for k, t in (("inflow", "Entrada: 0.000 m³/s"), ("sink", "PTAR 31: 0.000 m³/s"), ("crit", "Crít./Sobr.: 0 / 0"), ("mass", "Error masa: 0.00e+00 m³"))}
        for lbl in self._kpi_labels.values(): lbl.pack(side=tk.LEFT, padx=(0, 14))
        self.paned.add(center, minsize=340, stretch="always")

        self.notebook = ttk.Notebook(self.paned)
        self.inspector_tab = InspectorTab(self.notebook, self.fonts)
        self.critical_tab = CriticalPipesTab(self.notebook, self.fonts, on_select_pipe=lambda pid: self.select_entity("pipe", pid))
        self.charts_panel = ChartsPanel(self.notebook, self.fonts)
        self.comparison_panel = ComparisonPanel(self.notebook, self.fonts, self.run_comparison, lambda sid: (self.controls.select_scenario_by_id(sid), self.run_simulation()))
        for w, title in ((self.inspector_tab, "Inspector"), (self.critical_tab, "Críticas"), (self.charts_panel, "Gráficas"), (self.comparison_panel, "Comparación")):
            self.notebook.add(w, text=title)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.paned.add(self.notebook, width=430, minsize=330, stretch="never")

    # ── Carga, simulación y reproducción (RF01–RF09) ─────────────────────────

    def _active_tab(self) -> int:
        try: return int(self.notebook.index(self.notebook.select()))
        except tk.TclError: return 0
    def _current_snapshot(self) -> Optional[TimeStepSnapshot]:
        return self.result.snapshots[min(max(self.current_step, 0), len(self.result.snapshots) - 1)] if (self.result and self.result.snapshots) else None
    def _cancel_timer(self, attr: str) -> None:
        if (aid := getattr(self, attr, None)) is not None:
            try: self.after_cancel(aid)
            except tk.TclError: pass
            setattr(self, attr, None)

    def load_data(self, path: str, run_initial: bool = True) -> bool:
        try: ds = load_dataset(path)
        except (DataLoadError, OSError, ValueError) as exc:
            messagebox.showerror("Error al cargar datos", str(exc), parent=self)
            self._status_lbl.configure(text="Error de carga — se conserva dataset previo"); return False
        self._stop_playback(); self.clear_traversal()
        self.dataset, self.cached_comparisons, self._base_compare_key = ds, None, None
        self.selected_kind = self.selected_id = self._last_chart_pipe = None
        self.comparison_panel.set_comparisons(None, is_visible=self._active_tab() == 3)
        self.controls.populate_dataset(ds)
        if any(s.scenario_id == 3 for s in ds.scenarios): self.controls.select_scenario_by_id(3)
        self.network_canvas.set_graph(ds.graph)
        self._status_lbl.configure(text=f"Dataset cargado: {os.path.basename(ds.source_path)}")
        if run_initial: self.run_simulation()
        return True

    def run_simulation(self) -> Optional[SimulationResult]:
        if self.dataset is None: return None
        self._stop_playback()
        try: cfg = self.controls.get_simulation_config()
        except ValueError as exc: messagebox.showerror("Parámetros inválidos", str(exc), parent=self); return None
        key = _base_key(cfg)
        if self._base_compare_key is not None and key != self._base_compare_key:
            self.cached_comparisons = None; self.comparison_panel.invalidate()
        self._base_compare_key = key
        res = SewerSimulationEngine(self.dataset.graph, self.dataset.basin).run(cfg)
        self.result, self.current_step, self._updating_slider = res, 0, True
        try: self._scale.configure(from_=0, to=max(0, len(res.snapshots) - 1)); self._scale.set(0)
        finally: self._updating_slider = False
        self._btn_play.configure(text="▶ Iniciar")
        self._last_chart_pipe = self.selected_id if self.selected_kind == "pipe" else None
        self.charts_panel.set_result(res, self._last_chart_pipe, is_visible=self._active_tab() == 2)
        self.go_to_step(0)
        self._status_lbl.configure(text=f"Esc. {cfg.scenario_id} ({theme.translate_scenario_name(cfg.scenario_name)}) en {res.execution_time_ms:.1f} ms")
        return res

    def go_to_step(self, idx: int) -> None:
        if not self.result or not self.result.snapshots or self.dataset is None: return
        snaps = self.result.snapshots
        self.current_step = max(0, min(int(idx), len(snaps) - 1))
        snap = snaps[self.current_step]
        self._updating_slider = True
        try: self._scale.set(self.current_step)
        finally: self._updating_slider = False
        self._time_lbl.configure(text=f"t = {snap.time_min:.1f} / {snaps[-1].time_min:.1f} min")
        self.network_canvas.set_snapshot(snap)
        tab = self._active_tab()
        self.inspector_tab.update_view(self.dataset.graph, snap, self.result, self.selected_kind, self.selected_id)
        self.critical_tab.update_view(self.dataset.graph, snap, is_visible=tab == 1)
        if tab == 1 and self.selected_kind == "pipe": self.critical_tab.select_pipe(self.selected_id)
        self.charts_panel.update_cursor(snap.time_min, is_visible=tab == 2)
        counts = [0] * len(theme.COLOR_SCALE_LEGEND)
        for ps in snap.pipe_states.values():
            if 0 <= ps.category.tier_index < len(counts): counts[ps.category.tier_index] += 1
        for (rng, lbl), cnt in zip(self._legend_labels, counts): lbl.configure(text=f"{rng}: {cnt}")
        for k, txt in (("inflow", f"Entrada: {snap.total_source_inflow_m3s:.4f} m³/s"), ("sink", f"PTAR 31: {snap.total_sink_discharge_m3s:.4f} m³/s"),
                       ("crit", f"Crít./Sobr.: {len(snap.critical_pipe_ids)} / {len(snap.overloaded_pipe_ids)}"), ("mass", f"Error masa: {snap.mass_balance_error_m3:.2e} m³")):
            self._kpi_labels[k].configure(text=txt)

    def _on_slider_move(self, value: str) -> None:
        if not self._updating_slider and self.result and (idx := int(round(float(value)))) != self.current_step:
            self._stop_playback(True); self.go_to_step(idx)
    def step_forward(self) -> None: self._stop_playback(True); self.go_to_step(self.current_step + 1)
    def step_backward(self) -> None: self._stop_playback(True); self.go_to_step(self.current_step - 1)
    def _reset_playback(self) -> None: self._stop_playback(False); self.go_to_step(0)
    def _stop_playback(self, resume: bool = False) -> None:
        self.is_playing = False; self._cancel_timer("_play_after_id")
        if hasattr(self, "_btn_play"): self._btn_play.configure(text="▶ Reanudar" if (resume and self.current_step > 0) else "▶ Iniciar")
    def toggle_play(self) -> None:
        if not self.result or not self.result.snapshots: return
        if self.is_playing: self._stop_playback(True); return
        if self.current_step >= len(self.result.snapshots) - 1: self.go_to_step(0)
        self.is_playing = True; self._btn_play.configure(text="⏸ Pausar")
        self._play_after_id = self.after(self.play_speed_ms, self._play_tick)
    def _play_tick(self) -> None:
        self._play_after_id = None
        if not self.is_playing or not self.result: return
        if self.current_step + 1 < len(self.result.snapshots):
            self.go_to_step(self.current_step + 1); self._play_after_id = self.after(self.play_speed_ms, self._play_tick)
        else: self._stop_playback(False)

    # ── Selección, búsqueda O(1), recorridos BFS/DFS y animación ─────────────

    def select_entity(self, kind: Optional[str], entity_id: Optional[str]) -> None:
        new_sel = (kind, entity_id) if kind in ("pipe", "node") and entity_id else (None, None)
        if new_sel == (self.selected_kind, self.selected_id):
            return
        self.selected_kind, self.selected_id = new_sel
        self.network_canvas.set_selected(self.selected_kind, self.selected_id)
        self.inspector_tab.update_view(self.dataset.graph if self.dataset else None, self._current_snapshot(), self.result, self.selected_kind, self.selected_id)
        pipe_id = self.selected_id if self.selected_kind == "pipe" else None
        self.critical_tab.select_pipe(pipe_id)
        if pipe_id != self._last_chart_pipe:
            self._last_chart_pipe = pipe_id; self.charts_panel.set_result(self.result, pipe_id, is_visible=self._active_tab() == 2)

    def _action_search(self, query: str) -> None:
        if self.dataset is None: return
        kind, eid = search_entity(self.dataset.graph, query)
        if not kind or not eid: self._status_lbl.configure(text=f"No se encontró «{query}» en la red"); return
        self.select_entity(kind, eid); self.notebook.select(0)
        self._status_lbl.configure(text=f"Encontrado O(1): {'Tubería' if kind == 'pipe' else 'Nodo'} {eid}")

    def _on_tab_changed(self, _event: tk.Event) -> None:
        tab = self._active_tab()
        if tab == 1 and self.dataset is not None:
            self.critical_tab.mark_visible(self.dataset.graph, self._current_snapshot())
            if self.selected_kind == "pipe": self.critical_tab.select_pipe(self.selected_id)
        elif tab == 2: self.charts_panel.mark_visible()
        elif tab == 3: self.comparison_panel.mark_visible()

    def _stop_traversal(self) -> None:
        self.anim_playing = False; self._cancel_timer("_anim_after_id")
        if hasattr(self, "controls"): self.controls.set_traversal_playing(False)

    def _action_traversal(self, algo: str, start_id: str, target_id: Optional[str], animate: bool) -> None:
        if self.dataset is None: return
        self._stop_traversal()
        res = (bfs if algo.upper() == "BFS" else dfs)(self.dataset.graph, start_id, target_id, record_frames=animate)
        self._traversal_result, self.traversal_frames, self.anim_idx = res, res.frames if animate else [], 0
        if animate:
            if not self.traversal_frames: return
            self.anim_playing = True; self._render_traversal_frame()
            if len(self.traversal_frames) > 1: self._anim_after_id = self.after(_ANIM_MS, self._anim_tick)
            else: self._stop_traversal()
            return
        self.network_canvas.set_traversal_highlight(res.visited_order, res.traversed_edges, res.path_nodes, res.path_pipes, res.target_node if res.target_reached else res.start_node)
        msg = f"{res.algorithm}: {len(res.visited_order)} nodos" + (f" · Ruta ({len(res.path_pipes)}): {' → '.join(res.path_nodes)}" if (target_id and res.target_reached) else (f" · Sin ruta a {target_id}" if target_id else ""))
        self.controls.update_traversal_view(None, summary_text=msg, playing=False); self._status_lbl.configure(text=msg)

    def start_traversal_animation(self, algo: str, start_id: str, target_id: Optional[str] = None) -> None:
        self._action_traversal(algo, start_id, target_id, animate=True)

    def _render_traversal_frame(self) -> None:
        f = self.traversal_frames[self.anim_idx]
        lr = self._traversal_result if self.anim_idx == len(self.traversal_frames) - 1 else None
        self.network_canvas.set_traversal_highlight(f.visited_nodes, f.visited_edges, lr.path_nodes if lr else None, lr.path_pipes if lr else None, f.current_node, f.active_edge)
        self.controls.update_traversal_view(f, playing=self.anim_playing)

    def _anim_tick(self) -> None:
        self._anim_after_id = None
        if not self.anim_playing or not self.traversal_frames: return
        if self.anim_idx + 1 < len(self.traversal_frames):
            self.anim_idx += 1; self._render_traversal_frame(); self._anim_after_id = self.after(_ANIM_MS, self._anim_tick)
        else: self._stop_traversal()

    def step_traversal_animation(self, delta: int) -> None:
        if not self.traversal_frames: return
        self._stop_traversal(); self.anim_idx = max(0, min(self.anim_idx + int(delta), len(self.traversal_frames) - 1)); self._render_traversal_frame()

    def toggle_traversal_animation(self) -> None:
        if not self.traversal_frames: return
        if self.anim_playing: self._stop_traversal(); return
        if self.anim_idx >= len(self.traversal_frames) - 1: self.anim_idx = 0
        self.anim_playing = True; self._render_traversal_frame(); self._anim_after_id = self.after(_ANIM_MS, self._anim_tick)

    def _action_trace(self, start_id: str, upstream: bool) -> None:
        if self.dataset is None or not start_id: return
        self._stop_traversal()
        nodes, pipes = trace_upstream(self.dataset.graph, start_id) if upstream else ((r := trace_downstream(self.dataset.graph, start_id)).visited_order, r.traversed_edges)
        self._traversal_result, self.traversal_frames, self.anim_idx = None, [], 0
        self.network_canvas.set_traversal_highlight(visited_nodes=nodes, visited_edges=pipes, current_node=start_id)
        msg = f"Aguas {'arriba de' if upstream else 'abajo desde'} {start_id}: {len(nodes)} nodos, {len(pipes)} tuberías"
        self.controls.update_traversal_view(None, summary_text=msg, playing=False); self._status_lbl.configure(text=msg)

    def clear_traversal(self) -> None:
        self._stop_traversal(); self._traversal_result, self.traversal_frames, self.anim_idx = None, [], 0
        self.network_canvas.clear_traversal_highlight(); self.controls.update_traversal_view(None)

    # ── Comparación, I/O, reportes y cierre ──────────────────────────────────

    def run_comparison(self) -> Optional[List[ScenarioSummary]]:
        if self.dataset is None: return None
        try: cfg = self.controls.get_simulation_config()
        except ValueError as exc: messagebox.showerror("Parámetros inválidos", str(exc), parent=self); return None
        t0 = time.perf_counter(); summaries = compare_all_scenarios(self.dataset, cfg); elapsed = (time.perf_counter() - t0) * 1000.0
        self.cached_comparisons, self._base_compare_key = summaries, _base_key(cfg)
        self.comparison_panel.set_comparisons(summaries, elapsed_ms=elapsed, is_visible=self._active_tab() == 3)
        self._status_lbl.configure(text=f"Comparación de {len(summaries)} escenarios ({elapsed:.0f} ms)")
        return summaries

    def _pick_and_load(self, is_dir: bool) -> None:
        p = filedialog.askdirectory(parent=self, title="Seleccionar carpeta CSV") if is_dir else filedialog.askopenfilename(parent=self, title="Cargar dataset Excel", filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")])
        if p: self.load_data(p)
    def _action_export_csv(self) -> None:
        if self.dataset and (out_dir := filedialog.askdirectory(parent=self, title="Exportar dataset a carpeta CSV")):
            try: export_to_csv_dir(self.dataset, out_dir); self._status_lbl.configure(text=f"CSV exportado: {out_dir}")
            except OSError as exc: messagebox.showerror("Error al exportar CSV", str(exc), parent=self)

    def _action_export(self, fmt: str) -> None:
        if self.dataset is None or self.result is None:
            messagebox.showwarning("Sin simulación", "Ejecute una simulación antes de exportar.", parent=self); return
        if self.cached_comparisons is None: self.run_comparison()
        is_docx = fmt == "docx"
        p = filedialog.asksaveasfilename(parent=self, title="Exportar reporte Word (.docx)" if is_docx else "Exportar reporte Markdown / CSV",
                                         defaultextension=".docx" if is_docx else ".md", filetypes=[("Word", "*.docx")] if is_docx else [("Markdown", "*.md")])
        if not p: return
        out = (generate_docx_report if is_docx else generate_markdown_report)(self.dataset, self.result, self.cached_comparisons, p)
        self._status_lbl.configure(text=f"Reporte guardado: {os.path.basename(out)}")
        messagebox.showinfo("Reporte exportado", f"Archivo generado en:\n{out}", parent=self)

    def _show_assumptions(self) -> None:
        win = tk.Toplevel(self)
        win.title("Supuestos del Modelo Computacional"); win.configure(bg=theme.PAPER_BG); win.resizable(False, False); win.transient(self)
        tk.Label(win, text="SUPUESTOS DEL MODELO HIDRÁULICO", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self.fonts["title"], anchor="w", padx=12, pady=8).pack(fill=tk.X)
        tk.Label(win, text=MODEL_ASSUMPTIONS_TEXT, bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=self.fonts["body"], justify="left", anchor="w", wraplength=520, padx=14, pady=12).pack(fill=tk.BOTH, expand=True)
        self._btn(win, "Cerrar", win.destroy, "primary", padx=14, pady=4).pack(pady=(0, 12))

    def _on_close(self) -> None:
        self._stop_playback(); self._stop_traversal()
        self.network_canvas.cancel_pending(); self.charts_panel._cancel_cursor_timer()
        try: self.destroy()
        except tk.TclError: pass
