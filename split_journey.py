from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
import re
from typing import Any, Callable, Mapping, Sequence

import requests

from railway_api import (
    get_ixigo_train_availability,
    get_schedule_from_page,
    get_trains_between_stations,
)


TrainSearchFunc = Callable[..., dict[str, Any]]


class SplitJourneyError(RuntimeError):
    """Raised when a split journey cannot be evaluated."""


@dataclass(frozen=True)
class RouteStop:
    index: int
    code: str
    name: str
    day: int
    arrival_minutes: int | None
    departure_minutes: int | None


@dataclass(frozen=True)
class Segment:
    from_stop: RouteStop
    to_stop: RouteStop
    journey_date: str


def parse_class_list(classes: str | Sequence[str] | None) -> list[str]:
    """Parse a comma-separated or repeated class preference list."""
    if not classes:
        return []

    values: Sequence[str]
    if isinstance(classes, str):
        values = classes.split(",")
    else:
        values = classes

    parsed: list[str] = []
    for value in values:
        for class_code in str(value).split(","):
            class_code = class_code.strip().upper()
            if class_code and class_code not in parsed:
                parsed.append(class_code)
    return parsed


def parse_availability_status(status: Any) -> dict[str, Any]:
    """Classify availability text from RailYatri/Ixigo into a sortable shape."""
    text = "" if status is None else str(status).strip()
    normalized = re.sub(r"\s+", " ", text).upper()

    if not normalized or normalized == "N/A":
        return {"status": text or "N/A", "kind": "unknown", "count": None, "rank": 90}

    if "REGRET" in normalized or "NOT AVAILABLE" in normalized or "NO MORE" in normalized:
        return {"status": text, "kind": "unavailable", "count": None, "rank": 80}

    if "AVAILABLE" in normalized or normalized.startswith("AVL"):
        count = _first_int(normalized)
        return {"status": text, "kind": "available", "count": count, "rank": 0}

    if "RAC" in normalized:
        count = _number_after_token(normalized, "RAC")
        return {"status": text, "kind": "rac", "count": count, "rank": 10}

    if "WL" in normalized:
        count = _last_wl_number(normalized)
        return {"status": text, "kind": "wl", "count": count, "rank": 20}

    return {"status": text, "kind": "unknown", "count": None, "rank": 90}


def is_acceptable_status(
    parsed_status: Mapping[str, Any],
    *,
    accept_rac: bool,
    max_wl: int,
) -> bool:
    kind = parsed_status.get("kind")
    count = parsed_status.get("count")

    if kind == "available":
        return True
    if kind == "rac":
        return accept_rac
    if kind == "wl":
        return isinstance(count, int) and count <= max_wl
    return False


