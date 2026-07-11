from contextlib import ExitStack
import sys
import unittest
from unittest.mock import patch

import rail_scrapper


class CliTests(unittest.TestCase):
    def test_no_args_runs_configured_default_command(self) -> None:
        command_runners = {
            "station": "_run_station_search",
            "stations": "_run_station_search",
            "search-station": "_run_station_search",
            "trains": "_run_trains",
            "schedule": "_run_schedule",
            "split": "_run_split",
            "split-journey": "_run_split",
            "demo": "_run_demo",
        }
        expected_runner = command_runners[rail_scrapper.DEFAULT_COMMAND]

        with ExitStack() as stack:
            mocks = {
                name: stack.enter_context(patch.object(rail_scrapper, name, return_value=0))
                for name in set(command_runners.values())
            }
            stack.enter_context(patch.object(sys, "argv", ["rail_scrapper.py"]))
            result = rail_scrapper.main()

        self.assertEqual(result, 0)
        for runner_name, runner_mock in mocks.items():
            if runner_name == expected_runner:
                runner_mock.assert_called_once()
            else:
                runner_mock.assert_not_called()

    def test_station_command_uses_hardcoded_defaults(self) -> None:
        with patch.object(rail_scrapper, "_run_station_search", return_value=0) as run_station:
            result = rail_scrapper.main(["station"])

        self.assertEqual(result, 0)
        args = run_station.call_args.args[0]
        self.assertEqual(args.query, rail_scrapper.DEFAULT_STATION_QUERY)
        self.assertEqual(args.limit, rail_scrapper.DEFAULT_STATION_LIMIT)

    def test_trains_command_uses_hardcoded_defaults(self) -> None:
        with patch.object(rail_scrapper, "_run_trains", return_value=0) as run_trains:
            result = rail_scrapper.main(["trains"])

        self.assertEqual(result, 0)
        args = run_trains.call_args.args[0]
        self.assertEqual(args.from_station, rail_scrapper.DEFAULT_FROM_STATION)
        self.assertEqual(args.to_station, rail_scrapper.DEFAULT_TO_STATION)
        self.assertEqual(args.date, rail_scrapper.DEFAULT_JOURNEY_DATE)
        self.assertEqual(args.quota, rail_scrapper.DEFAULT_QUOTA)
        self.assertEqual(args.provider, rail_scrapper.DEFAULT_TRAIN_PROVIDER)

    def test_schedule_command_uses_hardcoded_defaults(self) -> None:
        with patch.object(rail_scrapper, "_run_schedule", return_value=0) as run_schedule:
            result = rail_scrapper.main(["schedule"])

        self.assertEqual(result, 0)
        args = run_schedule.call_args.args[0]
        self.assertEqual(args.train_number, rail_scrapper.DEFAULT_SCHEDULE_TRAIN)

    def test_split_command_uses_hardcoded_defaults(self) -> None:
        with patch.object(rail_scrapper, "_run_split", return_value=0) as run_split:
            result = rail_scrapper.main(["split"])

        self.assertEqual(result, 0)
        args = run_split.call_args.args[0]
        self.assertEqual(args.train_number, rail_scrapper.DEFAULT_SPLIT_TRAIN)
        self.assertEqual(args.from_station, rail_scrapper.DEFAULT_FROM_STATION)
        self.assertEqual(args.to_station, rail_scrapper.DEFAULT_TO_STATION)
        self.assertEqual(args.date, rail_scrapper.DEFAULT_JOURNEY_DATE)
        self.assertEqual(args.classes, rail_scrapper.DEFAULT_SPLIT_CLASSES)
        self.assertEqual(args.max_segments, rail_scrapper.DEFAULT_SPLIT_MAX_SEGMENTS)
        self.assertEqual(args.max_wl, rail_scrapper.DEFAULT_SPLIT_MAX_WL)
        self.assertEqual(args.max_results, rail_scrapper.DEFAULT_SPLIT_MAX_RESULTS)
        self.assertEqual(args.accept_rac, rail_scrapper.DEFAULT_SPLIT_ACCEPT_RAC)
        self.assertEqual(args.search_deeper, rail_scrapper.DEFAULT_SPLIT_SEARCH_DEEPER)


if __name__ == "__main__":
    unittest.main()
