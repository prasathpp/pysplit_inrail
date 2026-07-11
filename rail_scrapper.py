import argparse
import sys
from pathlib import Path
from typing import Any

from pysplit_inrail.formatters import (
    format_split_journey_results,
    format_schedule_info,
    format_station_results,
    format_train_info,
)
from pysplit_inrail.railway_api import (
    RailwayApiError,
    SUPPORTED_TRAIN_SEARCH_PROVIDERS,
    create_session,
    get_schedule_from_page,
    get_trains_between_stations,
)
from pysplit_inrail.split_journey import SplitJourneyError, find_same_train_split_journeys
from pysplit_inrail.stations import StationCacheError, load_station_cache, search_station_local


# Hardcoded inputs. Change these when you want to run without CLI arguments.
DEFAULT_COMMAND = "split" # station, trains, schedule, split, demo
DEFAULT_CACHE_FILE = Path(__file__).with_name("stations_cache.json")
DEFAULT_STATION_QUERY = "chennai"
DEFAULT_STATION_LIMIT = 10
DEFAULT_FROM_STATION = "MAS"
DEFAULT_TO_STATION = "MYS"
DEFAULT_JOURNEY_DATE = "31-07-2026"
DEFAULT_QUOTA = "GN"
DEFAULT_TRAIN_PROVIDER = "ixigo"
DEFAULT_SCHEDULE_TRAIN = "16021"
DEFAULT_SPLIT_TRAIN = "16021"
DEFAULT_SPLIT_CLASSES = "SL,3A,2A" # SL,3A,2A,1A,CC,2S,FC,EC
DEFAULT_SPLIT_MAX_SEGMENTS = 3
DEFAULT_SPLIT_MAX_WL = 20
DEFAULT_SPLIT_MAX_RESULTS = 10
DEFAULT_SPLIT_ACCEPT_RAC = True
DEFAULT_SPLIT_SEARCH_DEEPER = False
DEFAULT_DEMO_STATION_LIMIT = 5
DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 2


def display_train_info(train_data: dict[str, Any] | None, journey_date: str) -> None:
    """Backward-compatible print wrapper for train search results."""
    print(format_train_info(train_data, journey_date))


def display_schedule_info(schedule_data: dict[str, Any] | None) -> None:
    """Backward-compatible print wrapper for schedule results."""
    print(format_schedule_info(schedule_data))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search Indian Railways stations, trains, and schedules."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    station_parser = subparsers.add_parser(
        "station",
        aliases=["stations", "search-station"],
        help="Search stations from the local cache.",
    )
    station_parser.add_argument(
        "query",
        nargs="?",
        default=DEFAULT_STATION_QUERY,
        help=f"Station name or station code to search, default {DEFAULT_STATION_QUERY}.",
    )
    station_parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE_FILE,
        help="Path to stations_cache.json.",
    )
    station_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_STATION_LIMIT,
        help="Maximum station results to show.",
    )

    trains_parser = subparsers.add_parser(
        "trains",
        help="Fetch trains and availability between two stations.",
    )
    trains_parser.add_argument("--from", dest="from_station", default=DEFAULT_FROM_STATION, help="Source station code.")
    trains_parser.add_argument("--to", dest="to_station", default=DEFAULT_TO_STATION, help="Destination station code.")
    trains_parser.add_argument("--date", default=DEFAULT_JOURNEY_DATE, help="Journey date in DD-MM-YYYY format.")
    trains_parser.add_argument("--quota", default=DEFAULT_QUOTA, help=f"Journey quota, default {DEFAULT_QUOTA}.")
    trains_parser.add_argument(
        "--provider",
        choices=SUPPORTED_TRAIN_SEARCH_PROVIDERS,
        default=DEFAULT_TRAIN_PROVIDER,
        help=f"Train search provider, default {DEFAULT_TRAIN_PROVIDER}.",
    )
    trains_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds.")
    trains_parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="HTTP retry count.")

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Fetch a train schedule by train number.",
    )
    schedule_parser.add_argument(
        "train_number",
        nargs="?",
        default=DEFAULT_SCHEDULE_TRAIN,
        help=f"Train number, default {DEFAULT_SCHEDULE_TRAIN}.",
    )
    schedule_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds.")
    schedule_parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="HTTP retry count.")

    split_parser = subparsers.add_parser(
        "split",
        aliases=["split-journey"],
        help="Find same-train break/split journey options.",
    )
    split_parser.add_argument(
        "train_number",
        nargs="?",
        default=DEFAULT_SPLIT_TRAIN,
        help=f"Train number, default {DEFAULT_SPLIT_TRAIN}.",
    )
    split_parser.add_argument("--from", dest="from_station", default=DEFAULT_FROM_STATION)
    split_parser.add_argument("--to", dest="to_station", default=DEFAULT_TO_STATION)
    split_parser.add_argument("--date", default=DEFAULT_JOURNEY_DATE)
    split_parser.add_argument("--quota", default=DEFAULT_QUOTA)
    split_parser.add_argument(
        "--provider",
        choices=SUPPORTED_TRAIN_SEARCH_PROVIDERS,
        default=DEFAULT_TRAIN_PROVIDER,
    )
    split_parser.add_argument(
        "--classes",
        default=DEFAULT_SPLIT_CLASSES,
        help="Preferred class order, comma-separated. Example: SL,3A,2A",
    )
    split_parser.add_argument(
        "--max-segments",
        type=int,
        default=DEFAULT_SPLIT_MAX_SEGMENTS,
        help="Maximum total ticket segments to try.",
    )
    split_parser.add_argument(
        "--max-wl",
        type=int,
        default=DEFAULT_SPLIT_MAX_WL,
        help="Maximum WL number to treat as acceptable.",
    )
    split_parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_SPLIT_MAX_RESULTS,
        help="Maximum split options to show.",
    )
    split_parser.add_argument(
        "--no-rac",
        dest="accept_rac",
        action="store_false",
        help="Do not treat RAC as acceptable.",
    )
    split_parser.add_argument(
        "--search-deeper",
        action="store_true",
        default=DEFAULT_SPLIT_SEARCH_DEEPER,
        help="Continue checking deeper splits even after finding shallower options.",
    )
    split_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    split_parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    split_parser.set_defaults(accept_rac=DEFAULT_SPLIT_ACCEPT_RAC)

    demo_parser = subparsers.add_parser(
        "demo",
        help="Run the original MAS to MYS and 12164 example.",
    )
    demo_parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_FILE)
    demo_parser.add_argument("--station-query", default=DEFAULT_STATION_QUERY)
    demo_parser.add_argument("--station-limit", type=int, default=DEFAULT_DEMO_STATION_LIMIT)
    demo_parser.add_argument("--from", dest="from_station", default=DEFAULT_FROM_STATION)
    demo_parser.add_argument("--to", dest="to_station", default=DEFAULT_TO_STATION)
    demo_parser.add_argument("--date", default=DEFAULT_JOURNEY_DATE)
    demo_parser.add_argument("--quota", default=DEFAULT_QUOTA)
    demo_parser.add_argument(
        "--provider",
        choices=SUPPORTED_TRAIN_SEARCH_PROVIDERS,
        default=DEFAULT_TRAIN_PROVIDER,
    )
    demo_parser.add_argument("--schedule-train", default=DEFAULT_SCHEDULE_TRAIN)
    demo_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    demo_parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)

    return parser


