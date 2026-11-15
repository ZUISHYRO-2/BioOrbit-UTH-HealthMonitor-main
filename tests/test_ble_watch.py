import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src import ble_watch
sys.path.insert(0, os.path.abspath("src"))
import watch_connect


class BLEWatchTests(unittest.TestCase):
    def test_parses_standard_heart_rate_packet(self):
        measurement = ble_watch.parse_heart_rate_measurement(bytes([0, 72]))

        self.assertEqual(measurement["heart_rate_bpm"], 72.0)
        self.assertEqual(measurement["rr_intervals_ms"], [])

    def test_bridge_publishes_hrv_source_and_rejects_stale_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge_path = os.path.join(temp_dir, "live_watch_telemetry.json")
            with patch.object(ble_watch, "LIVE_BRIDGE_PATH", bridge_path):
                manager = ble_watch.BLEWatchManager()
                manager._publish_bridge_file(
                    ble_watch.WatchTelemetrySnapshot(
                        connected=True,
                        mode="ble_live",
                        heart_rate_bpm=72.0,
                        hrv_rmssd_ms=15.8,
                        hrv_source="Estimación desde BPM",
                    )
                )

                bridge = ble_watch.read_live_watch_bridge()
                self.assertEqual(bridge["hrv_source"], "Estimación desde BPM")

                with open(bridge_path, "w", encoding="utf-8") as file:
                    json.dump(
                        {
                            "connected": True,
                            "timestamp": 0,
                            "heart_rate_bpm": 72.0,
                            "hrv_rmssd_ms": 15.8,
                        },
                        file,
                    )
                self.assertIsNone(ble_watch.read_live_watch_bridge())

    def test_exit_requested_detects_q_and_esc_keys(self):
        fake_msvcrt = MagicMock()
        fake_msvcrt.kbhit.side_effect = [True, False, True, False, True, False]
        fake_msvcrt.getwch.side_effect = ["a", "q", "\x1b"]
        with patch.object(watch_connect, "msvcrt", fake_msvcrt), patch.object(
            watch_connect.sys.stdin, "isatty", return_value=True
        ):
            self.assertFalse(watch_connect._exit_requested())
            self.assertTrue(watch_connect._exit_requested())
            self.assertTrue(watch_connect._exit_requested())


if __name__ == "__main__":
    unittest.main()
