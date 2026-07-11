import json
import re
from datetime import datetime
from typing import Any, Mapping, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


RAILYATRI_TRAIN_SEARCH_URL = "https://trainticketapi.railyatri.in/api/trains-between-station-with-sa.json"
IXIGO_TRAIN_SEARCH_URL = "https://ixigotrainsapi.confirmtkt.com/api/v1/trains/search"
IXIGO_FETCH_AVAILABILITY_URL = (
    "https://ixigotrainsapi.confirmtkt.com/api/v1/availability/fetchAvailability"
)
TIMETABLE_URL = "https://www.railyatri.in/time-table/{train_number}"
SUPPORTED_TRAIN_SEARCH_PROVIDERS = ("ixigo", "railyatri")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}


class RailwayApiError(RuntimeError):
    """Raised when a railway API request or response cannot be processed."""


def create_session(retries: int = 2, backoff_factor: float = 0.4) -> requests.Session:
    """Create a requests session with conservative retry behavior."""
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        backoff_factor=backoff_factor,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def validate_journey_date(journey_date: str) -> str:
    """Validate the expected DD-MM-YYYY journey date format."""
    try:
        datetime.strptime(journey_date, "%d-%m-%Y")
    except ValueError as exc:
        raise ValueError("Journey date must be in DD-MM-YYYY format.") from exc
    return journey_date


def _request_get(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 20,
) -> requests.Response:
    try:
        response = session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as exc:
        raise RailwayApiError(f"Request failed for {url}: {exc}") from exc


def _request_post(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: Any | None = None,
    timeout: float = 20,
) -> requests.Response:
    try:
        # Some ixigo endpoints expect POST with query params and empty body.
        response = session.post(url, params=params, json=data, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as exc:
        raise RailwayApiError(f"Request failed for {url}: {exc}") from exc


def _format_duration(duration_minutes: Any) -> str:
    if not isinstance(duration_minutes, int):
        return "N/A"

    hours = duration_minutes // 60
    minutes = duration_minutes % 60
    return f"{hours}:{minutes:02d}"


def _non_empty_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping) and value:
        return value
    return {}


def _normalize_ixigo_train_search(
    payload: Mapping[str, Any],
    *,
    from_station: str,
    to_station: str,
    journey_date: str,
    quota: str,
) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        message = payload.get("errorMessage") or payload.get("message")
        return {
            "success": False,
            "provider": "ixigo",
            "message": message or "Ixigo train search response did not contain data.",
        }

    error_code = data.get("errorCode")
    if error_code not in (None, 0):
        return {
            "success": False,
            "provider": "ixigo",
            "message": data.get("errorMessage") or f"Ixigo returned error code {error_code}.",
        }

    trains = data.get("trainList", [])
    if not isinstance(trains, list):
        raise RailwayApiError("Ixigo train search response did not contain a train list.")

    normalized_trains = []
    for train in trains:
        if not isinstance(train, Mapping):
            continue

        availability_cache = _non_empty_mapping(train.get("availabilityCacheForQuota"))
        if not availability_cache:
            availability_cache = _non_empty_mapping(train.get("availabilityCache"))

        class_order = train.get("avlClassesSorted") or train.get("avlClasses") or list(availability_cache)
        if not isinstance(class_order, list):
            class_order = list(availability_cache)

        sa_data = []
        for class_code in class_order:
            availability = availability_cache.get(class_code)
            if not isinstance(availability, Mapping):
                continue

            display_status = (
                availability.get("availabilityDisplayName")
                or availability.get("availability")
                or "N/A"
            )
            prediction = availability.get("predictionDisplayName") or availability.get("prediction")
            seat_status = {
                f"Class - {class_code}": display_status,
                "total_fare": availability.get("fare", "N/A"),
                "raw_availability": availability.get("availability"),
                "prediction": prediction,
                "cache_time": availability.get("cacheTime"),
                "quota": availability.get("quota") or quota,
            }
            sa_data.append(
                {
                    "success": True,
                    "booking_class": class_code,
                    "seat_availibility": [seat_status],
                }
            )

        normalized_trains.append(
            {
                "train_name": train.get("trainName", "N/A"),
                "train_number": train.get("trainNumber", "N/A"),
                "from_station_name": train.get("fromStnName", "N/A"),
                "to_station_name": train.get("toStnName", "N/A"),
                "from_std": train.get("departureTime", "N/A"),
                "to_sta": train.get("arrivalTime", "N/A"),
                "duration": _format_duration(train.get("duration")),
                "sa_data": sa_data,
            }
        )

    return {
        "success": True,
        "provider": "ixigo",
        "from": from_station,
        "to": to_station,
        "journey_date": journey_date,
        "quota": quota,
        "train_between_stations": normalized_trains,
    }