def _run_station_search(args: argparse.Namespace) -> int:
    station_data = load_station_cache(args.cache)
    stations = search_station_local(args.query, station_data, limit=args.limit)
    print(format_station_results(args.query, stations))
    return 0


def _run_trains(args: argparse.Namespace) -> int:
    session = create_session(retries=args.retries)
    train_data = get_trains_between_stations(
        args.from_station,
        args.to_station,
        args.date,
        quota=args.quota,
        provider=args.provider,
        session=session,
        timeout=args.timeout,
        use_fetch_availability=True,
    )
    print(format_train_info(train_data, args.date, quota=args.quota))
    return 0


def _run_schedule(args: argparse.Namespace) -> int:
    session = create_session(retries=args.retries)
    schedule_data = get_schedule_from_page(
        args.train_number,
        session=session,
        timeout=args.timeout,
    )
    print(format_schedule_info(schedule_data))
    return 0


def _run_split(args: argparse.Namespace) -> int:
    session = create_session(retries=args.retries)
    split_data = find_same_train_split_journeys(
        train_number=args.train_number,
        from_station=args.from_station,
        to_station=args.to_station,
        journey_date=args.date,
        quota=args.quota,
        provider=args.provider,
        classes=args.classes,
        max_segments=args.max_segments,
        max_wl=args.max_wl,
        accept_rac=args.accept_rac,
        max_results=args.max_results,
        search_deeper=args.search_deeper,
        session=session,
        timeout=args.timeout,
    )
    print(format_split_journey_results(split_data))
    return 0


def _run_demo(args: argparse.Namespace) -> int:
    station_data = load_station_cache(args.cache)
    station_limit = getattr(args, "station_limit", DEFAULT_DEMO_STATION_LIMIT)
    stations = search_station_local(args.station_query, station_data, limit=station_limit)
    print(format_station_results(args.station_query, stations))

    session = create_session(retries=args.retries)
    train_data = get_trains_between_stations(
        args.from_station,
        args.to_station,
        args.date,
        quota=args.quota,
        provider=args.provider,
        session=session,
        timeout=args.timeout,
        use_fetch_availability=True,
    )
    print(format_train_info(train_data, args.date, quota=args.quota))

    schedule_data = get_schedule_from_page(
        args.schedule_train,
        session=session,
        timeout=args.timeout,
    )
    print(format_schedule_info(schedule_data))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None and len(sys.argv) == 1:
        argv = [DEFAULT_COMMAND]
    args = parser.parse_args(argv)

    try:
        if args.command in {"station", "stations", "search-station"}:
            return _run_station_search(args)
        if args.command == "trains":
            return _run_trains(args)
        if args.command == "schedule":
            return _run_schedule(args)
        if args.command in {"split", "split-journey"}:
            return _run_split(args)
        if args.command == "demo":
            return _run_demo(args)

        parser.error(f"Unknown command: {args.command}")
        return 2
    except (StationCacheError, RailwayApiError, SplitJourneyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
