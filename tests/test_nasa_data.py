import io
import unittest
from unittest.mock import Mock, patch

from src import nasa_data


class NasaDataTests(unittest.TestCase):
    def test_parse_sep_events_normalizes_and_sorts(self):
        events = nasa_data.parse_sep_events([
            {
                "sepID": "older",
                "eventTime": "2025-01-01T10:00Z",
                "instruments": [{"displayName": "GOES"}],
                "link": "https://example.test/older",
            },
            {
                "sepID": "newer",
                "eventTime": "2025-01-02T10:00Z",
                "instruments": [{"displayName": "SOHO"}],
            },
        ])

        self.assertEqual([event["ID"] for event in events], ["newer", "older"])
        self.assertEqual(events[1]["Instrumentos"], "GOES")
        self.assertEqual(events[1]["Ficha NASA"], "https://example.test/older")

    def test_parse_sep_events_rejects_invalid_response(self):
        with self.assertRaises(ValueError):
            nasa_data.parse_sep_events({"unexpected": "object"})

    @patch.object(nasa_data.requests, "get")
    def test_fetch_sep_events_sends_dates_and_key(self, get):
        response = Mock()
        response.json.return_value = [{
            "sepID": "event-1",
            "eventTime": "2025-01-02T10:00Z",
            "instruments": [],
        }]
        get.return_value = response

        events = nasa_data.fetch_sep_events("2025-01-01", "2025-01-03", api_key="test-key")

        self.assertEqual(events[0]["ID"], "event-1")
        self.assertEqual(get.call_args.kwargs["params"], {
            "startDate": "2025-01-01",
            "endDate": "2025-01-03",
            "api_key": "test-key",
        })
        response.raise_for_status.assert_called_once_with()

    @patch.object(nasa_data.requests, "get")
    def test_fetch_sep_events_rejects_reversed_dates_before_request(self, get):
        with self.assertRaises(ValueError):
            nasa_data.fetch_sep_events("2025-01-03", "2025-01-01")
        get.assert_not_called()

    def test_read_reference_dataset_accepts_tab_separated_file(self):
        dataset = nasa_data.read_reference_dataset(io.BytesIO(b"sample\tvalue\nA\t2\nB\t3\n"))

        self.assertEqual(list(dataset.columns), ["sample", "value"])
        self.assertEqual(len(dataset), 2)

    def test_read_reference_dataset_rejects_empty_file(self):
        with self.assertRaises(ValueError):
            nasa_data.read_reference_dataset(io.BytesIO(b""))


if __name__ == "__main__":
    unittest.main()
