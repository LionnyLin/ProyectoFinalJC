"""Pruebas unitarias para carga y validación desde Excel y CSV."""

import os
import tempfile
import unittest

from src.io.data_loader import DataLoadError, export_to_csv_dir, load_dataset


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_XLSX = os.path.join(BASE_DIR, "data", "DataSetBicentenario.xlsx")
DATA_CSV = os.path.join(BASE_DIR, "data", "csv")


class TestLoader(unittest.TestCase):
    def test_excel_and_csv_parity(self) -> None:
        ds_xlsx = load_dataset(DATA_XLSX)
        ds_csv = load_dataset(DATA_CSV)

        self.assertEqual(ds_xlsx.graph.summary()[:4], (46, 59, 8, 1))
        self.assertAlmostEqual(ds_xlsx.graph.total_network_length_m(), 19163.57, places=2)
        self.assertEqual(ds_xlsx.graph.summary()[:4], ds_csv.graph.summary()[:4])
        self.assertAlmostEqual(
            ds_xlsx.graph.total_network_length_m(),
            ds_csv.graph.total_network_length_m(),
            places=2,
        )
        self.assertEqual(len(ds_xlsx.scenarios), 5)
        self.assertEqual(len(ds_csv.scenarios), 5)
        self.assertAlmostEqual(ds_xlsx.basin.runoff_coefficient_c, 0.75)
        self.assertAlmostEqual(ds_xlsx.basin.area_ha, 388.0)

    def test_missing_or_invalid_path_raises(self) -> None:
        with self.assertRaises(DataLoadError):
            load_dataset("no_existe.xlsx")

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(DataLoadError):
                load_dataset(tmpdir)

    def test_csv_blank_rows_are_ignored_gracefully(self) -> None:
        ds_base = load_dataset(DATA_CSV)
        with tempfile.TemporaryDirectory() as tmpdir:
            export_to_csv_dir(ds_base, tmpdir)
            for fname in ("pipes.csv", "precipitation_scenarios.csv"):
                with open(os.path.join(tmpdir, fname), "a", encoding="utf-8") as f:
                    f.write(",,,,,\n")
            ds_reloaded = load_dataset(tmpdir)
            self.assertEqual(ds_reloaded.graph.summary()[:4], (46, 59, 8, 1))
            self.assertEqual(len(ds_reloaded.scenarios), 5)

    def test_dead_end_and_diameter_mismatch_rejected(self) -> None:
        # M5: nodo intermedio sin salida (error tipográfico en to_node) debe fallar validación
        ds_base = load_dataset(DATA_CSV)
        with tempfile.TemporaryDirectory() as tmpdir:
            export_to_csv_dir(ds_base, tmpdir)
            pipes_path = os.path.join(tmpdir, "pipes.csv")
            with open(pipes_path, "r", encoding="utf-8") as f:
                txt = f.read()
            # Desviar P3 hacia un nodo fantasma "3l" -> deja a "C" o "3l" como callejón sin salida
            with open(pipes_path, "w", encoding="utf-8") as f:
                f.write(txt.replace(",C,31,", ",C,3l,"))
            with self.assertRaises(DataLoadError):
                load_dataset(tmpdir)

        # M6: inconsistencia entre diameter_in y diameter_m debe fallar
        with tempfile.TemporaryDirectory() as tmpdir:
            export_to_csv_dir(ds_base, tmpdir)
            pipes_path = os.path.join(tmpdir, "pipes.csv")
            with open(pipes_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            parts = lines[1].split(",")
            parts[4] = "0.9999"  # diameter_m inconsistente con diameter_in=8"
            lines[1] = ",".join(parts)
            with open(pipes_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            with self.assertRaises(DataLoadError):
                load_dataset(tmpdir)

    def test_external_network_does_not_inherit_bicentenario_coords(self) -> None:
        # M7: una red pequeña con IDs genéricos ("1", "2", "99") sin node_coords.csv usa layout topológico
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "sources.csv"), "w", encoding="utf-8") as f:
                f.write("node_id\n1\n")
            with open(os.path.join(tmpdir, "sinks.csv"), "w", encoding="utf-8") as f:
                f.write("node_id\n99\n")
            with open(os.path.join(tmpdir, "drainage_basin.csv"), "w", encoding="utf-8") as f:
                f.write("runoff_coefficient_c,area_ha\n0.75,10.0\n")
            with open(os.path.join(tmpdir, "precipitation_scenarios.csv"), "w", encoding="utf-8") as f:
                f.write("scenario_id,condition,intensity_mm_h\n1,Light rain,10.0\n")
            with open(os.path.join(tmpdir, "pipes.csv"), "w", encoding="utf-8") as f:
                f.write(
                    "pipe_id,from_node,to_node,diameter_in,diameter_m,manning_n,slope,q_max_m3s,length_m,note\n"
                    "P1,1,2,8,0.2032,0.015,0.01,,100.0,\n"
                    "P2,2,99,8,0.2032,0.015,0.01,,100.0,\n"
                )
            ds_ext = load_dataset(tmpdir)
            self.assertEqual(ds_ext.graph.summary()[:4], (3, 2, 1, 1))
            # Debe haber calculado q_max_m3s con fallback Manning y asignado x topológico (0.08 -> 0.5 -> 0.92)
            self.assertAlmostEqual(ds_ext.graph.get_pipe("P1").q_max_m3s, 0.02965436, places=6)
            self.assertLess(ds_ext.graph.get_node("1").x, ds_ext.graph.get_node("2").x)
            self.assertLess(ds_ext.graph.get_node("2").x, ds_ext.graph.get_node("99").x)


if __name__ == "__main__":
    unittest.main()
