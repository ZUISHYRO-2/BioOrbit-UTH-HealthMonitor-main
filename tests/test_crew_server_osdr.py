import csv
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from crew_server import server


class CrewServerOsdrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_data = server.DATA
        self.original_db_path = server.DB_PATH
        self.original_catalog = server.OSDR_CATALOG
        server.DATA = Path(self.temp.name)
        server.DB_PATH = server.DATA / "crew.db"
        server.OSDR_CATALOG = server.DATA / "osdr_catalog.csv"
        with server.OSDR_CATALOG.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Experiment Title", "Missions", "Species"])
            writer.writeheader()
            writer.writerows([
                {"Experiment Title": "Lunar health", "Missions": "Artemis", "Species": "Human"},
                {"Experiment Title": "Plant growth", "Missions": "ISS", "Species": "Arabidopsis"},
            ])

        server._db = None
        server.create_user("control", "password", "Control", "CONTROL", "Control", "Tierra", "control")
        server.create_user("crew", "password", "Crew", "ASTRO-01", "Astronauta", "ISS")
        self.control_token = server.new_session("control")
        self.crew_token = server.new_session("crew")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        if server._db is not None:
            server._db.close()
        server._db = None
        server.DATA = self.original_data
        server.DB_PATH = self.original_db_path
        server.OSDR_CATALOG = self.original_catalog
        self.temp.cleanup()

    def get_catalog(self, query="", token=None):
        url = self.base + "/api/osdr/catalog" + query
        headers = {"Authorization": "Bearer " + token} if token else {}
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read())

    def test_control_can_search_and_page_through_catalog(self):
        first = self.get_catalog("?limit=1", self.control_token)
        self.assertEqual(first["total"], 2)
        self.assertEqual(first["rows"][0]["Experiment Title"], "Lunar health")

        second = self.get_catalog("?offset=1&limit=1", self.control_token)
        self.assertEqual(second["rows"][0]["Experiment Title"], "Plant growth")

        search = self.get_catalog("?q=artemis", self.control_token)
        self.assertEqual(search["total"], 1)
        self.assertEqual(search["rows"][0]["Missions"], "Artemis")

    def test_catalog_requires_control_session(self):
        for token, status in ((None, 401), (self.crew_token, 403)):
            with self.subTest(status=status):
                request = urllib.request.Request(
                    self.base + "/api/osdr/catalog",
                    headers={"Authorization": "Bearer " + token} if token else {},
                )
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request, timeout=3)
                self.assertEqual(error.exception.code, status)
                error.exception.close()


if __name__ == "__main__":
    unittest.main()
