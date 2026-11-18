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
        """Calcula la intensidad de lluvia I(t) en mm/h según el perfil temporal."""
        if time_min > config.storm_duration_min or config.storm_duration_min <= 0:
            return 0.0
        if config.hyetograph == "triangular":
            half = config.storm_duration_min / 2.0
            if half <= 0:
                return config.intensity_mm_h
            # Triángulo simétrico con área equivalente a la lluvia uniforme (pico = 2 * I_media)
            if time_min <= half:
                return 2.0 * config.intensity_mm_h * (time_min / half)
            return 2.0 * config.intensity_mm_h * (
                (config.storm_duration_min - time_min) / half
            )
        return config.intensity_mm_h

    def compute_source_inflows_by_source(
        self, config: SimulationConfig, intensity_mm_h: float
    ) -> Tuple[float, Dict[str, float]]:
        """Calcula caudal total y distribución por fuente (por capacidad instalada o uniforme 1/N)."""
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
            raw_caps = {
                sid: sum(e.q_max_m3s for e in self.graph.outgoing_pipes(sid))
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
        """Ejecuta la simulación completa y almacena cada instante en `self.history`."""
        t_start = time.perf_counter()
        self.history.clear()

        dt_min = max(0.1, config.dt_min)
        dt_s = dt_min * 60.0
        n_steps = max(1, int(math.ceil(config.duration_min / dt_min)))

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
        max_phys_util = max(100.1, float(config.max_physical_utilization_pct))

        interventions: Dict[str, PipeIntervention] = config.interventions or {}
        eff_params = {
            p.pipe_id: resolve_pipe_hydraulics(p, interventions.get(p.pipe_id))
            for p in self.graph.pipes()
        }

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
        peak_sink_q = 0.0
        max_mass_err = 0.0
        ever_critical = set()
        ever_overloaded = set()

        for step in range(1, n_steps + 1):
            t_prev_s = (step - 1) * dt_s
            t_curr_s = step * dt_s
            t_curr_min = step * dt_min

            intensity = self._effective_intensity(config, t_curr_min)
            total_src_q, q_by_source = self.compute_source_inflows_by_source(config, intensity)

            node_arrivals: Dict[str, float] = {nid: 0.0 for nid in self.graph.node_ids()}
            node_inflow_step: Dict[str, float] = {nid: 0.0 for nid in self.graph.node_ids()}
            node_outflow_step: Dict[str, float] = {nid: 0.0 for nid in self.graph.node_ids()}
            node_flood_rate: Dict[str, float] = {nid: 0.0 for nid in self.graph.node_ids()}

            # 1. Procesar eventos de llegada programados en la PriorityQueue hasta t_curr_s
            while not event_queue.is_empty():
                arr_t, _ = event_queue.peek()
                if arr_t > t_curr_s + 1e-9:
                    break
                _, ev = event_queue.pop()
                node_arrivals[ev.target_node] += ev.volume_m3
                new_transit = max(0.0, pipe_transit_vol[ev.pipe_id] - ev.volume_m3)
                pipe_transit_vol.put(ev.pipe_id, new_transit)

            # 2. Inyectar caudal en nodos fuente
            for sid in self.graph.source_ids():
                q_src = q_by_source.get(sid, 0.0)
                vol_in = q_src * dt_s
                node_arrivals[sid] += vol_in
                node_inflow_step[sid] += q_src
                cum_inflow_m3 += vol_in

            pipe_states: Dict[str, PipeStepState] = {}
            step_sink_vol = 0.0
            critical_ids: List[str] = []
            overloaded_ids: List[str] = []

            # 3. Propagar en orden topológico (permite tránsito inmediato si t_i <= dt)
            for u in self._topo_order:
                avail_vol = node_stored[u] + node_arrivals[u]
                if u not in source_set:
                    node_inflow_step[u] = node_arrivals[u] / dt_s

                if u in sink_set or self.graph.out_degree(u) == 0:
                    step_sink_vol += avail_vol
                    cum_sink_m3 += avail_vol
                    node_stored.put(u, 0.0)
                    node_outflow_step[u] = avail_vol / dt_s
                    continue

                outgoing = self.graph.outgoing_pipes(u).to_list()
                if config.split_rule == "equal":
                    weights = [1.0 / len(outgoing)] * len(outgoing)
                else:
                    total_cap = sum(eff_params[p.pipe_id][0] for p in outgoing)
                    weights = [
                        (eff_params[p.pipe_id][0] / total_cap)
                        if total_cap > 0
                        else (1.0 / len(outgoing))
                        for p in outgoing
                    ]

                remaining_stored = 0.0
                total_sent_u = 0.0

                for edge, w in zip(outgoing, weights):
                    eff_q_max, eff_vel_ms, eff_transit_s, _eff_diam = eff_params[edge.pipe_id]
                    demand_vol = avail_vol * w
                    cap_vol = eff_q_max * dt_s
                    sent_vol = min(demand_vol, cap_vol)
                    excess_vol = max(0.0, demand_vol - sent_vol)
                    remaining_stored += excess_vol
                    total_sent_u += sent_vol

                    if sent_vol > 0.0:
                        t_transit_s = eff_transit_s
                        arrival_s = t_prev_s + t_transit_s
                        if arrival_s <= t_curr_s + 1e-9:
                            # Llega dentro del mismo intervalo discreto
                            node_arrivals[edge.to_node] += sent_vol
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

                    # Caudal de demanda vs caudal físico acotado en tubería (tope presurizado <= max_phys_util)
                    q_arrival_share = (node_arrivals[u] * w) / dt_s
                    q_conveyed = sent_vol / dt_s
                    vol_in_pipe = pipe_transit_vol[edge.pipe_id]
                    q_in_transit = (
                        vol_in_pipe / eff_transit_s
                        if eff_transit_s > dt_s
                        else q_conveyed
                    )
                    if eff_q_max <= 1e-12:
                        if excess_vol > 1e-9 or q_arrival_share > 1e-9:
                            q_demand = max(q_arrival_share, demand_vol / dt_s)
                            base_ref = max(edge.q_max_m3s, 1e-6)
                            demand_ratio = max(105.0, (q_demand / base_ref) * 100.0)
                            util_pct = max_phys_util
                            q_physical = 0.0
                        else:
                            q_demand = 0.0
                            demand_ratio = 0.0
                            util_pct = 0.0
                            q_physical = 0.0
                        excess_q = q_demand
                    else:
                        q_demand = max(q_arrival_share, q_conveyed, q_in_transit)
                        if excess_vol > 1e-9 or q_demand > eff_q_max + 1e-9:
                            q_demand = max(q_demand, eff_q_max * 1.05)
                            demand_ratio = (q_demand / eff_q_max) * 100.0
                            over_frac = max(0.05, (q_demand - eff_q_max) / eff_q_max)
                            util_pct = 100.0 + (max_phys_util - 100.0) * (1.0 - math.exp(-1.6 * over_frac))
                            q_physical = eff_q_max * (util_pct / 100.0)
                        else:
                            q_physical = min(eff_q_max, q_demand)
                            util_pct = (q_physical / eff_q_max) * 100.0
                            demand_ratio = (q_demand / eff_q_max) * 100.0
                        excess_q = max(0.0, q_demand - eff_q_max)

                    cat = classify_utilization(util_pct)

                    pipe_states[edge.pipe_id] = PipeStepState(
                        pipe_id=edge.pipe_id,
                        flow_m3s=q_physical,
                        conveyed_flow_m3s=q_conveyed,
                        volume_in_transit_m3=vol_in_pipe,
                        utilization_pct=util_pct,
                        category=cat,
                        excess_flow_m3s=excess_q,
                        demand_flow_m3s=q_demand,
                        demand_ratio_pct=demand_ratio,
                        effective_q_max_m3s=eff_q_max,
                        effective_velocity_ms=eff_vel_ms,
                    )

                    if util_pct > peak_util[edge.pipe_id]:
                        peak_util[edge.pipe_id] = util_pct
                    if q_physical > peak_flow[edge.pipe_id]:
                        peak_flow[edge.pipe_id] = q_physical
                    if demand_ratio > peak_demand_ratio[edge.pipe_id]:
                        peak_demand_ratio[edge.pipe_id] = demand_ratio
                    if q_demand > peak_demand_flow[edge.pipe_id]:
                        peak_demand_flow[edge.pipe_id] = q_demand
                    if cat.is_critical:
                        critical_ids.append(edge.pipe_id)
                        ever_critical.add(edge.pipe_id)
                    if cat.is_overloaded:
                        overloaded_ids.append(edge.pipe_id)
                        ever_overloaded.add(edge.pipe_id)

                stored_u = min(remaining_stored, cap_manhole)
                spill_u = max(0.0, remaining_stored - stored_u)
                node_stored.put(u, stored_u)
                if spill_u > 0.0:
                    node_flooded.put(u, node_flooded[u] + spill_u)
                    node_flood_rate[u] = spill_u / dt_s
                node_outflow_step[u] = total_sent_u / dt_s
                if stored_u > max_storage[u]:
                    max_storage[u] = stored_u

            total_manhole_storage = sum(node_stored[nid] for nid in self.graph.node_ids())
            total_pipe_transit = sum(pipe_transit_vol[pid] for pid in self.graph.pipe_ids())
            total_surface_flooding = sum(node_flooded[nid] for nid in self.graph.node_ids())
            mass_err = abs(
                cum_inflow_m3
                - (cum_sink_m3 + total_manhole_storage + total_pipe_transit + total_surface_flooding)
            )
            max_mass_err = max(max_mass_err, mass_err)

            sink_q = step_sink_vol / dt_s
            peak_sink_q = max(peak_sink_q, sink_q)

            node_states = {
                nid: NodeStepState(
                    node_id=nid,
                    inflow_m3s=node_inflow_step[nid],
                    outflow_m3s=node_outflow_step[nid],
                    stored_volume_m3=node_stored[nid],
                    surface_flooding_m3=node_flooded[nid],
                    flooding_rate_m3s=node_flood_rate[nid],
                )
                for nid in self.graph.node_ids()
            }

            self.history.append(
                TimeStepSnapshot(
                    step_index=step,
                    time_min=t_curr_min,
                    rain_intensity_mm_h=intensity,
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
                    overloaded_pipe_ids=overloaded_ids,
                )
            )

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        snapshots_list = self.history.to_list()
        actual_duration_min = (
            snapshots_list[-1].time_min
            if snapshots_list
            else max(dt_min, float(config.duration_min))
        )
        overloaded_minutes: Dict[str, float] = {pid: 0.0 for pid in self.graph.pipe_ids()}
        for snap in self.history:
            if snap.step_index == 0:
                continue
            for pid in snap.overloaded_pipe_ids:
                overloaded_minutes[pid] = min(
                    actual_duration_min,
                    overloaded_minutes.get(pid, 0.0) + dt_min,
                )

        last_snap = snapshots_list[-1]
        residual = last_snap.total_manhole_storage_m3 + last_snap.total_pipe_transit_m3
        max_flood_by_node = {nid: node_flooded[nid] for nid in self.graph.node_ids()}

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
            ever_overloaded_pipes=sorted(ever_overloaded),
            execution_time_ms=elapsed_ms,
            pipe_overloaded_minutes=overloaded_minutes,
            peak_pipe_demand_ratio=peak_demand_ratio,
            peak_pipe_demand_flow=peak_demand_flow,
            total_surface_flooding_m3=last_snap.total_surface_flooding_m3,
            max_node_flooding_m3=max_flood_by_node,
        )
