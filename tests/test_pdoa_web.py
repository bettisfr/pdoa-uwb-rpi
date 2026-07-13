import csv
from datetime import datetime
import importlib.util
import tempfile
import time
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pdoa-web.py"
SPEC = importlib.util.spec_from_file_location("pdoa_web", MODULE_PATH)
pdoa_web = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pdoa_web)


class ExperimentTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "logs").mkdir()
        self.log_path = self.root / "logs" / "pdoa_test.csv"
        self.app = pdoa_web.App(self.root, "/dev/null", "127.0.0.1", 0, False, 100)
        self.app.monitor = RunningMonitor()

    def tearDown(self):
        self.temporary.cleanup()

    def write_rows(self, count, timestamp, tag_names=None):
        tag_names = set(tag_names or [item["tag"] for item in pdoa_web.TAG_LAYOUT])
        with self.log_path.open("w", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=pdoa_web.RAW_FIELDS)
            writer.writeheader()
            for index in range(count):
                for tag_index, layout in enumerate(pdoa_web.TAG_LAYOUT):
                    if layout["tag"] not in tag_names:
                        continue
                    writer.writerow({
                        "time": timestamp,
                        "tag": layout["tag"],
                        "a16": f"{tag_index:04X}",
                        "seq": index,
                        "range_cm": 200,
                        "pdoa_deg": tag_index,
                        "x_cm": tag_index + 1,
                        "y_cm": 10,
                        "clk_ppm": "0.10",
                        "t_us": 1000,
                    })

    def test_run_completes_and_writes_metadata(self):
        now = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        self.write_rows(1, now)
        state = self.app.create_experiment("Elevated test", 100, 2.5)
        self.assertEqual(len(self.app.samples()["tags"]), 9)

        self.app.start_run(2, 90)
        state = self.app._load_state()
        state["active_run"]["started_epoch"] = time.time() - 1
        self.app._persist_experiment(state)
        self.write_rows(100, now)

        status = self.app.experiment_status()
        condition = status["experiment"]["conditions"]["2:90"]
        self.assertEqual(condition["status"], "complete")
        self.assertIsNone(status["experiment"]["active_run"])

        output = self.root / "datasets" / state["id"] / "runs" / condition["file"]
        with output.open(newline="") as fp:
            rows = list(csv.DictReader(fp))
        self.assertEqual(len(rows), 900)
        self.assertEqual(rows[0]["target_distance_m"], "2")
        self.assertEqual(rows[0]["tag_rotation_deg"], "90")
        self.assertEqual(rows[0]["node_height_m"], "2.5")
        self.assertEqual(rows[0]["missing_tags"], "")

        summary = self.app.run_summary(2, 90)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["bearings"][0]["tag"], "dw00")
        self.assertEqual(summary["bearings"][0]["samples"], 100)
        self.assertEqual(summary["bearings"][0]["range_avg_cm"], "200.0")

    def test_setup_can_change_before_first_run(self):
        state = self.app.create_experiment("Initial", 100, 1)
        updated = self.app.update_experiment("Ground", 200, 0)
        self.assertEqual(updated["name"], "Ground")
        self.assertEqual(updated["target_samples"], 200)
        self.assertEqual(updated["node_height_m"], 0)

    def test_node_requires_serial_device_and_monitor(self):
        self.assertTrue(self.app.node_ready())
        self.app.device = str(self.root / "missing-device")
        self.assertFalse(self.app.node_ready())

    def test_partial_run_records_missing_tag_and_advances(self):
        now = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        participating = [item["tag"] for item in pdoa_web.TAG_LAYOUT[:-1]]
        self.write_rows(1, now, participating)
        state = self.app.create_experiment("Partial", 100, 0)

        active = self.app.start_run(2, 0)
        self.assertEqual(active["missing_tags"], ["dw08"])
        state = self.app._load_state()
        state["active_run"]["started_epoch"] = time.time() - 1
        self.app._persist_experiment(state)
        self.write_rows(100, now, participating)

        status = self.app.experiment_status()
        condition = status["experiment"]["conditions"]["2:0"]
        self.assertEqual(condition["status"], "partial")
        self.assertEqual(status["next_condition"], {"distance_m": 2, "rotation_deg": 90})

        output = self.root / "datasets" / state["id"] / "runs" / condition["file"]
        with output.open(newline="") as fp:
            first = next(csv.DictReader(fp))
        self.assertEqual(first["missing_tags"], "dw08")

        with self.assertRaisesRegex(ValueError, "Confirmation"):
            self.app.clear_runs("delete")
        result = self.app.clear_runs("DELETE_ALL_RUNS")
        self.assertEqual(result["deleted_runs"], 1)
        self.assertFalse(output.exists())
        reset = self.app._load_state()
        self.assertTrue(all(item == {"status": "pending", "attempts": 0} for item in reset["conditions"].values()))


class RunningMonitor:
    def poll(self):
        return None


if __name__ == "__main__":
    unittest.main()
