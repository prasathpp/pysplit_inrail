import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_SOURCE_URL = "https://api.railyatri.in/api/common_city_station_search.json?q="
DEFAULT_OUTPUT_FILE = Path(__file__).with_name("stations_endpoint.json")


def fetch_station_endpoint(source_url: str, timeout: int) -> dict[str, Any]:
    request = Request(
        source_url,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Safari/537.36"
            ),
        },
    )

    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        payload = json.loads(response.read().decode(charset))

    if not isinstance(payload, dict):
        raise ValueError("Expected endpoint response to be a JSON object.")

    if payload.get("success") is not True:
        raise ValueError("Station endpoint did not return success=true.")

    if not isinstance(payload.get("items"), list):
        raise ValueError("Station endpoint response does not contain an items list.")

    return payload


def write_json(payload: dict[str, Any], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
        file.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download RailYatri station endpoint data into stations_endpoint.json."
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="RailYatri station endpoint URL to fetch.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="JSON file to write.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate the endpoint without writing the output file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        payload = fetch_station_endpoint(args.source_url, args.timeout)
        items = payload["items"]

        print(f"Source: {args.source_url}")
        print(f"Stations endpoint rows: {len(items)}")

        if args.dry_run:
            print("Dry run only; no file was written.")
            return 0

        write_json(payload, args.output)
        print(f"Wrote: {args.output}")
        return 0

    except HTTPError as exc:
        print(f"Error: HTTP {exc.code} while fetching station endpoint.", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Error: could not fetch station endpoint: {exc.reason}", file=sys.stderr)
        return 1
    except (TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(f"Error: could not read station endpoint data: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
