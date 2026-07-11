import json
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_STATION_CACHE = Path(__file__).parent.parent / "stations_cache.json"


class StationCacheError(RuntimeError):
    """Raised when the local station cache cannot be loaded."""


def load_station_cache(file_path: str | Path = DEFAULT_STATION_CACHE) -> list[dict[str, Any]]:
    """Load station data from the local cache JSON file."""
    path = Path(file_path)

    try:
        with path.open("r", encoding="utf-8") as file:
            station_data = json.load(file)
    except FileNotFoundError as exc:
        raise StationCacheError(
            f"Station cache not found: {path}. Run create_station_cache.py first."
        ) from exc
    except json.JSONDecodeError as exc:
        raise StationCacheError(f"Could not decode station cache JSON: {path}") from exc

    if not isinstance(station_data, list):
        raise StationCacheError(f"Station cache must contain a JSON list: {path}")

    return [station for station in station_data if isinstance(station, dict)]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def search_station_local(
    query: str,
    station_data: Iterable[Mapping[str, Any]],
    limit: int | None = None,
) -> list[dict[str, str]]:
    """Search the local station cache by station name or station code."""
    normalized_query = _clean_text(query).casefold()
    if not normalized_query:
        return []

    matches: list[tuple[int, int, dict[str, str]]] = []
    for index, station in enumerate(station_data):
        code = _clean_text(station.get("code") or station.get("station_code")).upper()
        name = _clean_text(station.get("name") or station.get("station_name"))
        if not code or not name:
            continue

        code_search = code.casefold()
        name_search = name.casefold()

        if normalized_query == code_search:
            score = 0
        elif code_search.startswith(normalized_query):
            score = 1
        elif normalized_query in name_search:
            score = 2
        else:
            continue

        matches.append((score, index, {"code": code, "name": name}))

    matches.sort(key=lambda match: (match[0], match[1]))
    stations = [station for _, _, station in matches]
    if limit is not None:
        return stations[:limit]
    return stations