def _first_int(text: str) -> int | None:
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def _number_after_token(text: str, token: str) -> int | None:
    match = re.search(rf"{re.escape(token)}\s*-?\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _last_wl_number(text: str) -> int | None:
    matches = re.findall(r"WL\s*-?\s*(\d+)", text)
    return int(matches[-1]) if matches else None


def extract_route_stops(schedule_data: Mapping[str, Any]) -> list[RouteStop]:
    """Return only scheduled stops from RailYatri timetable data."""
    stops: list[RouteStop] = []
    stop_index = 0

    for day_group in schedule_data.get("timeTableDaysGroup", []):
        if not isinstance(day_group, Mapping):
            continue
        for stop in day_group.get("items", []):
            if not isinstance(stop, Mapping) or not stop.get("stop"):
                continue

            code = _clean_text(stop.get("station_code")).upper()
            name = _clean_text(stop.get("station_name"))
            if not code:
                continue

            stop_index += 1
            stops.append(
                RouteStop(
                    index=stop_index,
                    code=code,
                    name=name,
                    day=_safe_int(stop.get("day"), default=1),
                    arrival_minutes=_optional_int(stop.get("sta_min")),
                    departure_minutes=_optional_int(stop.get("std_min")),
                )
            )

    return stops


def find_route_slice(
    stops: Sequence[RouteStop],
    from_station: str,
    to_station: str,
) -> list[RouteStop]:
    source = from_station.strip().upper()
    destination = to_station.strip().upper()

    source_index = _find_stop_index(stops, source)
    destination_index = _find_stop_index(stops, destination)
    if source_index is None:
        raise SplitJourneyError(f"Source station {source} is not a scheduled stop for this train.")
    if destination_index is None:
        raise SplitJourneyError(
            f"Destination station {destination} is not a scheduled stop for this train."
        )
    if source_index >= destination_index:
        raise SplitJourneyError(
            f"Destination station {destination} must appear after source station {source}."
        )

    return list(stops[source_index : destination_index + 1])


def _find_stop_index(stops: Sequence[RouteStop], code: str) -> int | None:
    for index, stop in enumerate(stops):
        if stop.code == code:
            return index
    return None


def generate_split_segments(
    route_stops: Sequence[RouteStop],
    journey_date: str,
    segment_count: int,
) -> list[list[Segment]]:
    """Generate consecutive route segments for a requested total segment count."""
    if segment_count < 1:
        raise ValueError("segment_count must be at least 1.")
    if len(route_stops) < 2:
        return []
    if segment_count > len(route_stops) - 1:
        return []

    source_day = route_stops[0].day
    split_index_options = range(1, len(route_stops) - 1)
    segment_groups: list[list[Segment]] = []

    for split_indices in combinations(split_index_options, segment_count - 1):
        boundary_indices = (0, *split_indices, len(route_stops) - 1)
        segments = []
        for start_index, end_index in zip(boundary_indices, boundary_indices[1:]):
            from_stop = route_stops[start_index]
            to_stop = route_stops[end_index]
            segments.append(
                Segment(
                    from_stop=from_stop,
                    to_stop=to_stop,
                    journey_date=_date_for_route_day(journey_date, source_day, from_stop.day),
                )
            )
        segment_groups.append(segments)

    return segment_groups


def find_same_train_split_journeys(
    *,
    train_number: str,
    from_station: str,
    to_station: str,
    journey_date: str,
    quota: str = "GN",
    provider: str = "ixigo",
    classes: str | Sequence[str] | None = None,
    max_segments: int = 3,
    max_wl: int = 20,
    accept_rac: bool = True,
    max_results: int = 10,
    search_deeper: bool = False,
    session: requests.Session | None = None,
    timeout: float = 20,
    schedule_data: Mapping[str, Any] | None = None,
    train_search_func: TrainSearchFunc = get_trains_between_stations,
) -> dict[str, Any]:
    """Find acceptable split journeys on the same train."""
    if max_segments < 2:
        raise ValueError("max_segments must be at least 2 for split journeys.")
    if max_results < 1:
        raise ValueError("max_results must be at least 1.")

    normalized_train_number = train_number.strip()
    preferred_classes = parse_class_list(classes)
    active_schedule = schedule_data or get_schedule_from_page(
        normalized_train_number,
        session=session,
        timeout=timeout,
    )
    all_stops = extract_route_stops(active_schedule)
    route_stops = find_route_slice(all_stops, from_station, to_station)

    segment_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    checked_combinations = 0

    for segment_count in range(2, max_segments + 1):
        found_at_this_depth = False
        for segments in generate_split_segments(route_stops, journey_date, segment_count):
            checked_combinations += 1
            segment_availability = [
                _get_segment_train_availability(
                    segment,
                    train_number=normalized_train_number,
                    quota=quota,
                    provider=provider,
                    session=session,
                    timeout=timeout,
                    train_search_func=train_search_func,
                    segment_cache=segment_cache,
                    preferred_classes=preferred_classes,
                )
                for segment in segments
            ]

            class_options = _ranked_class_options(segment_availability, preferred_classes)
            for class_code in class_options:
                evaluated = _evaluate_segments_for_class(
                    segment_availability,
                    class_code,
                    accept_rac=accept_rac,
                    max_wl=max_wl,
                )
                if not evaluated["acceptable"]:
                    continue

                result = {
                    "train_number": normalized_train_number,
                    "train_name": _first_train_name(segment_availability),
                    "class": class_code,
                    "quota": quota.strip().upper(),
                    "provider": provider,
                    "segments": evaluated["segments"],
                    "segment_count": len(segments),
                    "split_stations": [
                        {
                            "code": segment.from_stop.code,
                            "name": segment.from_stop.name,
                        }
                        for segment in segments[1:]
                    ],
                    "score": _result_score(
                        evaluated["segments"],
                        segment_count=len(segments),
                        class_code=class_code,
                        preferred_classes=preferred_classes,
                    ),
                }
                results.append(result)
                found_at_this_depth = True

            results.sort(key=lambda result: result["score"])
            if len(results) >= max_results:
                return _build_result_payload(
                    active_schedule,
                    route_stops,
                    results[:max_results],
                    checked_combinations,
                    segment_cache,
                    max_segments=max_segments,
                    max_wl=max_wl,
                    accept_rac=accept_rac,
                    preferred_classes=preferred_classes,
                )

        if found_at_this_depth and not search_deeper:
            break

    return _build_result_payload(
        active_schedule,
        route_stops,
        results[:max_results],
        checked_combinations,
        segment_cache,
        max_segments=max_segments,
        max_wl=max_wl,
        accept_rac=accept_rac,
        preferred_classes=preferred_classes,
    )


def _get_segment_train_availability(
    segment: Segment,
    *,
    train_number: str,
    quota: str,
    provider: str,
    session: requests.Session | None,
    timeout: float,
    train_search_func: TrainSearchFunc,
    segment_cache: dict[tuple[str, str, str], dict[str, Any]],
    preferred_classes: Sequence[str],
) -> dict[str, Any]:
    cache_key = (segment.from_stop.code, segment.to_stop.code, segment.journey_date)
    if cache_key in segment_cache:
        return segment_cache[cache_key]

    if (
        provider.strip().lower() == "ixigo"
        and train_search_func is get_trains_between_stations
        and preferred_classes
    ):
        train_data = get_ixigo_train_availability(
            train_number,
            preferred_classes,
            segment.from_stop.code,
            segment.to_stop.code,
            segment.journey_date,
            quota=quota,
            session=session,
            timeout=timeout,
        )
    else:
        train_data = train_search_func(
            segment.from_stop.code,
            segment.to_stop.code,
            segment.journey_date,
            quota=quota,
            provider=provider,
            session=session,
            timeout=timeout,
            use_fetch_availability=True,
        )
    train = _find_train(train_data.get("train_between_stations", []), train_number)
    availability = _extract_train_availability(train)

    result = {
        "from": {
            "code": segment.from_stop.code,
            "name": segment.from_stop.name,
            "day": segment.from_stop.day,
        },
        "to": {
            "code": segment.to_stop.code,
            "name": segment.to_stop.name,
            "day": segment.to_stop.day,
        },
        "journey_date": segment.journey_date,
        "train": train,
        "availability": availability,
    }
    segment_cache[cache_key] = result
    return result


def _find_train(trains: Any, train_number: str) -> Mapping[str, Any] | None:
    if not isinstance(trains, list):
        return None

    for train in trains:
        if not isinstance(train, Mapping):
            continue
        if str(train.get("train_number") or train.get("trainNumber")).strip() == train_number:
            return train
    return None


def _extract_train_availability(train: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not train:
        return {}

    availability_by_class: dict[str, dict[str, Any]] = {}
    for availability in train.get("sa_data", []):
        if not isinstance(availability, Mapping) or not availability.get("success"):
            continue
        class_code = _clean_text(availability.get("booking_class")).upper()
        seat_list = availability.get("seat_availibility")
        if not class_code or not isinstance(seat_list, list) or not seat_list:
            continue
        status_info = seat_list[0]
        if not isinstance(status_info, Mapping):
            continue

        status = (
            status_info.get(f"Class - {class_code}")
            or status_info.get("availability")
            or status_info.get("raw_availability")
            or "N/A"
        )
        parsed = parse_availability_status(status)
        availability_by_class[class_code] = {
            "class": class_code,
            "status": parsed["status"],
            "kind": parsed["kind"],
            "count": parsed["count"],
            "rank": parsed["rank"],
            "fare": status_info.get("total_fare", "N/A"),
            "prediction": status_info.get("prediction"),
            "raw_availability": status_info.get("raw_availability"),
        }

    return availability_by_class


def _ranked_class_options(
    segment_availability: Sequence[Mapping[str, Any]],
    preferred_classes: Sequence[str],
) -> list[str]:
    available_classes: set[str] = set()
    for segment in segment_availability:
        availability = segment.get("availability")
        if isinstance(availability, Mapping):
            available_classes.update(str(class_code) for class_code in availability)

    if preferred_classes:
        return [
            class_code
            for class_code in preferred_classes
            if class_code in available_classes
        ]
    return sorted(available_classes)


def _evaluate_segments_for_class(
    segment_availability: Sequence[Mapping[str, Any]],
    class_code: str,
    *,
    accept_rac: bool,
    max_wl: int,
) -> dict[str, Any]:
    evaluated_segments = []
    acceptable = True

    for segment in segment_availability:
        availability = segment.get("availability", {})
        class_status = availability.get(class_code) if isinstance(availability, Mapping) else None
        if not isinstance(class_status, Mapping):
            class_status = {
                "class": class_code,
                "status": "N/A",
                "kind": "unknown",
                "count": None,
                "rank": 90,
                "fare": "N/A",
                "prediction": None,
            }

        segment_ok = is_acceptable_status(
            class_status,
            accept_rac=accept_rac,
            max_wl=max_wl,
        )
        acceptable = acceptable and segment_ok
        evaluated_segments.append(
            {
                "from": segment["from"],
                "to": segment["to"],
                "journey_date": segment["journey_date"],
                "class": class_code,
                "status": class_status["status"],
                "kind": class_status["kind"],
                "count": class_status["count"],
                "rank": class_status["rank"],
                "fare": class_status["fare"],
                "prediction": class_status.get("prediction"),
                "acceptable": segment_ok,
            }
        )

    return {"acceptable": acceptable, "segments": evaluated_segments}


def _result_score(
    segments: Sequence[Mapping[str, Any]],
    *,
    segment_count: int,
    class_code: str,
    preferred_classes: Sequence[str],
) -> tuple[Any, ...]:
    class_rank = preferred_classes.index(class_code) if class_code in preferred_classes else 99
    worst_status_rank = max(_safe_int(segment.get("rank"), default=99) for segment in segments)
    total_wait_count = sum(
        _safe_int(segment.get("count"), default=0)
        for segment in segments
        if segment.get("kind") in {"rac", "wl"}
    )
    total_fare = sum(
        _safe_int(segment.get("fare"), default=0)
        for segment in segments
    )
    return (segment_count, class_rank, worst_status_rank, total_wait_count, total_fare)


def _build_result_payload(
    schedule_data: Mapping[str, Any],
    route_stops: Sequence[RouteStop],
    results: Sequence[Mapping[str, Any]],
    checked_combinations: int,
    segment_cache: Mapping[tuple[str, str, str], Mapping[str, Any]],
    *,
    max_segments: int,
    max_wl: int,
    accept_rac: bool,
    preferred_classes: Sequence[str],
) -> dict[str, Any]:
    return {
        "success": True,
        "train_number": str(schedule_data.get("train_number") or ""),
        "train_name": schedule_data.get("train_name", "N/A"),
        "from": {"code": route_stops[0].code, "name": route_stops[0].name},
        "to": {"code": route_stops[-1].code, "name": route_stops[-1].name},
        "route_stop_count": len(route_stops),
        "max_segments": max_segments,
        "max_wl": max_wl,
        "accept_rac": accept_rac,
        "preferred_classes": list(preferred_classes),
        "checked_combinations": checked_combinations,
        "checked_segments": len(segment_cache),
        "results": list(results),
    }


def _first_train_name(segment_availability: Sequence[Mapping[str, Any]]) -> str:
    for segment in segment_availability:
        train = segment.get("train")
        if isinstance(train, Mapping):
            train_name = train.get("train_name") or train.get("trainName")
            if train_name:
                return str(train_name)
    return "N/A"


def _date_for_route_day(journey_date: str, source_day: int, route_day: int) -> str:
    base_date = datetime.strptime(journey_date, "%d-%m-%Y")
    offset_days = route_day - source_day
    return (base_date + timedelta(days=offset_days)).strftime("%d-%m-%Y")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None