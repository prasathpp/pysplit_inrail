import unittest

from formatters import (
    format_schedule_info,
    format_split_journey_results,
    format_train_info,
    minutes_to_hhmm,
)


class FormatterTests(unittest.TestCase):
    def test_minutes_to_hhmm_wraps_next_day(self) -> None:
        self.assertEqual(minutes_to_hhmm(0), "START")
        self.assertEqual(minutes_to_hhmm(1500), "01:00")
        self.assertEqual(minutes_to_hhmm(None), "N/A")

    def test_format_train_info_uses_ascii_fare_label(self) -> None:
        payload = {
            "success": True,
            "train_between_stations": [
                {
                    "train_name": "Example Express",
                    "train_number": "12345",
                    "from_station_name": "MGR CHENNAI CENTRAL",
                    "to_station_name": "MYSORE JN",
                    "from_std": "05:50",
                    "to_sta": "12:20",
                    "duration": "6:30",
                    "sa_data": [
                        {
                            "success": True,
                            "booking_class": "CC",
                            "seat_availibility": [
                                {"Class - CC": "AVAILABLE-0010", "total_fare": 100}
                            ],
                        }
                    ],
                }
            ],
        }

        output = format_train_info(payload, "31-07-2026")

        self.assertIn("Example Express (12345)", output)
        self.assertIn("CC: AVAILABLE-0010 (Rs. 100)", output)

    def test_format_train_info_includes_prediction_when_available(self) -> None:
        payload = {
            "success": True,
            "train_between_stations": [
                {
                    "train_name": "KAVERI EXPRESS",
                    "train_number": "16021",
                    "from_station_name": "Chennai Central",
                    "to_station_name": "Mysore Junction",
                    "from_std": "21:15",
                    "to_sta": "06:40",
                    "duration": "9:25",
                    "sa_data": [
                        {
                            "success": True,
                            "booking_class": "SL",
                            "seat_availibility": [
                                {
                                    "Class - SL": "WL 33",
                                    "total_fare": "310",
                                    "prediction": "90% Chance",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        output = format_train_info(payload, "31-07-2026")

        self.assertIn("SL: WL 33 (Rs. 310, 90% Chance)", output)

    def test_format_schedule_info_skips_non_stops(self) -> None:
        schedule = {
            "train_name": "Example Express",
            "train_number": "12345",
            "run_days": ["MON", "TUE"],
            "timeTableDaysGroup": [
                {
                    "items": [
                        {
                            "stop": True,
                            "station_name": "MGR CHENNAI CTL",
                            "station_code": "MAS",
                            "sta_min": 0,
                            "std_min": 360,
                            "day": 1,
                        },
                        {
                            "stop": False,
                            "station_name": "PASSING",
                            "station_code": "PASS",
                            "sta_min": 400,
                            "std_min": 400,
                            "day": 1,
                        },
                    ]
                }
            ],
        }

        output = format_schedule_info(schedule)

        self.assertIn("SCHEDULE FOR: Example Express (12345)", output)
        self.assertIn("MGR CHENNAI CTL", output)
        self.assertNotIn("PASSING", output)

    def test_format_split_journey_results(self) -> None:
        payload = {
            "success": True,
            "train_name": "Kaveri Express",
            "train_number": "16021",
            "from": {"code": "MAS", "name": "MGR CHENNAI CENTRAL"},
            "to": {"code": "MYS", "name": "MYSORE JN"},
            "accept_rac": True,
            "max_wl": 20,
            "checked_combinations": 1,
            "checked_segments": 2,
            "results": [
                {
                    "class": "SL",
                    "segment_count": 2,
                    "split_stations": [{"code": "SBC", "name": "KSR BENGALURU"}],
                    "segments": [
                        {
                            "from": {"code": "MAS"},
                            "to": {"code": "SBC"},
                            "journey_date": "31-07-2026",
                            "status": "WL 5",
                            "fare": "245",
                        },
                        {
                            "from": {"code": "SBC"},
                            "to": {"code": "MYS"},
                            "journey_date": "01-08-2026",
                            "status": "AVL 10",
                            "fare": "150",
                        },
                    ],
                }
            ],
        }

        output = format_split_journey_results(payload)

        self.assertIn("Split journey options for Kaveri Express (16021)", output)
        self.assertIn("Class SL | 2 segments via SBC", output)
        self.assertIn("MAS -> SBC on 31-07-2026: WL 5", output)


if __name__ == "__main__":
    unittest.main()
