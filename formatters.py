from typing import Any, Mapping, Sequence


def minutes_to_hhmm(minutes: int | None) -> str:
    """Convert minutes from midnight to HH:MM."""
    if minutes is None:
        return "N/A"
    if minutes == 0:
        return "START"
    if minutes < 0:
        return "N/A"

    normalized_minutes = minutes % 1440
    hour = normalized_minutes // 60
    minute = normalized_minutes % 60
    return f"{hour:02d}:{minute:02d}"


def format_station_results(query: str, stations: Sequence[Mapping[str, Any]]) -> str:
    if not stations:
        return f"No stations found for '{query}'."

    lines = [f"Stations matching '{query}':"]
    for station in stations:
        lines.append(f"  - {station.get('name', 'N/A')} ({station.get('code', 'N/A')})")
    return "\n".join(lines)


def format_train_info(
    train_data: Mapping[str, Any] | None,
    journey_date: str,
    *,
    quota: str = "GN",
) -> str:
    """Format train search results for terminal output."""
    if not train_data or not train_data.get("success"):
        message = None
        if train_data:
            message = train_data.get("message") or train_data.get("error")
        return message or "Could not retrieve train information."

    trains = train_data.get("train_between_stations", [])
    if not trains:
        return f"No trains found between {train_data.get('from')} and {train_data.get('to')}."

    first_train = trains[0]
    lines = [
        "",
        (
            f"--- Trains from {first_train.get('from_station_name', 'N/A')} "
            f"to {first_train.get('to_station_name', 'N/A')} on {journey_date} ---"
        ),
    ]

    for train in trains:
        lines.extend(
            [
                "",
                "=" * 50,
                f"> {train.get('train_name', 'N/A')} ({train.get('train_number', 'N/A')})",
                (
                    f"   Departs: {train.get('from_std', 'N/A')} | "
                    f"Arrives: {train.get('to_sta', 'N/A')} | "
                    f"Duration: {train.get('duration', 'N/A')}"
                ),
                f"   Availability ({quota} Quota):",
            ]
        )

        availability_lines = []
        for availability in train.get("sa_data", []):
            if not availability.get("success") or not availability.get("seat_availibility"):
                continue

            status_info = availability["seat_availibility"][0]
            class_code = availability.get("booking_class", "N/A")
            status = status_info.get(f"Class - {class_code}", "N/A")
            fare = status_info.get("total_fare", "N/A")
            details = [f"Rs. {fare}"]
            prediction = status_info.get("prediction")
            if prediction and prediction not in {status, "Available"}:
                details.append(str(prediction))
            availability_lines.append(f"     - {class_code}: {status} ({', '.join(details)})")

        lines.extend(availability_lines or ["     - No availability data returned."])

    lines.append("=" * 50)
    return "\n".join(lines)


def format_schedule_info(schedule_data: Mapping[str, Any] | None) -> str:
    """Format a train schedule for terminal output."""
    if not schedule_data or "timeTableDaysGroup" not in schedule_data:
        return "Schedule data is empty or invalid."

    lines = [
        "",
        "=" * 80,
        (
            f"SCHEDULE FOR: {schedule_data.get('train_name', 'N/A')} "
            f"({schedule_data.get('train_number', 'N/A')})"
        ),
        f"Runs On: {' '.join(schedule_data.get('run_days', []))}",
        "=" * 80,
        f"{'#':<4} {'Station Name':<30} {'Code':<6} {'Arrival':<10} {'Departure':<10} {'Day':<4}",
        f"{'-' * 4} {'-' * 30} {'-' * 6} {'-' * 10} {'-' * 10} {'-' * 4}",
    ]

    stop_count = 1
    for day_group in schedule_data.get("timeTableDaysGroup", []):
        for stop in day_group.get("items", []):
            if not stop.get("stop"):
                continue

            arrival_minutes = stop.get("sta_min")
            departure_minutes = stop.get("std_min")
            arrival = minutes_to_hhmm(arrival_minutes) if arrival_minutes else "START"
            departure = minutes_to_hhmm(departure_minutes) if departure_minutes else "END"

            lines.append(
                f"{stop_count:<4} "
                f"{stop.get('station_name', 'N/A'):<30} "
                f"{stop.get('station_code', 'N/A'):<6} "
                f"{arrival:<10} "
                f"{departure:<10} "
                f"{stop.get('day', 'N/A'):<4}"
            )
            stop_count += 1

    lines.append("=" * 80)
    return "\n".join(lines)



def format_split_journey_results(split_data: Mapping[str, Any] | None) -> str:
    """Format same-train split journey options for terminal output."""
    if not split_data or not split_data.get("success"):
        return "Could not evaluate split journey options."

    header = (
        f"Split journey options for {split_data.get('train_name', 'N/A')} "
        f"({split_data.get('train_number', 'N/A')})"
    )
    route = (
        f"{split_data.get('from', {}).get('name', 'N/A')} "
        f"({split_data.get('from', {}).get('code', 'N/A')}) -> "
        f"{split_data.get('to', {}).get('name', 'N/A')} "
        f"({split_data.get('to', {}).get('code', 'N/A')})"
    )
    policy = (
        f"Accepting: AVAILABLE"
        f"{' + RAC' if split_data.get('accept_rac') else ''}"
        f" + WL<={split_data.get('max_wl')}"
    )
    lines = [
        "",
        "=" * 90,
        header,
        route,
        policy,
        (
            f"Checked {split_data.get('checked_combinations', 0)} combinations "
            f"using {split_data.get('checked_segments', 0)} segment lookups."
        ),
        "=" * 90,
    ]

    results = split_data.get("results", [])
    if not results:
        lines.extend(
            [
                "No acceptable same-train split found with the current rules.",
                "Try increasing --max-segments, raising --max-wl, or changing --classes.",
                "=" * 90,
            ]
        )
        return "\n".join(lines)

    for index, result in enumerate(results, start=1):
        split_codes = " -> ".join(
            station.get("code", "N/A") for station in result.get("split_stations", [])
        )
        split_text = f" via {split_codes}" if split_codes else ""
        total_fare = _sum_segment_fares(result.get("segments", []))
        fare_text = f" | Total fare: Rs. {total_fare}" if total_fare else ""

        lines.extend(
            [
                "",
                f"{index}. Class {result.get('class', 'N/A')} | "
                f"{result.get('segment_count', 'N/A')} segments{split_text}{fare_text}",
            ]
        )

        for segment in result.get("segments", []):
            details = [f"Rs. {segment.get('fare')}"] if segment.get("fare") not in {None, "N/A"} else []
            prediction = segment.get("prediction")
            if prediction and prediction not in {segment.get("status"), "Available"}:
                details.append(str(prediction))
            suffix = f" ({', '.join(details)})" if details else ""
            lines.append(
                "   - "
                f"{segment.get('from', {}).get('code', 'N/A')}"
                f" -> {segment.get('to', {}).get('code', 'N/A')}"
                f" on {segment.get('journey_date', 'N/A')}: "
                f"{segment.get('status', 'N/A')}{suffix}"
            )

    lines.append("=" * 90)
    return "\n".join(lines)


def _sum_segment_fares(segments: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for segment in segments:
        try:
            total += int(segment.get("fare"))
        except (TypeError, ValueError):
            continue
    return total