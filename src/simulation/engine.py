"""Motor de simulación temporal discreta con Cola de Prioridad y Lista Enlazada."""

from dataclasses import dataclass
import math
import time
from typing import Dict, List, Tuple

from src.algorithms.analysis import classify_utilization
from src.algorithms.traversals import topological_sort
from src.data_structures import DirectedGraph, HashTable, LinkedList, PriorityQueue
from src.io.data_loader import DrainageBasin
from .models import (
    NodeStepState,
    PipeIntervention,
    PipeStepState,
    SimulationConfig,
    SimulationResult,
    TimeStepSnapshot,
    resolve_pipe_hydraulics,
)


@dataclass
class _TransitEvent:
    """Evento programado en la PriorityQueue para la llegada de un paquete de agua."""

    arrival_time_s: float
    pipe_id: str
    target_node: str
    volume_m3: float


class SewerSimulationEngine:
    """Simulador discreto-temporal conservativo de masa para redes de alcantarillado."""

    def __init__(self, graph: DirectedGraph, basin: DrainageBasin) -> None:
        self.graph = graph
        self.basin = basin
        self._topo_order, self._is_dag = topological_sort(graph)
        if not self._is_dag:
            raise ValueError("El grafo debe ser un DAG para ejecutar la simulación.")
        self.history: LinkedList[TimeStepSnapshot] = LinkedList()

    def _effective_intensity(self, config: SimulationConfig, time_min: float) -> float:
        """Calcula la intensidad instantánea de lluvia I(t) en mm/h según el perfil temporal."""
        if time_min < 0.0 or time_min > config.storm_duration_min or config.storm_duration_min <= 0.0:
            return 0.0
        if config.hyetograph == "triangular":
            half = config.storm_duration_min / 2.0
            if half <= 0.0:
                return config.intensity_mm_h
            # Triángulo simétrico con área equivalente a la lluvia uniforme (pico = 2 * I_media)
            if time_min <= half:
                return 2.0 * config.intensity_mm_h * (time_min / half)
            return 2.0 * config.intensity_mm_h * (
                (config.storm_duration_min - time_min) / half
            )
        return config.intensity_mm_h

    def _interval_mean_intensity(
        self, config: SimulationConfig, t0_min: float, t1_min: float
    ) -> float:
        """Calcula la intensidad promedio exacta (1/(t1-t0)) * integral_{t0}^{t1} I(tau) dtau."""
        dt = t1_min - t0_min
        storm_dur = float(config.storm_duration_min)
        if dt <= 1e-12 or storm_dur <= 0.0 or config.intensity_mm_h <= 0.0:
            return 0.0
        a = max(0.0, t0_min)
        b = min(storm_dur, t1_min)
        if b <= a + 1e-12:
            return 0.0

        if config.hyetograph != "triangular":
            return float(config.intensity_mm_h) * ((b - a) / dt)

        half = storm_dur / 2.0
        if half <= 1e-12:
            return float(config.intensity_mm_h) * ((b - a) / dt)

        def _tri_at(t: float) -> float:
            if t <= half:
                return 2.0 * float(config.intensity_mm_h) * (t / half)
            return 2.0 * float(config.intensity_mm_h) * ((storm_dur - t) / half)

        integral = 0.0
        if a < half < b:
            integral += 0.5 * (_tri_at(a) + _tri_at(half)) * (half - a)
            integral += 0.5 * (_tri_at(half) + _tri_at(b)) * (b - half)
        else:
            integral += 0.5 * (_tri_at(a) + _tri_at(b)) * (b - a)
        return integral / dt

    def compute_source_inflows_by_source(
        self, config: SimulationConfig, intensity_mm_h: float
    ) -> Tuple[float, Dict[str, float]]:
        """Calcula caudal total y distribución por fuente (por capacidad efectiva o uniforme 1/N)."""
        sources = self.graph.source_ids()
        n_sources = max(1, len(sources))
        q_rational_raw = (
            0.00278
            * self.basin.runoff_coefficient_c
            * intensity_mm_h
            * self.basin.area_ha
        )
        q_rain_effective = q_rational_raw * config.ingress_factor

        if config.source_distribution == "equal":
            weights = {sid: 1.0 / n_sources for sid in sources}
        else:
            interventions = config.interventions or {}
            raw_caps = {
                sid: sum(
                    resolve_pipe_hydraulics(e, interventions.get(e.pipe_id))[0]
                    for e in self.graph.outgoing_pipes(sid)
                )
                for sid in sources
            }
            total_cap = sum(raw_caps.values())
            if total_cap > 1e-12:
                weights = {sid: raw_caps[sid] / total_cap for sid in sources}
            else:
                weights = {sid: 1.0 / n_sources for sid in sources}

        per_source = {
            sid: (q_rain_effective * weights[sid]) + config.dry_weather_flow_per_source_m3s
            for sid in sources
        }
        q_total = sum(per_source.values())
        return q_total, per_source

    def compute_source_inflow_m3s(
        self, config: SimulationConfig, intensity_mm_h: float
    ) -> Tuple[float, float]:
        """Calcula caudal pluvial total (Método Racional) y promedio por nodo fuente."""
        q_total, per_source = self.compute_source_inflows_by_source(config, intensity_mm_h)
        q_avg = q_total / max(1, len(per_source))
        return q_total, q_avg

    def run(self, config: SimulationConfig) -> SimulationResult:
        """Ejecuta la simulación completa con sub-pasos hidráulicos continuos y conserva la masa."""
        t_start = time.perf_counter()
        self.history.clear()

        user_dt_min = max(0.1, float(config.dt_min))
        duration_min = max(0.1, float(config.duration_min))

        snap_times_min: List[float] = []
        t_acc = 0.0
        while t_acc < duration_min - 1e-9:
            t_next = min(duration_min, t_acc + user_dt_min)
            snap_times_min.append(t_next)
            t_acc = t_next
        if not snap_times_min:
            snap_times_min = [duration_min]

        # Estructuras propias para estado en tiempo real
        node_stored: HashTable[str, float] = HashTable()
        node_flooded: HashTable[str, float] = HashTable()
        pipe_transit_vol: HashTable[str, float] = HashTable()
        for nid in self.graph.node_ids():
            node_stored.put(nid, 0.0)
            node_flooded.put(nid, 0.0)
        for pid in self.graph.pipe_ids():
            pipe_transit_vol.put(pid, 0.0)

        event_queue: PriorityQueue[_TransitEvent] = PriorityQueue()
        source_set = set(self.graph.source_ids())
        sink_set = set(self.graph.sink_ids())
        cap_manhole = max(0.0, float(config.max_manhole_storage_m3))

        interventions: Dict[str, PipeIntervention] = config.interventions or {}
        eff_params = {
            p.pipe_id: resolve_pipe_hydraulics(p, interventions.get(p.pipe_id))
            for p in self.graph.pipes()
        }

        min_transit_s = min(
            (
                eff_params[p.pipe_id][2]
                for p in self.graph.pipes()
                if eff_params[p.pipe_id][2] > 0.0 and eff_params[p.pipe_id][0] > 1e-12
            ),
            default=60.0,
        )
        max_substep_s = max(0.5, min(10.0, 0.25 * min_transit_s))

        # Pesos fijos de bifurcación por nodo
        node_split_weights: Dict[str, List[Tuple[object, float]]] = {}
        for u in self._topo_order:
            outgoing = self.graph.outgoing_pipes(u).to_list()
            if not outgoing:
                node_split_weights[u] = []
                continue
            if config.split_rule == "equal":
                w_list = [1.0 / len(outgoing)] * len(outgoing)
            else:
                total_cap = sum(eff_params[p.pipe_id][0] for p in outgoing)
                w_list = [
                    (eff_params[p.pipe_id][0] / total_cap)
                    if total_cap > 0.0
                    else (1.0 / len(outgoing))
                    for p in outgoing
                ]
            node_split_weights[u] = list(zip(outgoing, w_list))

        # Registro inicial t = 0
        init_pipe_states = {
            p.pipe_id: PipeStepState(
                pipe_id=p.pipe_id,
                flow_m3s=0.0,
                conveyed_flow_m3s=0.0,
                volume_in_transit_m3=0.0,
                utilization_pct=0.0,
                category=classify_utilization(0.0),
                excess_flow_m3s=0.0,
                demand_flow_m3s=0.0,
                demand_ratio_pct=0.0,
                effective_q_max_m3s=eff_params[p.pipe_id][0],
                effective_velocity_ms=eff_params[p.pipe_id][1],
                is_closed=eff_params[p.pipe_id][0] <= 1e-12,
            )
            for p in self.graph.pipes()
        }
        init_node_states = {
            nid: NodeStepState(nid, 0.0, 0.0, 0.0, 0.0, 0.0) for nid in self.graph.node_ids()
        }
        self.history.append(
            TimeStepSnapshot(
                step_index=0,
                time_min=0.0,
                rain_intensity_mm_h=0.0,
                total_source_inflow_m3s=0.0,
                total_sink_discharge_m3s=0.0,
                cumulative_inflow_m3=0.0,
                cumulative_sink_discharge_m3=0.0,
                total_manhole_storage_m3=0.0,
                total_pipe_transit_m3=0.0,
                mass_balance_error_m3=0.0,
                total_surface_flooding_m3=0.0,
                pipe_states=init_pipe_states,
                node_states=init_node_states,
            )
        )

        cum_inflow_m3 = 0.0
        cum_sink_m3 = 0.0
        peak_util: Dict[str, float] = {p.pipe_id: 0.0 for p in self.graph.pipes()}
        peak_flow: Dict[str, float] = {p.pipe_id: 0.0 for p in self.graph.pipes()}
        peak_demand_ratio: Dict[str, float] = {p.pipe_id: 0.0 for p in self.graph.pipes()}
        peak_demand_flow: Dict[str, float] = {p.pipe_id: 0.0 for p in self.graph.pipes()}
        max_storage: Dict[str, float] = {nid: 0.0 for nid in self.graph.node_ids()}
        overloaded_minutes: Dict[str, float] = {p.pipe_id: 0.0 for p in self.graph.pipes()}
        peak_sink_q = 0.0
        max_mass_err = 0.0
        ever_critical = set()
        ever_near_capacity = set()
        ever_overloaded = set()

        all_node_ids = self.graph.node_ids()
        all_pipe_ids = self.graph.pipe_ids()
        source_ids = self.graph.source_ids()

        for step, snap_curr_min in enumerate(snap_times_min, start=1):
            snap_prev_min = 0.0 if step == 1 else snap_times_min[step - 2]
            snap_prev_s = snap_prev_min * 60.0
            snap_curr_s = snap_curr_min * 60.0
            snap_dt_s = max(1e-9, snap_curr_s - snap_prev_s)
            snap_dt_min = snap_dt_s / 60.0

            n_sub = max(1, int(math.ceil(snap_dt_s / max_substep_s)))
            sub_dt_s = snap_dt_s / n_sub

            stored_start: Dict[str, float] = {nid: node_stored[nid] for nid in all_node_ids}
            snap_node_arrivals: Dict[str, float] = {nid: 0.0 for nid in all_node_ids}
            snap_node_sent: Dict[str, float] = {nid: 0.0 for nid in all_node_ids}
            snap_node_spill: Dict[str, float] = {nid: 0.0 for nid in all_node_ids}
            snap_pipe_sent: Dict[str, float] = {pid: 0.0 for pid in all_pipe_ids}
            snap_inflow_vol = 0.0
            snap_sink_vol = 0.0

            for sub in range(n_sub):
                t_sub_prev_s = snap_prev_s + sub * sub_dt_s
                t_sub_curr_s = snap_prev_s + (sub + 1) * sub_dt_s
                t_sub_prev_min = t_sub_prev_s / 60.0
                t_sub_curr_min = t_sub_curr_s / 60.0

                sub_intensity = self._interval_mean_intensity(
                    config, t_sub_prev_min, t_sub_curr_min
                )
                _, sub_q_by_source = self.compute_source_inflows_by_source(config, sub_intensity)

                sub_arrivals: Dict[str, float] = {nid: 0.0 for nid in all_node_ids}

                # 1. Procesar eventos de llegada de la PriorityQueue hasta t_sub_curr_s
                while not event_queue.is_empty():
                    arr_t, _ = event_queue.peek()
                    if arr_t > t_sub_curr_s + 1e-9:
                        break
                    _, ev = event_queue.pop()
                    sub_arrivals[ev.target_node] += ev.volume_m3
                    snap_node_arrivals[ev.target_node] += ev.volume_m3
                    new_transit = max(0.0, pipe_transit_vol[ev.pipe_id] - ev.volume_m3)
                    pipe_transit_vol.put(ev.pipe_id, new_transit)

                # 2. Inyectar caudal en nodos fuente
                for sid in source_ids:
                    q_src = sub_q_by_source.get(sid, 0.0)
                    vol_in = q_src * sub_dt_s
                    sub_arrivals[sid] += vol_in
                    snap_node_arrivals[sid] += vol_in
                    cum_inflow_m3 += vol_in
                    snap_inflow_vol += vol_in

                # 3. Propagar por orden topológico con retardo físico real en tuberías
                for u in self._topo_order:
                    avail_vol = node_stored[u] + sub_arrivals[u]

                    if u in sink_set:
                        snap_sink_vol += avail_vol
                        cum_sink_m3 += avail_vol
                        node_stored.put(u, 0.0)
                        snap_node_sent[u] += avail_vol
                        continue

                    pairs = node_split_weights[u]
                    if not pairs:
                        # Nodo no-sumidero sin salidas: retiene en pozo y rebosa localmente (no acredita a PTAR)
                        stored_u = min(avail_vol, cap_manhole)
                        spill_u = max(0.0, avail_vol - stored_u)
                        node_stored.put(u, stored_u)
                        if spill_u > 0.0:
                            node_flooded.put(u, node_flooded[u] + spill_u)
                            snap_node_spill[u] += spill_u
                        if stored_u > max_storage[u]:
                            max_storage[u] = stored_u
                        continue

                    remaining_stored = 0.0
                    total_sent_u = 0.0

                    for edge, w in pairs:
                        eff_q_max, _eff_vel_ms, eff_transit_s, _eff_diam = eff_params[edge.pipe_id]
                        demand_vol = avail_vol * w
                        cap_vol = eff_q_max * sub_dt_s
                        sent_vol = min(demand_vol, cap_vol)
                        excess_vol = max(0.0, demand_vol - sent_vol)
                        remaining_stored += excess_vol
                        total_sent_u += sent_vol
                        snap_pipe_sent[edge.pipe_id] += sent_vol

                        if sent_vol > 0.0:
                            arrival_s = t_sub_curr_s + eff_transit_s
                            if arrival_s <= t_sub_curr_s + 1e-9:
                                sub_arrivals[edge.to_node] += sent_vol
                                snap_node_arrivals[edge.to_node] += sent_vol
                            else:
                                pipe_transit_vol.put(
                                    edge.pipe_id, pipe_transit_vol[edge.pipe_id] + sent_vol
                                )
                                event_queue.push(
                                    arrival_s,
                                    _TransitEvent(
                                        arrival_time_s=arrival_s,
                                        pipe_id=edge.pipe_id,
                                        target_node=edge.to_node,
                                        volume_m3=sent_vol,
                                    ),
                                )

                    stored_u = min(remaining_stored, cap_manhole)
                    spill_u = max(0.0, remaining_stored - stored_u)
                    node_stored.put(u, stored_u)
                    if spill_u > 0.0:
                        node_flooded.put(u, node_flooded[u] + spill_u)
                        snap_node_spill[u] += spill_u
                    snap_node_sent[u] += total_sent_u
                    if stored_u > max_storage[u]:
                        max_storage[u] = stored_u

            # Consolidar instantánea del intervalo de reporte [snap_prev_s, snap_curr_s]
            pipe_states: Dict[str, PipeStepState] = {}
            critical_ids: List[str] = []
            near_capacity_ids: List[str] = []
            overloaded_ids: List[str] = []

            for u in self._topo_order:
                pairs = node_split_weights[u]
                if not pairs:
                    continue
                node_demand_base_vol = stored_start[u] + snap_node_arrivals[u]
                for edge, w in pairs:
                    eff_q_max, eff_vel_ms, eff_transit_s, _eff_diam = eff_params[edge.pipe_id]
                    vol_in_pipe = pipe_transit_vol[edge.pipe_id]
                    q_conveyed = snap_pipe_sent[edge.pipe_id] / snap_dt_s
                    q_total_demand_step = (node_demand_base_vol * w) / snap_dt_s
                    q_in_transit = (
                        vol_in_pipe / eff_transit_s
                        if eff_transit_s > snap_dt_s
                        else q_conveyed
                    )

                    if eff_q_max <= 1e-12:
                        q_demand = q_total_demand_step
                        q_conveyed = 0.0
                        util_pct = 0.0
                        demand_ratio = 0.0
                        excess_q = q_demand
                        is_closed = True
                    else:
                        q_demand = max(q_total_demand_step, q_conveyed, q_in_transit)
                        util_pct = (q_demand / eff_q_max) * 100.0
                        demand_ratio = util_pct
                        excess_q = max(0.0, q_demand - eff_q_max)
                        is_closed = False

                    cat = classify_utilization(util_pct)

                    pipe_states[edge.pipe_id] = PipeStepState(
                        pipe_id=edge.pipe_id,
                        flow_m3s=q_conveyed,
                        conveyed_flow_m3s=q_conveyed,
                        volume_in_transit_m3=vol_in_pipe,
                        utilization_pct=util_pct,
                        category=cat,
                        excess_flow_m3s=excess_q,
                        demand_flow_m3s=q_demand,
                        demand_ratio_pct=demand_ratio,
                        effective_q_max_m3s=eff_q_max,
                        effective_velocity_ms=eff_vel_ms,
                        is_closed=is_closed,
                    )

                    if util_pct > peak_util[edge.pipe_id]:
                        peak_util[edge.pipe_id] = util_pct
                    if q_conveyed > peak_flow[edge.pipe_id]:
                        peak_flow[edge.pipe_id] = q_conveyed
                    if demand_ratio > peak_demand_ratio[edge.pipe_id]:
                        peak_demand_ratio[edge.pipe_id] = demand_ratio
                    if q_demand > peak_demand_flow[edge.pipe_id]:
                        peak_demand_flow[edge.pipe_id] = q_demand
                    if cat.is_critical:
                        critical_ids.append(edge.pipe_id)
                        ever_critical.add(edge.pipe_id)
                        if not cat.is_overloaded:
                            near_capacity_ids.append(edge.pipe_id)
                            ever_near_capacity.add(edge.pipe_id)
                    if cat.is_overloaded:
                        overloaded_ids.append(edge.pipe_id)
                        ever_overloaded.add(edge.pipe_id)
                        overloaded_minutes[edge.pipe_id] = min(
                            duration_min,
                            overloaded_minutes[edge.pipe_id] + snap_dt_min,
                        )

            total_manhole_storage = sum(node_stored[nid] for nid in all_node_ids)
            total_pipe_transit = sum(pipe_transit_vol[pid] for pid in all_pipe_ids)
            total_surface_flooding = sum(node_flooded[nid] for nid in all_node_ids)
            mass_err = abs(
                cum_inflow_m3
                - (cum_sink_m3 + total_manhole_storage + total_pipe_transit + total_surface_flooding)
            )
            max_mass_err = max(max_mass_err, mass_err)

            snap_intensity = self._interval_mean_intensity(config, snap_prev_min, snap_curr_min)
            total_src_q = snap_inflow_vol / snap_dt_s
            sink_q = snap_sink_vol / snap_dt_s
            peak_sink_q = max(peak_sink_q, sink_q)

            node_states = {
                nid: NodeStepState(
                    node_id=nid,
                    inflow_m3s=snap_node_arrivals[nid] / snap_dt_s,
                    outflow_m3s=snap_node_sent[nid] / snap_dt_s,
                    stored_volume_m3=node_stored[nid],
                    surface_flooding_m3=node_flooded[nid],
                    flooding_rate_m3s=snap_node_spill[nid] / snap_dt_s,
                )
                for nid in all_node_ids
            }

            self.history.append(
                TimeStepSnapshot(
                    step_index=step,
                    time_min=snap_curr_min,
                    rain_intensity_mm_h=snap_intensity,
                    total_source_inflow_m3s=total_src_q,
                    total_sink_discharge_m3s=sink_q,
                    cumulative_inflow_m3=cum_inflow_m3,
                    cumulative_sink_discharge_m3=cum_sink_m3,
                    total_manhole_storage_m3=total_manhole_storage,
                    total_pipe_transit_m3=total_pipe_transit,
                    mass_balance_error_m3=mass_err,
                    total_surface_flooding_m3=total_surface_flooding,
                    pipe_states=pipe_states,
                    node_states=node_states,
                    critical_pipe_ids=critical_ids,
                    near_capacity_pipe_ids=near_capacity_ids,
                    overloaded_pipe_ids=overloaded_ids,
                )
            )

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        snapshots_list = self.history.to_list()
        last_snap = snapshots_list[-1]
        residual = last_snap.total_manhole_storage_m3 + last_snap.total_pipe_transit_m3
        max_flood_by_node = {nid: node_flooded[nid] for nid in all_node_ids}

        return SimulationResult(
            config=config,
            snapshots=snapshots_list,
            peak_pipe_utilization=peak_util,
            peak_pipe_flow=peak_flow,
            max_manhole_storage_m3=max_storage,
            peak_sink_discharge_m3s=peak_sink_q,
            total_inflow_m3=cum_inflow_m3,
            total_sink_discharge_m3=cum_sink_m3,
            final_residual_m3=residual,
            max_mass_balance_error_m3=max_mass_err,
            ever_critical_pipes=sorted(ever_critical),
            ever_near_capacity_pipes=sorted(ever_near_capacity),
            ever_overloaded_pipes=sorted(ever_overloaded),
            execution_time_ms=elapsed_ms,
            pipe_overloaded_minutes=overloaded_minutes,
            peak_pipe_demand_ratio=peak_demand_ratio,
            peak_pipe_demand_flow=peak_demand_flow,
            total_surface_flooding_m3=last_snap.total_surface_flooding_m3,
            max_node_flooding_m3=max_flood_by_node,
        )
