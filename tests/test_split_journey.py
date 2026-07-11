import unittest

from pysplit_inrail.split_journey import (
    extract_route_stops,
    find_same_train_split_journeys,
    generate_split_segments,
    parse_availability_status,
)


def _seat(class_code: str, status: str, fare: str = "100") -> dict:
    return {
        "success": True,
        "booking_class": class_code,
        "seat_availibility": [
            {f"Class - {class_code}": status, "total_fare": fare}
        ],
    }


class SplitJourneyTests(unittest.TestCase):
    def test_parse_availability_status(self) -> None:
        self.assertEqual(parse_availability_status("AVL 36")["kind"], "available")
        self.assertEqual(parse_availability_status("AVAILABLE-0036")["count"], 36)
        self.assertEqual(parse_availability_status("RAC138")["kind"], "rac")
        self.assertEqual(parse_availability_status("RAC138")["count"], 138)
        self.assertEqual(parse_availability_status("GNWL52/WL33")["kind"], "wl")
        self.assertEqual(parse_availability_status("GNWL52/WL33")["count"], 33)
        self.assertEqual(parse_availability_status("Regret")["kind"], "unavailable")

    def test_generate_split_segments_applies_route_day_date_offset(self) -> None:
        schedule = {
            "timeTableDaysGroup": [
                {
                    "items": [
                        {
                            "stop": True,
                            "station_code": "MAS",
                            "station_name": "MGR CHENNAI CENTRAL",
                            "day": 1,
                            "sta_min": 0,
                            "std_min": 1275,
                        },
                        {
                            "stop": True,
                            "station_code": "SBC",
                            "station_name": "KSR BENGALURU",
                            "day": 2,
                            "sta_min": 230,
                            "std_min": 240,
                        },
                        {
                            "stop": True,
                            "station_code": "MYS",
                            "station_name": "MYSORE JN",
                            "day": 2,
                            "sta_min": 400,
                            "std_min": 405,
                        },
                    ]
                }
            ]
        }

        segments = generate_split_segments(extract_route_stops(schedule), "31-07-2026", 2)

        self.assertEqual(segments[0][0].journey_date, "31-07-2026")
        self.assertEqual(segments[0][1].journey_date, "01-08-2026")

    def test_find_same_train_split_journeys_with_mocked_search(self) -> None:
        schedule = {
            "train_name": "Kaveri Express",
            "train_number": "16021",
            "timeTableDaysGroup": [
                {
                    "items": [
                        {
                            "stop": True,
                            "station_code": "MAS",
                            "station_name": "MGR CHENNAI CENTRAL",
                            "day": 1,
                            "sta_min": 0,
                            "std_min": 1275,
                        },
                        {
                            "stop": True,
                            "station_code": "SBC",
                            "station_name": "KSR BENGALURU",
                            "day": 2,
                            "sta_min": 230,
                            "std_min": 240,
                        },
                        {
                            "stop": True,
                            "station_code": "MYS",
                            "station_name": "MYSORE JN",
                            "day": 2,
                            "sta_min": 400,
                            "std_min": 405,
                        },
                    ]
                }
            ],
        }
        calls = []

        def fake_train_search(from_station, to_station, journey_date, **kwargs):
            calls.append((from_station, to_station, journey_date))
            status_by_pair = {
                ("MAS", "SBC"): "WL 5",
                ("SBC", "MYS"): "AVL 10",
            }
            return {
                "success": True,
                "train_between_stations": [
                    {
                        "train_name": "KAVERI EXPRESS",
                        "train_number": "16021",
                        "sa_data": [_seat("SL", status_by_pair[(from_station, to_station)])],
                    }
                ],
            }

        result = find_same_train_split_journeys(
            train_number="16021",
            from_station="MAS",
            to_station="MYS",
            journey_date="31-07-2026",
            classes="SL",
            max_segments=2,
            max_wl=20,
            schedule_data=schedule,
            train_search_func=fake_train_search,
        )

        self.assertEqual(len(result["results"]), 1)
        split = result["results"][0]
        self.assertEqual(split["class"], "SL")
        self.assertEqual(split["split_stations"][0]["code"], "SBC")
        self.assertEqual(split["segments"][1]["journey_date"], "01-08-2026")
        self.assertEqual(calls, [("MAS", "SBC", "31-07-2026"), ("SBC", "MYS", "01-08-2026")])




if __name__ == "__main__":
    unittest.main()
