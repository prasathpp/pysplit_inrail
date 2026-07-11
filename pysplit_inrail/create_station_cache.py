import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT_FILE = Path(__file__).with_name("stations_endpoint.json")
DEFAULT_CACHE_FILE = Path(__file__).with_name("stations_cache.json")


def load_json_file(file_path: Path) -> Any:
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_json_url(url: str) -> Any:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def get_station_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        raise ValueError("Expected source JSON to contain an 'items' list.")

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    raise ValueError("Expected source JSON to be an object or a list.")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_station_cache(items: list[dict[str, Any]]) -> tuple[list[dict[str, str]], int, int]:
    stations_by_code: dict[str, dict[str, str]] = {}
    skipped = 0
    duplicates = 0

    for item in items:
        code = clean_text(item.get("station_code") or item.get("code")).upper()
        name = clean_text(item.get("station_name") or item.get("name"))

        if not code or not name:
            skipped += 1
            continue

        if code in stations_by_code:
            duplicates += 1
            continue

        stations_by_code[code] = {"code": code, "name": name}

    return list(stations_by_code.values()), skipped, duplicates


def write_station_cache(stations: list[dict[str, str]], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as file:
        json.dump(stations, file, indent=2, ensure_ascii=False)
        file.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create stations_cache.json for rail_scrapper.py."
    )
    parser.add_argument(
        "--endpoint-file",
        type=Path,
        default=DEFAULT_ENDPOINT_FILE,
        help="Raw station endpoint JSON file to read.",
    )
    parser.add_argument(
        "--source-url",
        help="Optional URL returning station endpoint JSON. Overrides --endpoint-file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_CACHE_FILE,
        help="Cache JSON file to write.",
    )
    parser.add_argument(
        "--sort",
        choices=("input", "code", "name"),
        default="input",
        help="Station order in the output cache.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without writing the output file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.source_url:
            payload = load_json_url(args.source_url)
            source_label = args.source_url
        else:
            payload = load_json_file(args.endpoint_file)
            source_label = str(args.endpoint_file)

        stations, skipped, duplicates = build_station_cache(get_station_items(payload))

        if args.sort == "code":
            stations.sort(key=lambda station: (station["code"], station["name"].casefold()))
        elif args.sort == "name":
            stations.sort(key=lambda station: (station["name"].casefold(), station["code"]))

        print(f"Source: {source_label}")
        print(f"Stations ready: {len(stations)}")
        print(f"Skipped invalid rows: {skipped}")
        print(f"Skipped duplicate codes: {duplicates}")

        if args.dry_run:
            print("Dry run only; no file was written.")
            return 0

        write_station_cache(stations, args.output)
        print(f"Wrote: {args.output}")
        return 0

    except FileNotFoundError:
        print(
            f"Error: source file not found: {args.endpoint_file}\n"
            "Keep stations_endpoint.json beside this script, or pass --source-url.",
            file=sys.stderr,
        )
        return 1
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Error: could not read station data: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
