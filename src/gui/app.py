"""Aplicación principal de escritorio (Tkinter) para la red de Ciudad Bicentenario."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from src.algorithms import (
    bfs,
    dfs,
    rank_critical_pipes,
    search_entities,
    trace_downstream,
    trace_upstream,
)
from src.io.data_loader import (
    DataLoadError,
    NetworkDataset,
    export_to_csv_dir,
    load_dataset,
)
from src.simulation import (
    ScenarioSummary,
    SewerSimulationEngine,
    SimulationConfig,
    SimulationResult,
    TimeStepSnapshot,
    compare_all_scenarios,
    generate_markdown_report,
)
from . import theme
from .charts_panel import ComparisonChartsPanel, TemporalChartsPanel
from .network_canvas import NetworkCanvas


class BicentenarioSewerApp(tk.Tk):
    """Interfaz gráfica principal para simulación y análisis de la red de alcantarillado."""

    def __init__(self, initial_data_path: Optional[str] = None) -> None:
        super().__init__()
        self.title("Simulador de Alcantarillado — Ciudad Bicentenario (Cartagena)")
        self.geometry("1460x880")
        self.minsize(1200, 720)
        self.configure(bg=theme.BG_DARK)

        self.dataset: Optional[NetworkDataset] = None
        self.engine: Optional[SewerSimulationEngine] = None
        self.result: Optional[SimulationResult] = None
        self.comparisons: List[ScenarioSummary] = []

        self.current_step: int = 0
        self.is_playing: bool = False
        self._after_id: Optional[str] = None
        self._selected_pipe_id: Optional[str] = None
        self._selected_node_id: Optional[str] = None
        self._updating_slider: bool = False

        # Variables de control de UI
        self.var_scenario = tk.StringVar()
        self.var_duration = tk.DoubleVar(value=90.0)
        self.var_storm_dur = tk.DoubleVar(value=60.0)
        self.var_dt = tk.DoubleVar(value=1.0)
        self.var_ingress_pct = tk.DoubleVar(value=2.5)
        self.var_dry_flow = tk.DoubleVar(value=0.003)
        self.var_split_rule = tk.StringVar(value="proportional")
        self.var_hyetograph = tk.StringVar(value="uniform")
        self.var_speed = tk.StringVar(value="2x")
        self.var_search = tk.StringVar()
        self.var_bfs_start = tk.StringVar(value="6")
        self.var_bfs_target = tk.StringVar(value="31")
        self.var_crit_filter = tk.StringVar(value="all")
        self.var_show_pipe_labels = tk.BooleanVar(value=True)
        self.var_show_util_labels = tk.BooleanVar(value=True)

        self._legend_count_labels: List[tk.Label] = []

        self._configure_styles()
        self._build_layout()

        # Cargar dataset inicial automáticamente si existe
        default_path = initial_data_path or self._find_default_dataset()
        if default_path:
            self._load_path(default_path, silent_error=False)
            if self.dataset is not None:
                self.run_simulation()

    def _find_default_dataset(self) -> Optional[str]:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        xlsx = os.path.join(base, "data", "DataSetBicentenario.xlsx")
        if os.path.isfile(xlsx):
            return xlsx
        csv_dir = os.path.join(base, "data", "csv")
        if os.path.isdir(csv_dir):
            return csv_dir
        return None

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=theme.BG_PANEL, foreground=theme.TEXT_PRIMARY, font=("Segoe UI", 9))
        style.configure("TFrame", background=theme.BG_PANEL)
        style.configure("Dark.TFrame", background=theme.BG_DARK)
        style.configure("Card.TFrame", background=theme.BG_CARD)
        style.configure("TLabel", background=theme.BG_PANEL, foreground=theme.TEXT_PRIMARY)
        style.configure("Muted.TLabel", background=theme.BG_PANEL, foreground=theme.TEXT_MUTED, font=("Segoe UI", 8))
        style.configure("Card.TLabel", background=theme.BG_CARD, foreground=theme.TEXT_PRIMARY)
        style.configure("TNotebook", background=theme.BG_PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", background=theme.BG_CARD, foreground=theme.TEXT_SECONDARY, padding=(10, 5))
        style.map(
            "TNotebook.Tab",
            background=[("selected", theme.ACCENT_BLUE)],
            foreground=[("selected", "#0f172a")],
        )
        style.configure(
            "Treeview",
            background=theme.BG_CANVAS,
            foreground=theme.TEXT_PRIMARY,
            fieldbackground=theme.BG_CANVAS,
            rowheight=23,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=theme.BG_CARD,
            foreground=theme.TEXT_PRIMARY,
            font=("Segoe UI", 8, "bold"),
        )
        style.map("Treeview", background=[("selected", "#1d4ed8")])
        style.configure("TCombobox", fieldbackground=theme.BG_CANVAS, background=theme.BG_CARD, foreground=theme.TEXT_PRIMARY)

    def _build_layout(self) -> None:
        # Barra superior
        topbar = tk.Frame(self, bg=theme.BG_PANEL, height=48, bd=0)
        topbar.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self, bg=theme.BORDER_COLOR, height=1).pack(side=tk.TOP, fill=tk.X)

        tk.Label(
            topbar,
            text="Red de Alcantarillado — Ciudad Bicentenario (Cartagena)",
            bg=theme.BG_PANEL,
            fg=theme.TEXT_PRIMARY,
            font=("Segoe UI", 12, "bold"),
        ).pack(side=tk.LEFT, padx=14, pady=8)

        btn_specs = [
            ("Cargar Excel", self._action_load_excel, "#0284c7"),
            ("Cargar CSV", self._action_load_csv, "#0369a1"),
            ("Exportar CSV", self._action_export_csv, "#334155"),
            ("Generar Reporte", self._action_generate_report, "#059669"),
            ("Supuestos", self._action_show_assumptions, "#475569"),
        ]
        for text, cmd, bg in reversed(btn_specs):
            tk.Button(
                topbar,
                text=text,
                command=cmd,
                bg=bg,
                fg="#ffffff",
                activebackground="#38bdf8",
                relief="flat",
                padx=10,
                pady=4,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            ).pack(side=tk.RIGHT, padx=4, pady=8)

        # Contenedor principal de 3 columnas
        main_pane = tk.PanedWindow(
            self,
            orient=tk.HORIZONTAL,
            bg=theme.BORDER_COLOR,
            sashwidth=4,
            bd=0,
        )
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Panel izquierdo con scroll
        left_container = tk.Frame(main_pane, bg=theme.BG_PANEL, width=320)
        left_canvas = tk.Canvas(left_container, bg=theme.BG_PANEL, highlightthickness=0, width=310)
        left_scroll = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=left_canvas.yview)
        self.left_frame = tk.Frame(left_canvas, bg=theme.BG_PANEL)
        self.left_frame.bind(
            "<Configure>",
            lambda _e: left_canvas.configure(scrollregion=left_canvas.bbox("all")),
        )
        left_canvas.create_window((0, 0), window=self.left_frame, anchor="nw", width=308)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        main_pane.add(left_container, minsize=290)

        self._build_left_controls(self.left_frame)

        # Panel central (Canvas del grafo + controles temporales)
        center_frame = tk.Frame(main_pane, bg=theme.BG_DARK)
        main_pane.add(center_frame, minsize=520)
        self._build_center_panel(center_frame)

        # Panel derecho (Notebook con Inspector, Críticas, Gráficas, Comparación)
        right_frame = tk.Frame(main_pane, bg=theme.BG_PANEL, width=430)
        main_pane.add(right_frame, minsize=380)
        self._build_right_panel(right_frame)

        # Barra de estado inferior
        self.status_var = tk.StringVar(value="Listo.")
        statusbar = tk.Frame(self, bg=theme.BG_PANEL, height=24)
        statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(
            statusbar,
            textvariable=self.status_var,
            bg=theme.BG_PANEL,
            fg=theme.TEXT_SECONDARY,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(side=tk.LEFT, padx=10, pady=2)

    def _make_section(self, parent: tk.Misc, title: str) -> tk.Frame:
        card = tk.Frame(parent, bg=theme.BG_CARD, highlightbackground=theme.BORDER_COLOR, highlightthickness=1)
        card.pack(fill=tk.X, padx=8, pady=5)
        tk.Label(
            card,
            text=title,
            bg=theme.BG_CARD,
            fg=theme.ACCENT_BLUE,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=8, pady=(6, 4))
        body = tk.Frame(card, bg=theme.BG_CARD)
        body.pack(fill=tk.X, padx=8, pady=(0, 8))
        return body

    def _build_left_controls(self, parent: tk.Frame) -> None:
        # 1. Escenario y Parámetros
        sec_sim = self._make_section(parent, "1. Escenario y Parámetros Hidráulicos")

        tk.Label(sec_sim, text="Escenario de precipitación:", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=("Segoe UI", 8)).pack(anchor="w")
        self.combo_scenario = ttk.Combobox(sec_sim, textvariable=self.var_scenario, state="readonly")
        self.combo_scenario.pack(fill=tk.X, pady=(2, 6))

        grid = tk.Frame(sec_sim, bg=theme.BG_CARD)
        grid.pack(fill=tk.X)
        fields = [
            ("Duración sim. (min):", self.var_duration, 10, 360, 10),
            ("Duración lluvia (min):", self.var_storm_dur, 0, 360, 5),
            ("Paso Δt (min):", self.var_dt, 0.5, 10.0, 0.5),
            ("Ingreso pluvial (%):", self.var_ingress_pct, 0.5, 100.0, 0.5),
            ("Caudal sanitario (m³/s):", self.var_dry_flow, 0.0, 0.05, 0.001),
        ]
        for row_i, (label, var, frm, to, inc) in enumerate(fields):
            tk.Label(grid, text=label, bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=("Segoe UI", 8)).grid(
                row=row_i, column=0, sticky="w", pady=2
            )
            tk.Spinbox(
                grid,
                textvariable=var,
                from_=frm,
                to=to,
                increment=inc,
                width=9,
                bg=theme.BG_CANVAS,
                fg=theme.TEXT_PRIMARY,
                buttonbackground=theme.BG_PANEL,
                relief="flat",
                font=("Segoe UI", 9),
            ).grid(row=row_i, column=1, sticky="e", pady=2)
        grid.columnconfigure(0, weight=1)

        # Presets rápidos del método racional vs calibrado
        preset_row = tk.Frame(sec_sim, bg=theme.BG_CARD)
        preset_row.pack(fill=tk.X, pady=(4, 4))
        tk.Button(
            preset_row,
            text="Calibrado (2.5%)",
            command=lambda: self._apply_preset(2.5, 0.003),
            bg="#334155",
            fg="#ffffff",
            relief="flat",
            font=("Segoe UI", 8),
            cursor="hand2",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(
            preset_row,
            text="Racional 100%",
            command=lambda: self._apply_preset(100.0, 0.0),
            bg="#334155",
            fg="#ffffff",
            relief="flat",
            font=("Segoe UI", 8),
            cursor="hand2",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

        row_rules = tk.Frame(sec_sim, bg=theme.BG_CARD)
        row_rules.pack(fill=tk.X, pady=2)
        tk.Label(row_rules, text="Bifurcación:", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=("Segoe UI", 8)).pack(side=tk.LEFT)
        ttk.Combobox(
            row_rules,
            textvariable=self.var_split_rule,
            values=["proportional", "equal"],
            state="readonly",
            width=12,
        ).pack(side=tk.RIGHT)

        row_hyeto = tk.Frame(sec_sim, bg=theme.BG_CARD)
        row_hyeto.pack(fill=tk.X, pady=2)
        tk.Label(row_hyeto, text="Hietograma:", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=("Segoe UI", 8)).pack(side=tk.LEFT)
        ttk.Combobox(
            row_hyeto,
            textvariable=self.var_hyetograph,
            values=["uniform", "triangular"],
            state="readonly",
            width=12,
        ).pack(side=tk.RIGHT)

        tk.Button(
            sec_sim,
            text="▶  Ejecutar Simulación",
            command=self.run_simulation,
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#38bdf8",
            relief="flat",
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(fill=tk.X, pady=(6, 0))

        # 2. Leyenda de colores (Sección 7)
        sec_leg = self._make_section(parent, "2. Escala de Utilización (Sección 7)")
        self._legend_count_labels.clear()
        for rng, color_hex, desc in theme.COLOR_SCALE_LEGEND:
            row = tk.Frame(sec_leg, bg=theme.BG_CARD)
            row.pack(fill=tk.X, pady=1.5)
            swatch = tk.Canvas(row, width=14, height=14, bg=color_hex, highlightthickness=1, highlightbackground="#0f172a")
            swatch.pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(row, text=f"{rng}  {desc}", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=("Segoe UI", 8)).pack(side=tk.LEFT)
            cnt_lbl = tk.Label(row, text="0", bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=("Segoe UI", 8, "bold"))
            cnt_lbl.pack(side=tk.RIGHT)
            self._legend_count_labels.append(cnt_lbl)

        # 3. Consulta rápida y Recorridos BFS / DFS
        sec_alg = self._make_section(parent, "3. Consultas y Recorridos (BFS / DFS)")

        search_row = tk.Frame(sec_alg, bg=theme.BG_CARD)
        search_row.pack(fill=tk.X, pady=(0, 5))
        ent = tk.Entry(
            search_row,
            textvariable=self.var_search,
            bg=theme.BG_CANVAS,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
        )
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        ent.bind("<Return>", lambda _e: self._action_search())
        tk.Button(
            search_row,
            text="Buscar",
            command=self._action_search,
            bg="#0284c7",
            fg="#ffffff",
            relief="flat",
            padx=8,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(4, 0))

        trav_grid = tk.Frame(sec_alg, bg=theme.BG_CARD)
        trav_grid.pack(fill=tk.X, pady=2)
        tk.Label(trav_grid, text="Origen:", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w")
        self.combo_bfs_start = ttk.Combobox(trav_grid, textvariable=self.var_bfs_start, width=10)
        self.combo_bfs_start.grid(row=0, column=1, sticky="e", pady=2)
        tk.Label(trav_grid, text="Destino:", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w")
        self.combo_bfs_target = ttk.Combobox(trav_grid, textvariable=self.var_bfs_target, width=10)
        self.combo_bfs_target.grid(row=1, column=1, sticky="e", pady=2)
        trav_grid.columnconfigure(0, weight=1)

        btn_trav = tk.Frame(sec_alg, bg=theme.BG_CARD)
        btn_trav.pack(fill=tk.X, pady=4)
        for text, cmd in [
            ("BFS", lambda: self._run_traversal("BFS")),
            ("DFS", lambda: self._run_traversal("DFS")),
            ("Aguas Abajo", lambda: self._run_trace("down")),
            ("Limpiar", self._clear_highlights),
        ]:
            tk.Button(
                btn_trav,
                text=text,
                command=cmd,
                bg="#334155",
                fg="#ffffff",
                relief="flat",
                font=("Segoe UI", 8, "bold"),
                cursor="hand2",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1.5)

        self.txt_traversal = tk.Text(
            sec_alg,
            height=5,
            bg=theme.BG_CANVAS,
            fg=theme.TEXT_SECONDARY,
            relief="flat",
            font=("Consolas", 8),
            wrap=tk.WORD,
        )
        self.txt_traversal.pack(fill=tk.X, pady=(2, 0))
        self.txt_traversal.configure(state=tk.DISABLED)

    def _build_center_panel(self, parent: tk.Frame) -> None:
        # Barra superior del canvas
        canvas_bar = tk.Frame(parent, bg=theme.BG_PANEL, height=34)
        canvas_bar.pack(side=tk.TOP, fill=tk.X)

        self.lbl_clock = tk.Label(
            canvas_bar,
            text="t = 0.0 min  |  Escenario: -",
            bg=theme.BG_PANEL,
            fg=theme.ACCENT_GOLD,
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_clock.pack(side=tk.LEFT, padx=10, pady=5)

        tk.Button(
            canvas_bar,
            text="Ajustar Vista",
            command=lambda: self.network_canvas.reset_view(),
            bg="#334155",
            fg="#ffffff",
            relief="flat",
            padx=8,
            font=("Segoe UI", 8),
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=6, pady=4)

        tk.Checkbutton(
            canvas_bar,
            text="% Util.",
            variable=self.var_show_util_labels,
            command=self._toggle_labels,
            bg=theme.BG_PANEL,
            fg=theme.TEXT_SECONDARY,
            selectcolor=theme.BG_CANVAS,
            activebackground=theme.BG_PANEL,
            font=("Segoe UI", 8),
        ).pack(side=tk.RIGHT, padx=4)

        tk.Checkbutton(
            canvas_bar,
            text="IDs Tuberías",
            variable=self.var_show_pipe_labels,
            command=self._toggle_labels,
            bg=theme.BG_PANEL,
            fg=theme.TEXT_SECONDARY,
            selectcolor=theme.BG_CANVAS,
            activebackground=theme.BG_PANEL,
            font=("Segoe UI", 8),
        ).pack(side=tk.RIGHT, padx=4)

        # Canvas interactivo del grafo
        self.network_canvas = NetworkCanvas(
            parent,
            on_select_pipe=self._on_pipe_selected,
            on_select_node=self._on_node_selected,
        )
        self.network_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Barra de control temporal (RF09)
        player = tk.Frame(parent, bg=theme.BG_PANEL)
        player.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))

        controls_row = tk.Frame(player, bg=theme.BG_PANEL)
        controls_row.pack(fill=tk.X, padx=8, pady=(6, 2))

        for label, cmd, bg in [
            ("⏮ Inicio", self._player_reset, "#334155"),
            ("◀ -1", lambda: self._player_step(-1), "#334155"),
            ("▶ Iniciar / Reanudar", self._player_play, "#059669"),
            ("⏸ Pausar", self._player_pause, "#d97706"),
            ("+1 ▶", lambda: self._player_step(1), "#334155"),
        ]:
            tk.Button(
                controls_row,
                text=label,
                command=cmd,
                bg=bg,
                fg="#ffffff",
                relief="flat",
                padx=8,
                pady=3,
                font=("Segoe UI", 8, "bold"),
                cursor="hand2",
            ).pack(side=tk.LEFT, padx=2)

        tk.Label(controls_row, text="Vel:", bg=theme.BG_PANEL, fg=theme.TEXT_MUTED, font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(10, 2))
        ttk.Combobox(
            controls_row,
            textvariable=self.var_speed,
            values=["1x", "2x", "5x", "10x"],
            state="readonly",
            width=4,
        ).pack(side=tk.LEFT)

        self.lbl_mass_audit = tk.Label(
            controls_row,
            text="Balance de masa: -",
            bg=theme.BG_PANEL,
            fg="#34d399",
            font=("Segoe UI", 8, "bold"),
        )
        self.lbl_mass_audit.pack(side=tk.RIGHT, padx=4)

        self.timeline_slider = tk.Scale(
            player,
            from_=0,
            to=0,
            orient=tk.HORIZONTAL,
            showvalue=False,
            command=self._on_slider_move,
            bg=theme.BG_PANEL,
            fg=theme.TEXT_PRIMARY,
            troughcolor=theme.BG_CANVAS,
            highlightthickness=0,
            activebackground=theme.ACCENT_BLUE,
        )
        self.timeline_slider.pack(fill=tk.X, padx=8, pady=(0, 6))

    def _build_right_panel(self, parent: tk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Tab 1: Inspector y Resumen
        tab_info = ttk.Frame(self.notebook)
        self.notebook.add(tab_info, text="Inspector y Resumen")
        self.txt_inspector = tk.Text(
            tab_info,
            bg=theme.BG_CANVAS,
            fg=theme.TEXT_PRIMARY,
            relief="flat",
            font=("Consolas", 9),
            wrap=tk.WORD,
            padx=10,
            pady=8,
        )
        self.txt_inspector.pack(fill=tk.BOTH, expand=True)
        self.txt_inspector.configure(state=tk.DISABLED)

        # Tab 2: Tuberías Críticas (RF10)
        tab_crit = ttk.Frame(self.notebook)
        self.notebook.add(tab_crit, text="Tuberías Críticas")

        filter_bar = tk.Frame(tab_crit, bg=theme.BG_PANEL)
        filter_bar.pack(fill=tk.X, padx=6, pady=5)
        for text, val in [
            ("Todas (59)", "all"),
            ("Críticas (>=75%)", "critical"),
            ("Sobrecargadas (>100%)", "overloaded"),
        ]:
            tk.Radiobutton(
                filter_bar,
                text=text,
                variable=self.var_crit_filter,
                value=val,
                command=self._refresh_critical_table,
                bg=theme.BG_PANEL,
                fg=theme.TEXT_SECONDARY,
                selectcolor=theme.BG_CANVAS,
                activebackground=theme.BG_PANEL,
                font=("Segoe UI", 8),
            ).pack(side=tk.LEFT, padx=4)

        cols = ("rank", "pipe", "tramo", "q_curr", "q_max", "util", "estado")
        self.tree_critical = ttk.Treeview(tab_crit, columns=cols, show="headings", selectmode="browse")
        headers = [
            ("rank", "#", 32),
            ("pipe", "Tub.", 48),
            ("tramo", "Tramo", 70),
            ("q_curr", "Q (m³/s)", 74),
            ("q_max", "Qmax", 74),
            ("util", "% Util", 64),
            ("estado", "Estado", 130),
        ]
        for cid, htext, w in headers:
            self.tree_critical.heading(cid, text=htext)
            self.tree_critical.column(cid, width=w, anchor="center" if cid in ("rank", "pipe", "tramo") else "e")

        crit_scroll = ttk.Scrollbar(tab_crit, orient=tk.VERTICAL, command=self.tree_critical.yview)
        self.tree_critical.configure(yscrollcommand=crit_scroll.set)
        self.tree_critical.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        crit_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_critical.bind("<<TreeviewSelect>>", self._on_critical_row_select)

        # Tab 3: Gráficas Temporales
        tab_charts = ttk.Frame(self.notebook)
        self.notebook.add(tab_charts, text="Evolución Temporal")
        self.temporal_charts = TemporalChartsPanel(tab_charts)
        self.temporal_charts.pack(fill=tk.BOTH, expand=True)

        # Tab 4: Comparación de Escenarios (RF11)
        tab_comp = ttk.Frame(self.notebook)
        self.notebook.add(tab_comp, text="Comparación Escenarios")

        comp_top = tk.Frame(tab_comp, bg=theme.BG_PANEL)
        comp_top.pack(fill=tk.X, padx=6, pady=6)
        tk.Button(
            comp_top,
            text="Comparar Todos los Escenarios",
            command=self._action_compare_scenarios,
            bg="#0284c7",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side=tk.LEFT)

        comp_cols = ("esc", "int", "max_u", "crit_p", "n_crit", "n_over", "ptar")
        self.tree_comp = ttk.Treeview(tab_comp, columns=comp_cols, show="headings", height=6)
        for cid, htext, w in [
            ("esc", "Escenario", 115),
            ("int", "mm/h", 48),
            ("max_u", "Máx %", 64),
            ("crit_p", "Crítica", 54),
            ("n_crit", ">=75%", 50),
            ("n_over", ">100%", 52),
            ("ptar", "Pico PTAR", 76),
        ]:
            self.tree_comp.heading(cid, text=htext)
            self.tree_comp.column(cid, width=w, anchor="center")
        self.tree_comp.pack(fill=tk.X, padx=4, pady=(0, 4))

        self.comparison_charts = ComparisonChartsPanel(tab_comp)
        self.comparison_charts.pack(fill=tk.BOTH, expand=True)

    # --- Acciones de archivo y configuración ---

    def _apply_preset(self, ingress_pct: float, dry_flow: float) -> None:
        self.var_ingress_pct.set(ingress_pct)
        self.var_dry_flow.set(dry_flow)
        self.run_simulation()

    def _toggle_labels(self) -> None:
        self.network_canvas.show_pipe_labels = self.var_show_pipe_labels.get()
        self.network_canvas.show_util_labels = self.var_show_util_labels.get()
        self.network_canvas.redraw()

    def _load_path(self, path: str, silent_error: bool = False) -> None:
        try:
            dataset = load_dataset(path)
        except DataLoadError as exc:
            if not silent_error:
                messagebox.showerror("Error de validación de datos", str(exc))
            self.status_var.set(f"Error al cargar: {exc}")
            return
        except Exception as exc:
            if not silent_error:
                messagebox.showerror("Error inesperado", str(exc))
            self.status_var.set(f"Error inesperado: {exc}")
            return

        self._player_pause()
        self.dataset = dataset
        self.engine = SewerSimulationEngine(dataset.graph, dataset.basin)
        self.result = None
        self.comparisons = []

        self.network_canvas.set_graph(dataset.graph)

        scen_labels = [s.display_name for s in dataset.scenarios]
        self.combo_scenario["values"] = scen_labels
        if len(scen_labels) >= 3:
            self.var_scenario.set(scen_labels[2])  # Escenario 3 (Moderada) por defecto
        elif scen_labels:
            self.var_scenario.set(scen_labels[0])

        nids = dataset.graph.node_ids()
        self.combo_bfs_start["values"] = nids
        self.combo_bfs_target["values"] = nids
        srcs = dataset.graph.source_ids()
        snks = dataset.graph.sink_ids()
        if srcs:
            self.var_bfs_start.set(srcs[0])
        if snks:
            self.var_bfs_target.set(snks[0])

        n_nodes, n_pipes, n_src, n_snk, total_len = dataset.graph.summary()
        self.status_var.set(
            f"Red cargada: {n_nodes} nodos, {n_pipes} tuberías ({total_len:,.1f} m) desde {os.path.basename(path)}"
        )
        self._refresh_inspector()

    def _action_load_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar archivo Excel de la red",
            filetypes=[("Archivos Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
        )
        if path:
            self._load_path(path)
            if self.dataset is not None:
                self.run_simulation()

    def _action_load_csv(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta con archivos CSV")
        if path:
            self._load_path(path)
            if self.dataset is not None:
                self.run_simulation()

    def _action_export_csv(self) -> None:
        if self.dataset is None:
            messagebox.showwarning("Sin datos", "Primero cargue un conjunto de datos.")
            return
        out_dir = filedialog.askdirectory(title="Seleccionar carpeta destino para CSV")
        if out_dir:
            export_to_csv_dir(self.dataset, out_dir)
            messagebox.showinfo("Exportación completada", f"Archivos CSV exportados en:\n{out_dir}")

    def _action_generate_report(self) -> None:
        if self.dataset is None or self.result is None:
            messagebox.showwarning("Sin simulación", "Ejecute primero una simulación.")
            return
        out_file = filedialog.asksaveasfilename(
            title="Guardar reporte de simulación",
            defaultextension=".md",
            initialfile=f"reporte_escenario_{self.result.config.scenario_id}.md",
            filetypes=[("Markdown", "*.md"), ("Texto", "*.txt")],
        )
        if not out_file:
            return
        comps = self.comparisons or compare_all_scenarios(self.dataset, self.result.config)
        self.comparisons = comps
        written = generate_markdown_report(self.dataset, self.result, comps, out_file)
        messagebox.showinfo(
            "Reporte generado",
            f"Reporte y tabla CSV generados en:\n{written}",
        )

    def _action_show_assumptions(self) -> None:
        msg = (
            "Supuestos del Modelo Computacional (Ciudad Bicentenario):\n\n"
            "1. Grafo Dirigido Propio: 46 vértices (8 fuentes, 37 pozos, 1 sumidero PTAR 31) y 59 aristas.\n"
            "2. Método Racional: Q = 0.00278 · C · I(t) · A · f_ingreso + Q_sanitario.\n"
            "   El factor de ingreso pluvial permite evaluar tanto el caso calibrado a red sanitaria "
            "(2.5% por infiltración/conexiones erradas) como el caso teórico directo (100%).\n"
            "3. Tiempo de Tránsito: t_i = L_i / V_i, con V_i = Q_max,i / A_i (velocidad a tubo lleno de Manning).\n"
            "   Los paquetes de caudal se programan en una Cola de Prioridad (Min-Heap).\n"
            "4. Distribución en Bifurcaciones: Proporcional a Q_max (o uniforme seleccionable).\n"
            "5. Sobrecarga (>100%): El caudal que supera Q_max se retiene temporalmente en el pozo aguas arriba "
            "sin pérdida de masa (conservación exacta de volumen)."
        )
        messagebox.showinfo("Supuestos del Modelo", msg)

    # --- Simulación y reproducción ---

    def _selected_scenario_obj(self):
        assert self.dataset is not None
        selected = self.var_scenario.get()
        for sc in self.dataset.scenarios:
            if sc.display_name == selected:
                return sc
        return self.dataset.scenarios[0]

    def _build_sim_config(self) -> SimulationConfig:
        sc = self._selected_scenario_obj()
        return SimulationConfig(
            scenario_id=sc.scenario_id,
            scenario_name=sc.condition,
            intensity_mm_h=sc.intensity_mm_h,
            duration_min=max(5.0, float(self.var_duration.get())),
            storm_duration_min=max(0.0, float(self.var_storm_dur.get())),
            dt_min=max(0.25, float(self.var_dt.get())),
            ingress_factor=max(0.001, min(1.0, float(self.var_ingress_pct.get()) / 100.0)),
            dry_weather_flow_per_source_m3s=max(0.0, float(self.var_dry_flow.get())),
            split_rule=self.var_split_rule.get(),
            hyetograph=self.var_hyetograph.get(),
        )

    def run_simulation(self) -> None:
        if self.dataset is None or self.engine is None:
            return
        self._player_pause()
        try:
            cfg = self._build_sim_config()
        except Exception as exc:
            messagebox.showerror("Parámetros inválidos", f"Revise los parámetros numéricos: {exc}")
            return

        self.result = self.engine.run(cfg)
        n_snaps = len(self.result.snapshots)
        self._updating_slider = True
        self.timeline_slider.configure(to=max(0, n_snaps - 1))
        self._updating_slider = False

        # Mostrar el instante pico de carga o iniciar desde t=0 según conveniencia:
        # iniciamos en el paso medio/final si se prefiere? Mejor mostrar el paso final o t=0?
        # Empecemos en t = min(storm_dur, duration) para impacto visual inmediato y permitir ▶ desde 0!
        target_idx = min(n_snaps - 1, max(1, int(cfg.storm_duration_min / cfg.dt_min)))
        self._set_step(target_idx)
        self.status_var.set(
            f"Simulación Escenario {cfg.scenario_id} ({cfg.intensity_mm_h:.0f} mm/h) lista en "
            f"{self.result.execution_time_ms:.1f} ms | {n_snaps} instantes en LinkedList."
        )

    def _set_step(self, step_idx: int) -> None:
        if self.result is None or not self.result.snapshots:
            return
        step_idx = max(0, min(len(self.result.snapshots) - 1, step_idx))
        self.current_step = step_idx
        snap = self.result.snapshots[step_idx]

        self._updating_slider = True
        self.timeline_slider.set(step_idx)
        self._updating_slider = False

        self.network_canvas.set_snapshot(snap)
        cfg = self.result.config
        self.lbl_clock.configure(
            text=(
                f"t = {snap.time_min:.1f} / {cfg.duration_min:.0f} min  |  "
                f"Escenario {cfg.scenario_id}: {cfg.scenario_name} ({snap.rain_intensity_mm_h:.1f} mm/h)  |  "
                f"PTAR 31: {snap.total_sink_discharge_m3s:.4f} m³/s"
            )
        )
        self.lbl_mass_audit.configure(
            text=f"Conservación masa OK | Error: {snap.mass_balance_error_m3:.2e} m³"
        )
        self._update_legend_counts(snap)
        self._refresh_critical_table()
        self._refresh_inspector()
        self.temporal_charts.update_plots(
            self.result, self._selected_pipe_id, snap.time_min
        )

    def _update_legend_counts(self, snap: TimeStepSnapshot) -> None:
        counts = [0, 0, 0, 0, 0]
        for ps in snap.pipe_states.values():
            counts[ps.category.tier_index] += 1
        for lbl, c in zip(self._legend_count_labels, counts):
            lbl.configure(text=str(c))

    def _on_slider_move(self, val: str) -> None:
        if self._updating_slider:
            return
        self._player_pause()
        self._set_step(int(float(val)))

    def _player_play(self) -> None:
        if self.result is None:
            return
        if self.current_step >= len(self.result.snapshots) - 1:
            self._set_step(0)
        self.is_playing = True
        self._schedule_next_frame()

    def _player_pause(self) -> None:
        self.is_playing = False
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

    def _player_reset(self) -> None:
        self._player_pause()
        self._set_step(0)

    def _player_step(self, delta: int) -> None:
        self._player_pause()
        self._set_step(self.current_step + delta)

    def _schedule_next_frame(self) -> None:
        if not self.is_playing or self.result is None:
            return
        if self.current_step >= len(self.result.snapshots) - 1:
            self.is_playing = False
            self._after_id = None
            return
        self._set_step(self.current_step + 1)
        speed_map = {"1x": 420, "2x": 210, "5x": 85, "10x": 40}
        delay = speed_map.get(self.var_speed.get(), 200)
        self._after_id = self.after(delay, self._schedule_next_frame)

    # --- Consultas, selección, recorridos y comparación ---

    def _on_pipe_selected(self, pipe_id: str) -> None:
        self._selected_pipe_id = pipe_id
        self._selected_node_id = None
        self._refresh_inspector()
        if self.result is not None:
            snap = self.result.snapshots[self.current_step]
            self.temporal_charts.update_plots(self.result, pipe_id, snap.time_min)

    def _on_node_selected(self, node_id: str) -> None:
        self._selected_node_id = node_id
        self._selected_pipe_id = None
        self.var_bfs_start.set(node_id)
        self._refresh_inspector()

    def _action_search(self) -> None:
        if self.dataset is None:
            return
        q = self.var_search.get().strip()
        if not q:
            return
        nodes, pipes = search_entities(self.dataset.graph, q)
        if not nodes and not pipes:
            messagebox.showinfo("Sin resultados", f"No se encontró nodo o tubería para '{q}'.")
            return

        # Priorizar coincidencia exacta en HashTable
        exact_pipe = self.dataset.graph.get_pipe(q.upper()) or self.dataset.graph.get_pipe(q)
        exact_node = self.dataset.graph.get_node(q.upper()) or self.dataset.graph.get_node(q)
        if exact_pipe is not None:
            self.network_canvas.select_pipe(exact_pipe.pipe_id)
            self._on_pipe_selected(exact_pipe.pipe_id)
        elif exact_node is not None:
            self.network_canvas.select_node(exact_node.node_id)
            self._on_node_selected(exact_node.node_id)
        elif pipes:
            self.network_canvas.select_pipe(pipes[0].pipe_id)
            self._on_pipe_selected(pipes[0].pipe_id)
        elif nodes:
            self.network_canvas.select_node(nodes[0].node_id)
            self._on_node_selected(nodes[0].node_id)

        self.network_canvas.set_highlights(
            pipe_ids={p.pipe_id for p in pipes},
            node_ids={n.node_id for n in nodes},
        )
        self.status_var.set(f"Búsqueda '{q}': {len(nodes)} nodo(s), {len(pipes)} tubería(s).")

    def _run_traversal(self, alg: str) -> None:
        if self.dataset is None:
            return
        start = self.var_bfs_start.get().strip()
        target = self.var_bfs_target.get().strip() or None
        try:
            res = bfs(self.dataset.graph, start, target) if alg == "BFS" else dfs(self.dataset.graph, start, target)
        except KeyError as exc:
            messagebox.showwarning("Nodo inválido", str(exc))
            return

        if res.path_pipes:
            hl_pipes = {p.pipe_id for p in res.path_pipes}
            hl_nodes = set(res.path_nodes)
        else:
            hl_pipes = {p.pipe_id for p in res.traversed_edges}
            hl_nodes = set(res.visited_order)

        self.network_canvas.set_highlights(hl_pipes, hl_nodes)

        lines = [
            f"[{res.algorithm}] {start} → {target or 'todo'}",
            f"Visitados ({len(res.visited_order)}): {' -> '.join(res.visited_order[:18])}"
            + (" ..." if len(res.visited_order) > 18 else ""),
        ]
        if target:
            if res.target_reached:
                lines.append(f"Camino ({len(res.path_pipes)} tramos): {' -> '.join(res.path_nodes)}")
                lines.append(f"Tuberías: {', '.join(p.pipe_id for p in res.path_pipes)}")
                total_t = sum(p.transit_time_min for p in res.path_pipes)
                lines.append(f"Tiempo tránsito acumulado: {total_t:.1f} min")
            else:
                lines.append(f"No hay camino dirigido desde {start} hasta {target}.")

        self._set_traversal_text("\n".join(lines))

    def _run_trace(self, direction: str) -> None:
        if self.dataset is None:
            return
        nid = self.var_bfs_start.get().strip()
        try:
            nodes, pipes = (
                trace_downstream(self.dataset.graph, nid)
                if direction == "down"
                else trace_upstream(self.dataset.graph, nid)
            )
        except KeyError as exc:
            messagebox.showwarning("Nodo inválido", str(exc))
            return
        self.network_canvas.set_highlights({p.pipe_id for p in pipes}, set(nodes))
        self._set_traversal_text(
            f"[Trazado aguas abajo desde {nid}]\n"
            f"Nodos alcanzados ({len(nodes)}): {', '.join(nodes)}\n"
            f"Tuberías ({len(pipes)}): {', '.join(p.pipe_id for p in pipes)}"
        )

    def _clear_highlights(self) -> None:
        self.network_canvas.set_highlights(set(), set())
        self._set_traversal_text("")

    def _set_traversal_text(self, text: str) -> None:
        self.txt_traversal.configure(state=tk.NORMAL)
        self.txt_traversal.delete("1.0", tk.END)
        self.txt_traversal.insert("1.0", text)
        self.txt_traversal.configure(state=tk.DISABLED)

    def _refresh_critical_table(self) -> None:
        for item in self.tree_critical.get_children():
            self.tree_critical.delete(item)
        if self.dataset is None or self.result is None:
            return

        snap = self.result.snapshots[self.current_step]
        flows = {pid: ps.flow_m3s for pid, ps in snap.pipe_states.items()}
        utils = {pid: ps.utilization_pct for pid, ps in snap.pipe_states.items()}

        flt = self.var_crit_filter.get()
        min_u = 75.0 if flt == "critical" else (100.0001 if flt == "overloaded" else 0.0)
        ranked = rank_critical_pipes(self.dataset.graph, flows, utils, min_utilization_pct=min_u)

        for rec in ranked:
            self.tree_critical.insert(
                "",
                tk.END,
                iid=rec.pipe_id,
                values=(
                    rec.rank,
                    rec.pipe_id,
                    f"{rec.from_node}→{rec.to_node}",
                    f"{rec.flow_m3s:.4f}",
                    f"{rec.q_max_m3s:.4f}",
                    f"{rec.utilization_pct:.1f}%",
                    rec.category.label,
                ),
            )

    def _on_critical_row_select(self, _event: tk.Event) -> None:
        sel = self.tree_critical.selection()
        if sel:
            pid = sel[0]
            self.network_canvas.select_pipe(pid)
            self._on_pipe_selected(pid)

    def _refresh_inspector(self) -> None:
        lines: List[str] = []
        if self.dataset is None:
            lines.append("Cargue un archivo Excel o carpeta CSV para comenzar.")
        else:
            g = self.dataset.graph
            snap = self.result.snapshots[self.current_step] if self.result else None

            if self._selected_pipe_id and g.has_pipe(self._selected_pipe_id):
                p = g.get_pipe(self._selected_pipe_id)
                assert p is not None
                lines.extend([
                    f"=== TUBERÍA {p.pipe_id} ({p.from_node} → {p.to_node}) ===",
                    f"Diámetro        : {p.diameter_in:.0f}\" ({p.diameter_m:.4f} m)",
                    f"Longitud        : {p.length_m:.2f} m",
                    f"Pendiente (S)   : {p.slope:.4f} m/m  |  Manning n: {p.manning_n:.3f}",
                    f"Capacidad Qmax  : {p.q_max_m3s:.5f} m³/s",
                    f"Velocidad ref.  : {p.reference_velocity_ms:.3f} m/s",
                    f"Tiempo tránsito : {p.transit_time_min:.2f} min ({p.transit_time_s:.1f} s)",
                ])
                if p.note:
                    lines.append(f"Marca dataset   : {p.note}")
                if snap and p.pipe_id in snap.pipe_states:
                    ps = snap.pipe_states[p.pipe_id]
                    lines.extend([
                        "",
                        f"--- Estado en t = {snap.time_min:.1f} min ---",
                        f"Caudal Q(t)     : {ps.flow_m3s:.5f} m³/s",
                        f"Caudal conducc. : {ps.conveyed_flow_m3s:.5f} m³/s",
                        f"Vol. tránsito   : {ps.volume_in_transit_m3:.2f} m³",
                        f"Utilización O(t): {ps.utilization_pct:.2f} %",
                        f"Clasificación   : {ps.category.label}",
                        f"Exceso sobrec.  : {ps.excess_flow_m3s:.5f} m³/s",
                    ])
                if self.result:
                    lines.append(
                        f"Utilización pico: {self.result.peak_pipe_utilization.get(p.pipe_id, 0.0):.2f} %"
                    )
            elif self._selected_node_id and g.has_node(self._selected_node_id):
                n = g.get_node(self._selected_node_id)
                assert n is not None
                out_p = [e.pipe_id for e in g.outgoing_pipes(n.node_id)]
                in_p = [e.pipe_id for e in g.incoming_pipes(n.node_id)]
                lines.extend([
                    f"=== NODO {n.node_id} ({n.node_type.upper()}) ===",
                    f"Tuberías entrantes : {', '.join(in_p) or 'Ninguna (Fuente)'}",
                    f"Tuberías salientes : {', '.join(out_p) or 'Ninguna (Sumidero PTAR)'}",
                ])
                if snap and n.node_id in snap.node_states:
                    ns = snap.node_states[n.node_id]
                    lines.extend([
                        "",
                        f"--- Estado en t = {snap.time_min:.1f} min ---",
                        f"Caudal entrada  : {ns.inflow_m3s:.5f} m³/s",
                        f"Caudal salida   : {ns.outflow_m3s:.5f} m³/s",
                        f"Vol. almacenado : {ns.stored_volume_m3:.3f} m³",
                    ])
            else:
                lines.append("Haga clic sobre una tubería o pozo del grafo para ver su detalle.")

            # Resumen del escenario abajo
            lines.extend(["", "=== RESUMEN DEL ESCENARIO ==="])
            if self.result and snap:
                cfg = self.result.config
                lines.extend([
                    f"Escenario       : {cfg.scenario_id} — {cfg.scenario_name} ({cfg.intensity_mm_h:.0f} mm/h)",
                    f"Cuenca          : C={self.dataset.basin.runoff_coefficient_c}, A={self.dataset.basin.area_ha} ha",
                    f"Factor ingreso  : {cfg.ingress_factor*100:.1f}%  |  Q_san={cfg.dry_weather_flow_per_source_m3s:.4f} m³/s",
                    f"Entrada acum.   : {snap.cumulative_inflow_m3:,.2f} m³",
                    f"Descarga PTAR 31: {snap.cumulative_sink_discharge_m3:,.2f} m³ (pico {self.result.peak_sink_discharge_m3s:.4f} m³/s)",
                    f"En pozos/tráns. : {snap.total_manhole_storage_m3:,.2f} / {snap.total_pipe_transit_m3:,.2f} m³",
                    f"Error balance   : {self.result.max_mass_balance_error_m3:.3e} m³",
                    f"Críticas (>=75%): {len(self.result.ever_critical_pipes)} tuberías",
                    f"Sobrec. (>100%) : {len(self.result.ever_overloaded_pipes)} tuberías",
                ])

        self.txt_inspector.configure(state=tk.NORMAL)
        self.txt_inspector.delete("1.0", tk.END)
        self.txt_inspector.insert("1.0", "\n".join(lines))
        self.txt_inspector.configure(state=tk.DISABLED)

    def _action_compare_scenarios(self) -> None:
        if self.dataset is None:
            return
        cfg = self._build_sim_config()
        self.comparisons = compare_all_scenarios(self.dataset, cfg)

        for item in self.tree_comp.get_children():
            self.tree_comp.delete(item)
        for s in self.comparisons:
            self.tree_comp.insert(
                "",
                tk.END,
                values=(
                    f"E{s.scenario_id} {s.condition}",
                    f"{s.intensity_mm_h:.0f}",
                    f"{s.max_utilization_pct:.1f}%",
                    s.most_critical_pipe,
                    s.num_critical_pipes,
                    s.num_overloaded_pipes,
                    f"{s.peak_sink_discharge_m3s:.4f}",
                ),
            )
        self.comparison_charts.update_comparison(self.comparisons)
        self.status_var.set("Comparación de los 5 escenarios completada.")
