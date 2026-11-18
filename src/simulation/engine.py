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

    def compute_source_inflow_m3s(
        self, config: SimulationConfig, intensity_mm_h: float
    ) -> Tuple[float, float]:
        """Calcula caudal pluvial total (Método Racional) y caudal total por nodo fuente.

        Fórmula: Q = 0.00278 * C * I * A * ingress_factor + Q_sanitario
        """
        sources = self.graph.source_ids()
        n_sources = max(1, len(sources))
        q_rational_raw = (
            0.00278
            * self.basin.runoff_coefficient_c
            * intensity_mm_h
            * self.basin.area_ha
        )
        q_rain_effective = q_rational_raw * config.ingress_factor
        q_per_source = (q_rain_effective / n_sources) + config.dry_weather_flow_per_source_m3s
        q_total = q_per_source * n_sources
        return q_total, q_per_source

    def run(self, config: SimulationConfig) -> SimulationResult:
        """Ejecuta la simulación completa y almacena cada instante en `self.history`."""
        t_start = time.perf_counter()
        self.history.clear()

        dt_min = max(0.1, config.dt_min)
        dt_s = dt_min * 60.0
        n_steps = max(1, int(math.ceil(config.duration_min / dt_min)))

        # Estructuras propias para estado en tiempo real
        node_stored: HashTable[str, float] = HashTable()
        pipe_transit_vol: HashTable[str, float] = HashTable()
        for nid in self.graph.node_ids():
            node_stored.put(nid, 0.0)
        for pid in self.graph.pipe_ids():
            pipe_transit_vol.put(pid, 0.0)

        event_queue: PriorityQueue[_TransitEvent] = PriorityQueue()
        source_set = set(self.graph.source_ids())
        sink_set = set(self.graph.sink_ids())

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
                effective_q_max_m3s=eff_params[p.pipe_id][0],
                effective_velocity_ms=eff_params[p.pipe_id][1],
            )
            for p in self.graph.pipes()
        }
        init_node_states = {
            nid: NodeStepState(nid, 0.0, 0.0, 0.0) for nid in self.graph.node_ids()
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
                pipe_states=init_pipe_states,
                node_states=init_node_states,
            )
        )

        cum_inflow_m3 = 0.0
        cum_sink_m3 = 0.0
        peak_util: Dict[str, float] = {p.pipe_id: 0.0 for p in self.graph.pipes()}
        peak_flow: Dict[str, float] = {p.pipe_id: 0.0 for p in self.graph.pipes()}
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
            total_src_q, q_per_src = self.compute_source_inflow_m3s(config, intensity)

            node_arrivals: Dict[str, float] = {nid: 0.0 for nid in self.graph.node_ids()}
            node_inflow_step: Dict[str, float] = {nid: 0.0 for nid in self.graph.node_ids()}
            node_outflow_step: Dict[str, float] = {nid: 0.0 for nid in self.graph.node_ids()}

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
                vol_in = q_per_src * dt_s
                node_arrivals[sid] += vol_in
                node_inflow_step[sid] += q_per_src
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

                    # Caudal efectivo en tubería: refleja la tasa instantánea de llegada + tránsito,
                    # evitando inflar artificialmente el caudal por acumulación histórica de volumen.
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
                            q_effective = max(q_arrival_share, demand_vol / dt_s)
                            base_ref = max(edge.q_max_m3s, 1e-6)
                            util_pct = max(105.0, (q_effective / base_ref) * 100.0)
                        else:
                            q_effective = 0.0
                            util_pct = 0.0
                    else:
                        if excess_vol > 1e-9:
                            # Si hay sobrecarga retenida en el pozo, la tubería excede 100% mientras drena
                            q_effective = max(q_arrival_share, eff_q_max * 1.05, q_in_transit)
                        else:
                            q_effective = max(q_arrival_share, q_conveyed, q_in_transit)
                        util_pct = (q_effective / eff_q_max) * 100.0
                    cat = classify_utilization(util_pct)
                    excess_q = max(0.0, q_effective - eff_q_max)

                    pipe_states[edge.pipe_id] = PipeStepState(
                        pipe_id=edge.pipe_id,
                        flow_m3s=q_effective,
                        conveyed_flow_m3s=q_conveyed,
                        volume_in_transit_m3=vol_in_pipe,
                        utilization_pct=util_pct,
                        category=cat,
                        excess_flow_m3s=excess_q,
                        effective_q_max_m3s=eff_q_max,
                        effective_velocity_ms=eff_vel_ms,
                    )

                    if util_pct > peak_util[edge.pipe_id]:
                        peak_util[edge.pipe_id] = util_pct
                    if q_effective > peak_flow[edge.pipe_id]:
                        peak_flow[edge.pipe_id] = q_effective
                    if cat.is_critical:
                        critical_ids.append(edge.pipe_id)
                        ever_critical.add(edge.pipe_id)
                    if cat.is_overloaded:
                        overloaded_ids.append(edge.pipe_id)
                        ever_overloaded.add(edge.pipe_id)

                node_stored.put(u, remaining_stored)
                node_outflow_step[u] = total_sent_u / dt_s
                if remaining_stored > max_storage[u]:
                    max_storage[u] = remaining_stored

            total_manhole_storage = sum(node_stored[nid] for nid in self.graph.node_ids())
            total_pipe_transit = sum(pipe_transit_vol[pid] for pid in self.graph.pipe_ids())
            mass_err = abs(
                cum_inflow_m3 - (cum_sink_m3 + total_manhole_storage + total_pipe_transit)
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
                    pipe_states=pipe_states,
                    node_states=node_states,
                    critical_pipe_ids=critical_ids,
                    overloaded_pipe_ids=overloaded_ids,
                )
            )

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        snapshots_list = self.history.to_list()
        overloaded_minutes: Dict[str, float] = {pid: 0.0 for pid in self.graph.pipe_ids()}
        for snap in self.history:
            if snap.step_index == 0:
                continue
            for pid in snap.overloaded_pipe_ids:
                overloaded_minutes[pid] = min(
                    config.duration_min,
                    overloaded_minutes.get(pid, 0.0) + config.dt_min,
                )

        last_snap = snapshots_list[-1]
        residual = last_snap.total_manhole_storage_m3 + last_snap.total_pipe_transit_m3

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
        )
