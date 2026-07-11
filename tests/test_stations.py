import json
import tempfile
import unittest
from pathlib import Path

from stations import StationCacheError, load_station_cache, search_station_local


class StationTests(unittest.TestCase):
    def test_search_station_by_exact_code_first(self) -> None:
        station_data = [
            {"code": "MS", "name": "CHENNAI EGMORE"},
            {"code": "MAS", "name": "MGR CHENNAI CENTRAL"},
            {"code": "MYS", "name": "MYSORE JN"},
        ]

        results = search_station_local("mas", station_data)

        self.assertEqual(results[0], {"code": "MAS", "name": "MGR CHENNAI CENTRAL"})

    def test_search_station_by_name_with_limit(self) -> None:
        station_data = [
            {"code": "MAS", "name": "MGR CHENNAI CENTRAL"},
            {"code": "MS", "name": "CHENNAI EGMORE"},
            {"code": "CBE", "name": "COIMBATORE JN"},
        ]

        results = search_station_local("chennai", station_data, limit=1)

        self.assertEqual(results, [{"code": "MAS", "name": "MGR CHENNAI CENTRAL"}])

    def test_load_station_cache_validates_list_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_file = Path(directory) / "stations_cache.json"
            cache_file.write_text(json.dumps({"items": []}), encoding="utf-8")

            with self.assertRaises(StationCacheError):
                load_station_cache(cache_file)


if __name__ == "__main__":
    unittest.main()
