"""Panel central: franja de telemetría (KPIs), barra de modo cartográfico, NetworkCanvas y reproductor."""

from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.algorithms import classify_overload_persistence, classify_utilization
from src.simulation import SimulationResult, TimeStepSnapshot
from .. import theme
from ..canvas import NetworkCanvas
from ..widgets import KpiCard, SegmentedControl, StyledButton, blocked_signals, make_separator
from .tour_overlay import GuidedTourCard


class CenterPanel(QFrame):
    """Área central con telemetría, modos de mapa, lienzo cartográfico y reproductor temporal."""

    labelsToggled = Signal(bool, bool)
    mapModeChanged = Signal(str)
    guidedTourRequested = Signal()
    resetRequested = Signal()
    stepRequested = Signal(int)
    playPauseRequested = Signal()
    speedChanged = Signal(str)
    sliderMoved = Signal(int)

    def __init__(
        self,
        icons: Dict[str, QIcon],
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        display_font: str = "Inter",
        dpi_scale: float = 1.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CenterPanel")
        self._icons = icons
        self._ui_font = ui_font
        self._mono_font = mono_font
        self._player_compact: Optional[bool] = None
        self._map_mode_tier: Optional[str] = None
        self._is_playing: bool = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # 1. Franja superior de telemetría (Reloj + Toggles + 4 KPIs)
        telemetry = QFrame(self)
        telemetry.setObjectName("TelemetryHeader")
        tel_lay = QVBoxLayout(telemetry)
        tel_lay.setContentsMargins(0, 0, 0, 0)
        tel_lay.setSpacing(0)

        top_row = QWidget(telemetry)
        top_row.setObjectName("TelemetryTopRow")
        tr_lay = QHBoxLayout(top_row)
        tr_lay.setContentsMargins(8, 6, 8, 6)
        tr_lay.setSpacing(8)

        clock_pill = QFrame(top_row)
        clock_pill.setObjectName("ClockPill")
        cp_lay = QHBoxLayout(clock_pill)
        cp_lay.setContentsMargins(9, 3, 9, 3)
        self.lbl_clock = QLabel("t = 0.0 min  ·  Escenario: -", clock_pill)
        self.lbl_clock.setObjectName("ClockLabel")
        cp_lay.addWidget(self.lbl_clock)
        tr_lay.addWidget(clock_pill)

        tr_lay.addStretch(1)

        self.chk_ids = QCheckBox("IDs", top_row)
        self.chk_ids.setChecked(True)
        self.chk_ids.setFont(QFont(ui_font, 8, QFont.Weight.Bold))
        self.chk_ids.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_ids.toggled.connect(self._emit_labels_toggled)

        self.chk_util = QCheckBox("% Util.", top_row)
        self.chk_util.setChecked(True)
        self.chk_util.setFont(QFont(ui_font, 8, QFont.Weight.Bold))
        self.chk_util.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_util.toggled.connect(self._emit_labels_toggled)

        tr_lay.addWidget(self.chk_ids)
        tr_lay.addWidget(self.chk_util)
        tel_lay.addWidget(top_row)

        tel_lay.addWidget(make_separator("h", theme.DOCK_BORDER, 1, telemetry))

        kpi_row = QWidget(telemetry)
        kpi_row.setObjectName("KpiRow")
        kr_lay = QHBoxLayout(kpi_row)
        kr_lay.setContentsMargins(0, 0, 0, 0)
        kr_lay.setSpacing(1)

        self.kpi_cards: Dict[str, KpiCard] = {
            "sys_fmax": KpiCard("USO SIS. (F_MAX)", "-", kpi_row),
            "max_util": KpiCard("UTILIZACIÓN MÁX.", "-", kpi_row),
            "critical": KpiCard("CRÍTICAS (>75–100%)", "-", kpi_row),
            "overloaded": KpiCard("SOBRECARGA (>100%)", "-", kpi_row),
            "ptar": KpiCard("DESCARGA PTAR 31", "-", kpi_row),
        }
        for card in self.kpi_cards.values():
            kr_lay.addWidget(card, 1)
        tel_lay.addWidget(kpi_row)
        lay.addWidget(telemetry)

        # 2. Barra de modo cartográfico + NetworkCanvas (sin espacio entre barra y lienzo)
        canvas_block = QVBoxLayout()
        canvas_block.setContentsMargins(0, 0, 0, 0)
        canvas_block.setSpacing(0)

        self.map_mode_bar = QFrame(self)
        self.map_mode_bar.setObjectName("MapModeBar")
        mm_lay = QHBoxLayout(self.map_mode_bar)
        mm_lay.setContentsMargins(8, 3, 8, 3)
        mm_lay.setSpacing(6)

        self.lbl_map_mode = QLabel("Lectura cartográfica:", self.map_mode_bar)
        self.lbl_map_mode.setObjectName("MapModeCaption")
        mm_lay.addWidget(self.lbl_map_mode)

        self.seg_map_mode = SegmentedControl(
            [
                ("instant", "Instantáneo O(t)"),
                ("peak", "Pico Máximo"),
                ("overload_minutes", "Minutos en Sobrecarga"),
            ],
            initial_key="instant",
            inactive_variant="dock_secondary",
            font_pt=8,
            pad_x=9,
            pad_y=3,
            spacing=1,
            framed=True,
            parent=self.map_mode_bar,
        )
        self.seg_map_mode.selectionChanged.connect(self.mapModeChanged.emit)
        mm_lay.addWidget(self.seg_map_mode)
        mm_lay.addStretch(1)

        self.btn_tour_quick = StyledButton(
            " Tour Guiado",
            variant="light_secondary",
            icon=icons["tour_ink"],
            icon_size=12,
            font_pt=8,
            pad_x=8,
            pad_y=3,
            parent=self.map_mode_bar,
        )
        self.btn_tour_quick.setToolTip(
            "Abrir recorrido guiado interactivo (4 hallazgos clave del escenario)"
        )
        self.btn_tour_quick.clicked.connect(self.guidedTourRequested.emit)
        mm_lay.addWidget(self.btn_tour_quick)
        canvas_block.addWidget(self.map_mode_bar)

        self.network_canvas = NetworkCanvas(
            ui_font=ui_font,
            mono_font=mono_font,
            dpi_scale=dpi_scale,
            parent=self,
        )
        self.tour_card = GuidedTourCard(
            ui_font=ui_font,
            mono_font=mono_font,
            display_font=display_font,
            parent=self.network_canvas,
        )
        self.network_canvas.attach_tour_card(self.tour_card)
        canvas_block.addWidget(self.network_canvas, 1)
        lay.addLayout(canvas_block, 1)

        # 3. Reproductor temporal inferior
        self.player_frame = QFrame(self)
        self.player_frame.setObjectName("PlayerBar")
        pf_lay = QVBoxLayout(self.player_frame)
        pf_lay.setContentsMargins(10, 7, 10, 7)
        pf_lay.setSpacing(5)

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(3)

        self.btn_reset = StyledButton(
            " Inicio",
            variant="dock_secondary",
            icon=icons["reset_light"],
            icon_size=11,
            font_pt=8,
            pad_x=6,
            pad_y=3,
            parent=self.player_frame,
        )
        self.btn_reset.clicked.connect(self.resetRequested.emit)
        controls_row.addWidget(self.btn_reset)

        self.btn_step_back = StyledButton(
            " -1",
            variant="dock_secondary",
            icon=icons["step_back_light"],
            icon_size=11,
            font_pt=8,
            pad_x=6,
            pad_y=3,
            parent=self.player_frame,
        )
        self.btn_step_back.clicked.connect(lambda: self.stepRequested.emit(-1))
        controls_row.addWidget(self.btn_step_back)

        self.btn_play_pause = StyledButton(
            " Reproducir",
            variant="primary",
            icon=icons["play_on_accent"],
            icon_size=11,
            font_pt=8,
            pad_x=8,
            pad_y=3,
            parent=self.player_frame,
        )
        self.btn_play_pause.setMinimumWidth(96)
        self.btn_play_pause.clicked.connect(self.playPauseRequested.emit)
        controls_row.addWidget(self.btn_play_pause)

        self.btn_step_fwd = StyledButton(
            " +1",
            variant="dock_secondary",
            icon=icons["step_fwd_light"],
            icon_size=11,
            font_pt=8,
            pad_x=6,
            pad_y=3,
            parent=self.player_frame,
        )
        self.btn_step_fwd.clicked.connect(lambda: self.stepRequested.emit(1))
        controls_row.addWidget(self.btn_step_fwd)

        self.lbl_speed_cap = QLabel("Vel.", self.player_frame)
        self.lbl_speed_cap.setFont(QFont(ui_font, 8))
        controls_row.addSpacing(4)
        controls_row.addWidget(self.lbl_speed_cap)

        self.combo_speed = QComboBox(self.player_frame)
        self.combo_speed.addItems(["1x", "2x", "5x", "10x"])
        self.combo_speed.setCurrentText("2x")
        self.combo_speed.setMinimumWidth(52)
        self.combo_speed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_speed.currentTextChanged.connect(self.speedChanged.emit)
        controls_row.addWidget(self.combo_speed)

        controls_row.addStretch(1)

        self.lbl_mass_audit = QLabel("Balance masa: -", self.player_frame)
        self.lbl_mass_audit.setObjectName("MassAuditLabel")
        controls_row.addWidget(self.lbl_mass_audit)
        pf_lay.addLayout(controls_row)

        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(0, 0, 0, 0)
        slider_row.setSpacing(6)

        self.lbl_t_start = QLabel("0m", self.player_frame)
        self.lbl_t_start.setFont(QFont(mono_font, 7, QFont.Weight.Bold))
        slider_row.addWidget(self.lbl_t_start)

        self.timeline_slider = QSlider(Qt.Orientation.Horizontal, self.player_frame)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.setValue(0)
        self.timeline_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timeline_slider.valueChanged.connect(self.sliderMoved.emit)
        slider_row.addWidget(self.timeline_slider, 1)

        self.lbl_t_end = QLabel("90m", self.player_frame)
        self.lbl_t_end.setFont(QFont(mono_font, 7, QFont.Weight.Bold))
        slider_row.addWidget(self.lbl_t_end)
        pf_lay.addLayout(slider_row)

        lay.addWidget(self.player_frame)

    def _emit_labels_toggled(self) -> None:
        self.labelsToggled.emit(self.chk_ids.isChecked(), self.chk_util.isChecked())

    def set_map_mode_active(self, mode: str) -> None:
        self.seg_map_mode.set_current(mode)

    def set_slider_range(self, max_step: int, end_min: float) -> None:
        with blocked_signals(self.timeline_slider):
            self.timeline_slider.setRange(0, max(0, max_step))
        self.lbl_t_end.setText(f"{end_min:.0f}m")

    def set_slider_value(self, step: int) -> None:
        with blocked_signals(self.timeline_slider):
            self.timeline_slider.setValue(step)

    def set_playing_state(self, playing: bool) -> None:
        self._is_playing = playing
        self._update_play_button_label()

    def set_speed_label(self, speed_label: str) -> None:
        with blocked_signals(self.combo_speed):
            self.combo_speed.setCurrentText(speed_label)

    def _update_play_button_label(self) -> None:
        icon = self._icons["pause_on_accent"] if self._is_playing else self._icons["play_on_accent"]
        self.btn_play_pause.setIcon(icon)
        if self._player_compact:
            self.btn_play_pause.setText("")
            self.btn_play_pause.setMinimumWidth(34)
            self.btn_play_pause.setMaximumWidth(40)
        else:
            self.btn_play_pause.setText(" Pausar" if self._is_playing else " Reproducir")
            self.btn_play_pause.setMinimumWidth(104)
            self.btn_play_pause.setMaximumWidth(16777215)

    def update_telemetry(
        self,
        *,
        map_mode: str,
        result: Optional[SimulationResult],
        snap: Optional[TimeStepSnapshot],
        peak_all: Dict[str, float],
        ov_all: Dict[str, float],
        dur_total: float,
    ) -> None:
        self._update_clock_label(map_mode, result, snap, dur_total)
        self._update_kpi_cards(map_mode, result, snap, peak_all, ov_all, dur_total)
        self._update_mass_audit_label(snap)

    def _update_kpi_cards(
        self,
        map_mode: str,
        result: Optional[SimulationResult],
        snap: Optional[TimeStepSnapshot],
        peak_all: Dict[str, float],
        ov_all: Dict[str, float],
        dur_total: float,
    ) -> None:
        if result is None or snap is None:
            return
        if map_mode == "peak":
            captions = {
                "sys_fmax": "PICO SIS. (F_MAX)",
                "max_util": "PICO MÁX. UTIL.",
                "critical": "CRÍTICAS PICO (>75–100%)",
                "overloaded": "SOBRECARGA PICO (>100%)",
                "ptar": "PICO DESCARGA PTAR 31",
            }
            for k, txt in captions.items():
                self.kpi_cards[k].set_caption(txt)
            sys_tier = classify_utilization(result.peak_system_utilization_pct).tier_index
            self.kpi_cards["sys_fmax"].set_value(
                f"{result.peak_system_utilization_pct:.1f}%",
                theme.TIER_TEXT_ON_LIGHT[sys_tier],
            )
            max_u = max((peak_all.get(pid, 0.0) for pid in snap.pipe_states), default=0.0)
            tier_idx = classify_utilization(max_u).tier_index
            crit_cnt = sum(
                1 for pid in snap.pipe_states if classify_utilization(peak_all.get(pid, 0.0)).tier_index == 3
            )
            over_cnt = sum(
                1 for pid in snap.pipe_states if classify_utilization(peak_all.get(pid, 0.0)).tier_index == 4
            )
            self.kpi_cards["max_util"].set_value(
                f"{max_u:.1f}%", theme.TIER_TEXT_ON_LIGHT[tier_idx]
            )
            self.kpi_cards["critical"].set_value(
                str(crit_cnt), theme.STATUS_ERR_LIGHT if crit_cnt else theme.INK_PRIMARY
            )
            self.kpi_cards["overloaded"].set_value(
                str(over_cnt), theme.TIER_TEXT_ON_LIGHT[4] if over_cnt else theme.INK_PRIMARY
            )
            self.kpi_cards["ptar"].set_value(
                f"{result.peak_sink_discharge_m3s:.4f} m³/s", theme.ACCENT_TEXT_ON_LIGHT
            )
        elif map_mode == "overload_minutes":
            captions = {
                "sys_fmax": "FLUJO MÁX. (FF)",
                "max_util": "MÁX. SOBREC. ACUM.",
                "critical": "TUBERÍAS >0 min >100%",
                "overloaded": "COLAPSO CRÓNICO (>75%)",
                "ptar": "VOLUMEN PTAR 31",
            }
            for k, txt in captions.items():
                self.kpi_cards[k].set_caption(txt)
            self.kpi_cards["sys_fmax"].set_value(
                f"{result.system_max_flow_m3s:.4f} m³/s", theme.ACCENT_TEXT_ON_LIGHT
            )
            max_ov = max((ov_all.get(pid, 0.0) for pid in snap.pipe_states), default=0.0)
            tier_ov, _, _ = classify_overload_persistence(max_ov, dur_total)
            any_ov_cnt = sum(1 for pid in snap.pipe_states if ov_all.get(pid, 0.0) >= 0.5)
            chronic_cnt = sum(
                1
                for pid in snap.pipe_states
                if classify_overload_persistence(ov_all.get(pid, 0.0), dur_total)[0] == 4
            )
            self.kpi_cards["max_util"].set_value(
                f"{max_ov:.0f} / {dur_total:.0f}m", theme.TIER_TEXT_ON_LIGHT[tier_ov]
            )
            self.kpi_cards["critical"].set_value(
                str(any_ov_cnt), theme.STATUS_ERR_LIGHT if any_ov_cnt else theme.INK_PRIMARY
            )
            self.kpi_cards["overloaded"].set_value(
                str(chronic_cnt), theme.TIER_TEXT_ON_LIGHT[4] if chronic_cnt else theme.INK_PRIMARY
            )
            self.kpi_cards["ptar"].set_value(
                f"{result.total_sink_discharge_m3:.1f} m³", theme.ACCENT_TEXT_ON_LIGHT
            )
        else:
            captions = {
                "sys_fmax": "USO SIS. (F_MAX)",
                "max_util": "UTILIZACIÓN MÁX.",
                "critical": "CRÍTICAS (>75–100%)",
                "overloaded": "SOBRECARGA (>100%)",
                "ptar": "DESCARGA PTAR 31",
            }
            for k, txt in captions.items():
                self.kpi_cards[k].set_caption(txt)
            sys_tier = classify_utilization(snap.system_utilization_pct).tier_index
            self.kpi_cards["sys_fmax"].set_value(
                f"{snap.system_utilization_pct:.1f}%",
                theme.TIER_TEXT_ON_LIGHT[sys_tier],
            )
            max_u = max((ps.utilization_pct for ps in snap.pipe_states.values()), default=0.0)
            tier_idx = 0 if max_u <= 25 else (1 if max_u <= 50 else (2 if max_u <= 75 else (3 if max_u <= 100 else 4)))
            self.kpi_cards["max_util"].set_value(
                f"{max_u:.1f}%", theme.TIER_TEXT_ON_LIGHT[tier_idx]
            )
            self.kpi_cards["critical"].set_value(
                str(len(snap.near_capacity_pipe_ids)),
                theme.STATUS_ERR_LIGHT if snap.near_capacity_pipe_ids else theme.INK_PRIMARY,
            )
            self.kpi_cards["overloaded"].set_value(
                str(len(snap.overloaded_pipe_ids)),
                theme.TIER_TEXT_ON_LIGHT[4] if snap.overloaded_pipe_ids else theme.INK_PRIMARY,
            )
            self.kpi_cards["ptar"].set_value(
                f"{snap.total_sink_discharge_m3s:.4f} m³/s", theme.ACCENT_TEXT_ON_LIGHT
            )

    def _update_clock_label(
        self,
        map_mode: str,
        result: Optional[SimulationResult],
        snap: Optional[TimeStepSnapshot],
        dur_total: float,
    ) -> None:
        if result is None or snap is None:
            return
        cfg = result.config
        if cfg.target_fmax_pct is not None:
            scen_es = f"Sim. {cfg.target_fmax_pct:.0f}% F_max"
        else:
            scen_es = theme.translate_scenario_name(
                cfg.scenario_name, compact=bool(self._player_compact)
            )
        if map_mode == "peak":
            txt = (
                f"Pico 0–{dur_total:.0f}m · {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
                if self._player_compact
                else f"Pico máximo · 0–{dur_total:.0f} min  ·  {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
            )
        elif map_mode == "overload_minutes":
            txt = (
                f"Sobrecarga 0–{dur_total:.0f}m · {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
                if self._player_compact
                else f"Sobrecarga acumulada · 0–{dur_total:.0f} min  ·  {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
            )
        elif self._player_compact:
            txt = f"t={snap.time_min:.0f}/{cfg.duration_min:.0f}m · {scen_es} ({snap.rain_intensity_mm_h:.0f} mm/h)"
        else:
            txt = (
                f"t = {snap.time_min:.1f} / {cfg.duration_min:.0f} min  ·  "
                f"{scen_es} ({snap.rain_intensity_mm_h:.0f} mm/h)"
            )
        self.lbl_clock.setText(txt)

    def _update_mass_audit_label(self, snap: Optional[TimeStepSnapshot]) -> None:
        if snap is None:
            self.lbl_mass_audit.setText("Balance masa: -")
            return
        if self._player_compact or self.width() < 640:
            self.lbl_mass_audit.setText(f"Masa OK · {snap.mass_balance_error_m3:.1e}")
        else:
            self.lbl_mass_audit.setText(
                f"Masa OK · {snap.mass_balance_error_m3:.2e} m³"
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self.width()

        compact = w < 600
        if compact != self._player_compact:
            self._player_compact = compact
            if compact:
                self.btn_reset.setText("")
                self.btn_step_back.setText("")
                self.btn_step_fwd.setText("")
                self.lbl_speed_cap.setVisible(False)
            else:
                self.btn_reset.setText(" Inicio")
                self.btn_step_back.setText(" -1")
                self.btn_step_fwd.setText(" +1")
                self.lbl_speed_cap.setVisible(True)
            self._update_play_button_label()

        mm_tier = "full" if w >= 660 else ("mid" if w >= 480 else "short")
        if mm_tier != self._map_mode_tier:
            self._map_mode_tier = mm_tier
            if mm_tier == "full":
                self.lbl_map_mode.setVisible(True)
                self.seg_map_mode.set_labels(
                    {
                        "instant": "Instantáneo O(t)",
                        "peak": "Pico Máximo",
                        "overload_minutes": "Minutos en Sobrecarga",
                    },
                    pad_x=9,
                )
            elif mm_tier == "mid":
                self.lbl_map_mode.setVisible(False)
                self.seg_map_mode.set_labels(
                    {
                        "instant": "Instantáneo O(t)",
                        "peak": "Pico Máximo",
                        "overload_minutes": "Min. Sobrecarga",
                    },
                    pad_x=8,
                )
            else:
                self.lbl_map_mode.setVisible(False)
                self.seg_map_mode.set_labels(
                    {
                        "instant": "O(t)",
                        "peak": "Pico",
                        "overload_minutes": "Min >100%",
                    },
                    pad_x=6,
                )
            self.btn_tour_quick.setVisible(mm_tier in ("full", "mid"))

        self.network_canvas.reposition_tour_card()

    def set_tour_active(self, active: bool) -> None:
        if active:
            self.btn_tour_quick.set_variant("primary")
            self.btn_tour_quick.setIcon(self._icons["tour_light"])
        else:
            self.btn_tour_quick.set_variant("light_secondary")
            self.btn_tour_quick.setIcon(self._icons["tour_ink"])