def _get_ixigo_trains_between_stations(
    from_station: str,
    to_station: str,
    journey_date: str,
    *,
    quota: str = "GN",
    session: requests.Session | None = None,
    timeout: float = 20,
    use_fetch_availability: bool = False,
) -> dict[str, Any]:
    """Fetch and normalize train availability from ixigo/ConfirmTkt."""
    source = from_station.strip().upper()
    destination = to_station.strip().upper()
    quota_code = quota.strip().upper()
    params = {
        "sourceStationCode": source,
        "destinationStationCode": destination,
        "addAvailabilityCache": "true",
        "excludeMultiTicketAlternates": "false",
        "excludeBoostAlternates": "false",
        "sortBy": "DEFAULT",
        "dateOfJourney": journey_date,
        "enableNearby": "true",
        "enableTG": "true",
        "tGPlan": "ITG-A50",
        "showTGPrediction": "false",
        "tgColor": "DEFAULT",
        "showPredictionGlobal": "true",
        "showNewAlternates": "true",
        "showNewAltText": "true",
        "quota": quota_code,
    }

    active_session = session or create_session()
    response = _request_get(
        active_session,
        IXIGO_TRAIN_SEARCH_URL,
        params=params,
        timeout=timeout,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RailwayApiError("Ixigo train search response was not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise RailwayApiError("Ixigo train search response was not a JSON object.")

    # Optionally replace per-class availability using fetchAvailability
    if use_fetch_availability:
        try:
            data = payload.get("data") or {}
            trains = data.get("trainList") or []
            if isinstance(trains, list):
                for train in trains:
                    if not isinstance(train, Mapping):
                        continue
                    train_no = train.get("trainNumber") or train.get("trainNo")
                    if not train_no:
                        continue

                    # availability caches can be in different keys
                    availability_cache = _non_empty_mapping(train.get("availabilityCacheForQuota"))
                    if not availability_cache:
                        availability_cache = _non_empty_mapping(train.get("availabilityCache"))

                    class_order = train.get("avlClassesSorted") or train.get("avlClasses") or list(availability_cache)
                    if not isinstance(class_order, list):
                        class_order = list(availability_cache)

                    for class_code in class_order:
                        if not isinstance(class_code, str):
                            continue
                        try:
                            fetch_payload = _get_ixigo_fetch_availability(
                                str(train_no),
                                class_code,
                                source,
                                destination,
                                journey_date,
                                quota=quota_code,
                                session=active_session,
                                timeout=timeout,
                            )
                        except RailwayApiError:
                            fetch_payload = {}

                        normalized_avl = _normalize_ixigo_fetch_availability(
                            fetch_payload, journey_date=journey_date, quota=quota_code
                        )
                        if normalized_avl:
                            # set/replace availability info for this class
                            if not isinstance(availability_cache, dict):
                                availability_cache = {}
                            availability_cache[class_code] = normalized_avl

                    # ensure the train has availabilityCache set so the existing normalizer can pick it up
                    if availability_cache:
                        train["availabilityCacheForQuota"] = availability_cache
        except Exception:
            # non-fatal: if fetch loop fails, fall back to original search payload
            pass

    return _normalize_ixigo_train_search(
        payload,
        from_station=source,
        to_station=destination,
        journey_date=journey_date,
        quota=quota_code,
    )


def _parse_travel_classes(travel_classes: str | Sequence[str] | None) -> list[str]:
    if travel_classes is None:
        return []
    if isinstance(travel_classes, str):
        values = travel_classes.split(",")
    else:
        values = travel_classes

    parsed: list[str] = []
    for value in values:
        class_code = str(value).strip().upper()
        if class_code and class_code not in parsed:
            parsed.append(class_code)
    return parsed


def _normalize_ixigo_fetch_availability(
    payload: Mapping[str, Any], *, journey_date: str, quota: str | None = None
) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return {}

    # avlDayList contains availability entries per date
    avl_list = data.get("avlDayList") or []
    # find entry for journey_date (flexible parsing)
    def _date_matches(avl_date: str, target: str) -> bool:
        try:
            d1 = datetime.strptime(avl_date.replace(" ", ""), "%d-%m-%Y")
        except Exception:
            try:
                d1 = datetime.strptime(avl_date, "%d-%m-%Y")
            except Exception:
                # try single-digit month/day formats like '31-7-2026'
                parts = avl_date.split("-")
                if len(parts) != 3:
                    return False
                day, month, year = parts
                try:
                    d1 = datetime(int(year), int(month), int(day))
                except Exception:
                    return False

        try:
            d2 = datetime.strptime(journey_date, "%d-%m-%Y")
        except Exception:
            return False
        return d1.date() == d2.date()

    chosen = None
    for entry in avl_list:
        if not isinstance(entry, Mapping):
            continue
        avl_date = entry.get("availablityDate") or entry.get("availabilityDate")
        if not avl_date:
            continue
        if _date_matches(avl_date, journey_date):
            chosen = entry
            break

    if not chosen and avl_list:
        # fallback to first
        chosen = avl_list[0]

    if not isinstance(chosen, Mapping):
        return {}

    normalized = {
        "availabilityDisplayName": chosen.get("availabilityDisplayName") or chosen.get("availability") or "N/A",
        "availability": chosen.get("availablityStatus") or chosen.get("availability") or chosen.get("availablityStatus"),
        "predictionDisplayName": chosen.get("predictionDisplayName") or chosen.get("prediction"),
        "prediction": chosen.get("prediction"),
        "fare": data.get("fare"),
        "cacheTime": data.get("timeStamp") or data.get("cacheTime"),
        "quota": quota or data.get("quota"),
        "raw": data,
    }
    return normalized


def _get_ixigo_fetch_availability(
    train_no: str,
    travel_class: str,
    from_station: str,
    to_station: str,
    journey_date: str,
    *,
    quota: str = "GN",
    session: requests.Session | None = None,
    timeout: float = 20,
) -> dict[str, Any]:
    active_session = session or create_session()
    params = {
        "trainNo": train_no.strip(),
        "travelClass": travel_class.strip(),
        "quota": quota.strip().upper(),
        "sourceStationCode": from_station.strip().upper(),
        "destinationStationCode": to_station.strip().upper(),
        "dateOfJourney": journey_date,
        "enableTG": "true",
        "tGPlan": "ITG-A50",
        "showTGPrediction": "false",
        "tgColor": "DEFAULT",
        "showPredictionGlobal": "true",
    }

    response = _request_post(active_session, IXIGO_FETCH_AVAILABILITY_URL, params=params, timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return payload



def get_ixigo_train_availability(
    train_no: str,
    travel_classes: str | Sequence[str] | None,
    from_station: str,
    to_station: str,
    journey_date: str,
    *,
    quota: str = "GN",
    session: requests.Session | None = None,
    timeout: float = 20,
) -> dict[str, Any]:
    class_codes = _parse_travel_classes(travel_classes)
    if not class_codes:
        raise ValueError("At least one travel class must be provided.")

    active_session = session or create_session()
    data: Mapping[str, Any] = {}
    try:
        payload = _get_ixigo_fetch_availability(
            train_no,
            class_codes[0],
            from_station,
            to_station,
            journey_date,
            quota=quota,
            session=active_session,
            timeout=timeout,
        )
        if isinstance(payload, Mapping):
            data = payload.get("data") or {}
    except RailwayApiError:
        data = {}

    train_name = str(data.get("trainName") or data.get("train_name") or "N/A")
    sa_data: list[dict[str, Any]] = []

    for class_code in class_codes:
        try:
            payload = _get_ixigo_fetch_availability(
                train_no,
                class_code,
                from_station,
                to_station,
                journey_date,
                quota=quota,
                session=active_session,
                timeout=timeout,
            )
        except RailwayApiError:
            continue
        normalized = _normalize_ixigo_fetch_availability(
            payload,
            journey_date=journey_date,
            quota=quota,
        )
        if not normalized:
            continue
        sa_data.append(
            {
                "success": True,
                "booking_class": class_code,
                "seat_availibility": [
                    {
                        f"Class - {class_code}": normalized.get("availabilityDisplayName") or "N/A",
                        "total_fare": normalized.get("fare", "N/A"),
                        "raw_availability": normalized.get("availability"),
                        "prediction": normalized.get("prediction"),
                    }
                ],
            }
        )

    return {
        "success": True,
        "provider": "ixigo",
        "from": from_station,
        "to": to_station,
        "journey_date": journey_date,
        "quota": quota,
        "train_between_stations": [
            {
                "train_name": train_name,
                "train_number": train_no,
                "sa_data": sa_data,
            }
        ],
    }


def _get_railyatri_trains_between_stations(
    from_station: str,
    to_station: str,
    journey_date: str,
    *,
    quota: str = "GN",
    session: requests.Session | None = None,
    timeout: float = 20,
) -> dict[str, Any]:
    """Fetch train list, availability, and fares between two stations from RailYatri."""
    validate_journey_date(journey_date)
    active_session = session or create_session()
    params = {
        "from": from_station.strip().upper(),
        "to": to_station.strip().upper(),
        "dateOfJourney": journey_date,
        "journey_quota": quota.strip().upper(),
    }

    response = _request_get(active_session, RAILYATRI_TRAIN_SEARCH_URL, params=params, timeout=timeout)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RailwayApiError("Train search response was not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise RailwayApiError("Train search response was not a JSON object.")
    payload.setdefault("provider", "railyatri")
    return payload


def get_trains_between_stations(
    from_station: str,
    to_station: str,
    journey_date: str,
    *,
    quota: str = "GN",
    provider: str = "ixigo",
    session: requests.Session | None = None,
    timeout: float = 20,
    use_fetch_availability: bool = False,
) -> dict[str, Any]:
    """Fetch train list, availability, and fares between two stations."""
    validate_journey_date(journey_date)
    provider_key = provider.strip().lower()
    if provider_key == "ixigo":
        return _get_ixigo_trains_between_stations(
            from_station,
            to_station,
            journey_date,
            quota=quota,
            session=session,
            timeout=timeout,
            use_fetch_availability=use_fetch_availability,
        )
    if provider_key == "railyatri":
        return _get_railyatri_trains_between_stations(
            from_station,
            to_station,
            journey_date,
            quota=quota,
            session=session,
            timeout=timeout,
        )

    supported = ", ".join(SUPPORTED_TRAIN_SEARCH_PROVIDERS)
    raise ValueError(f"Train search provider must be one of: {supported}.")


def extract_schedule_from_html(html_content: str) -> dict[str, Any]:
    """Extract RailYatri's embedded trainTimeTable JSON from a timetable page."""
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html_content,
        re.DOTALL,
    )
    if not match:
        raise RailwayApiError("Could not find embedded schedule data on the page.")

    try:
        page_data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise RailwayApiError("Failed to parse embedded schedule JSON.") from exc

    schedule_data = (
        page_data.get("props", {})
        .get("pageProps", {})
        .get("trainTimeTable", {})
    )
    if not isinstance(schedule_data, dict) or not schedule_data:
        raise RailwayApiError("Schedule data was empty or missing from the page.")
    return schedule_data


def get_schedule_from_page(
    train_number: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 20,
) -> dict[str, Any]:
    """Fetch a train schedule by scraping the embedded JSON from RailYatri."""
    train_number = train_number.strip()
    if not train_number.isdigit():
        raise ValueError("Train number must contain digits only.")

    active_session = session or create_session()
    response = _request_get(
        active_session,
        TIMETABLE_URL.format(train_number=train_number),
        timeout=timeout,
    )
    return extract_schedule_from_html(response.text)
