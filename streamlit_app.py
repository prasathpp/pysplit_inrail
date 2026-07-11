from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


def _running_in_streamlit() -> bool:
    try:
        from streamlit.runtime import exists
        return exists()
    except Exception:
        return False


def _launch_with_streamlit_if_needed() -> None:
    if __name__ != "__main__" or _running_in_streamlit():
        return

    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(Path(__file__).resolve()),
    ]
    cmd.extend(sys.argv[1:])
    raise SystemExit(subprocess.call(cmd))


_launch_with_streamlit_if_needed()

import pandas as pd
import streamlit as st

from rail_scrapper import (
    DEFAULT_CACHE_FILE,
    DEFAULT_FROM_STATION,
    DEFAULT_JOURNEY_DATE,
    DEFAULT_QUOTA,
    DEFAULT_RETRIES,
    DEFAULT_SCHEDULE_TRAIN,
    DEFAULT_SPLIT_ACCEPT_RAC,
    DEFAULT_SPLIT_CLASSES,
    DEFAULT_SPLIT_MAX_RESULTS,
    DEFAULT_SPLIT_MAX_SEGMENTS,
    DEFAULT_SPLIT_MAX_WL,
    DEFAULT_SPLIT_SEARCH_DEEPER,
    DEFAULT_SPLIT_TRAIN,
    DEFAULT_STATION_LIMIT,
    DEFAULT_STATION_QUERY,
    DEFAULT_TIMEOUT,
    DEFAULT_TO_STATION,
    DEFAULT_TRAIN_PROVIDER,
)
from pyinrail.railway_api import (
    RailwayApiError,
    SUPPORTED_TRAIN_SEARCH_PROVIDERS,
    create_session,
    get_schedule_from_page,
    get_trains_between_stations,
)
from pyinrail.split_journey import (
    SplitJourneyError,
    extract_route_stops,
    find_route_slice,
    find_same_train_split_journeys,
    parse_availability_status,
    parse_class_list,
)
from pyinrail.stations import StationCacheError, load_station_cache, search_station_local


APP_TITLE = "Rail Split Journey"
CLASS_OPTIONS = ["SL", "3A", "2A", "1A", "3E", "CC", "EC", "2S", "FC", "EA"]
QUOTA_LABELS = {
    "GN": "General",
    "TQ": "Tatkal",
    "PT": "Premium Tatkal",
    "LD": "Ladies",
    "SS": "Lower Berth",
    "HP": "Physically Handicapped",
    "DF": "Defence",
}
QUOTA_OPTIONS = list(QUOTA_LABELS)
MAX_SEGMENT_LIMIT = 8
MAX_RESULTS_LIMIT = 100
SCHEDULE_CACHE_TTL_SECONDS = 6 * 60 * 60


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🚄",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    inject_css()
    initialize_session_state()

    settings = render_sidebar()
    
    st.title("🚄 Rail Split Journey Pro")
    st.markdown("Optimize your railway bookings by finding intelligent split tickets and hidden availabilities.")
    st.write("")

    tabs = st.tabs(["🛤️ Split Journey", "🚆 Direct Trains", "📅 Schedule", "🚉 Stations"])

    with tabs[0]:
        render_split_tab(settings)
    with tabs[1]:
        render_direct_trains_tab(settings)
    with tabs[2]:
        render_schedule_tab(settings)
    with tabs[3]:
        render_station_tab(settings)


def initialize_session_state() -> None:
    defaults = {
        "split_result": None,
        "split_route_rows": [],
        "split_params": None,
        "direct_train_result": None,
        "direct_train_params": None,
        "schedule_result": None,
        "schedule_params": None,
        "station_result": None,
        "station_params": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def render_sidebar() -> dict[str, Any]:
    with st.sidebar:
        st.header("⚙️ Preferences")
        
        provider = st.selectbox(
            "Search Provider",
            options=list(SUPPORTED_TRAIN_SEARCH_PROVIDERS),
            index=safe_index(SUPPORTED_TRAIN_SEARCH_PROVIDERS, DEFAULT_TRAIN_PROVIDER),
            format_func=lambda value: value.title(),
            help="Select the backend API to query for trains."
        )
        quota = st.selectbox(
            "Booking Quota",
            options=QUOTA_OPTIONS,
            index=safe_index(QUOTA_OPTIONS, DEFAULT_QUOTA),
            format_func=lambda code: f"{code} - {QUOTA_LABELS.get(code, code)}",
        )

        st.markdown("---")
        with st.expander("🔧 Network & System", expanded=False):
            cols = st.columns(2)
            timeout = int(
                cols[0].number_input(
                    "Timeout (s)",
                    min_value=5,
                    max_value=120,
                    value=int(DEFAULT_TIMEOUT),
                    step=5,
                )
            )
            retries = int(
                cols[1].number_input(
                    "Retries",
                    min_value=0,
                    max_value=5,
                    value=int(DEFAULT_RETRIES),
                )
            )

            cache_path = st.text_input("Station Cache Path", value=str(DEFAULT_CACHE_FILE))
            show_raw = st.toggle("Show Raw JSON Outputs", value=False)
            
            try:
                station_count = len(load_station_cache_cached(cache_path))
                st.caption(f"✅ {station_count:,} stations loaded")
            except StationCacheError as exc:
                st.caption(f"❌ Error: {str(exc)}")

    return {
        "provider": provider,
        "quota": quota,
        "timeout": timeout,
        "retries": retries,
        "cache_path": cache_path,
        "show_raw": show_raw,
    }


def render_split_tab(settings: Mapping[str, Any]) -> None:
    # Custom CSS injected inside the tab to vertically align toggles with number inputs
    st.markdown(
        """
        <style>
        /* Target the specific controls row and align items vertically to the bottom/center */
        div[data-testid="stForm"] div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMarkdownContainer"]) {
            align-items: flex-end;
        }
        /* Alternative robust targeting for the container layout */
        div.element-container:has(div.stToggle) {
            margin-bottom: 10px; /* Adjusts the alignment to sit evenly with the number input fields */
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    with st.form("split_form", clear_on_submit=False):
        st.subheader("Journey Details")
        route_cols = st.columns([1.2, 1, 1, 1.5])
        
        train_number = route_cols[0].text_input(
            "Train Number",
            value=DEFAULT_SPLIT_TRAIN,
            max_chars=8,
            placeholder="e.g. 16021"
        )
        from_station = route_cols[1].text_input(
            "From (Code)",
            value=DEFAULT_FROM_STATION,
            max_chars=6,
            placeholder="MAS"
        )
        to_station = route_cols[2].text_input(
            "To (Code)",
            value=DEFAULT_TO_STATION,
            max_chars=6,
            placeholder="MYS"
        )
        journey_day = route_cols[3].date_input(
            "Journey Date",
            value=parse_default_date(DEFAULT_JOURNEY_DATE),
            format="DD-MM-YYYY",
        )

        selected_classes = st.multiselect(
            "Class Priority (in order of preference)",
            options=CLASS_OPTIONS,
            default=default_classes(DEFAULT_SPLIT_CLASSES),
        )

        # Advanced search controls shown inline
        controls = st.columns([1, 1, 1, 1.5, 1.5])
        max_segments = int(
            controls[0].number_input(
                "Max Segments",
                min_value=2,
                max_value=MAX_SEGMENT_LIMIT,
                value=int(DEFAULT_SPLIT_MAX_SEGMENTS),
            )
        )
        max_wl = int(
            controls[1].number_input(
                "Max WL limit",
                min_value=0,
                max_value=500,
                value=int(DEFAULT_SPLIT_MAX_WL),
            )
        )
        max_results = int(
            controls[2].number_input(
                "Max Results",
                min_value=1,
                max_value=MAX_RESULTS_LIMIT,
                value=int(DEFAULT_SPLIT_MAX_RESULTS),
            )
        )

        toggle_controls = st.columns([1.5, 1.5, 1, 1, 1])
        # Removed the manual <br> spacer completely so they don't get pushed down
        accept_rac = toggle_controls[0].toggle("Accept RAC as Available", value=DEFAULT_SPLIT_ACCEPT_RAC)
        search_deeper = toggle_controls[1].toggle("Search Deeper Configurations", value=DEFAULT_SPLIT_SEARCH_DEEPER)

        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        submitted = col2.form_submit_button("🔍 Find Optimal Split Options", type="primary", width='stretch')

    if submitted:
        run_split_search(
            train_number=train_number,
            from_station=from_station,
            to_station=to_station,
            journey_day=journey_day,
            selected_classes=selected_classes,
            max_segments=max_segments,
            max_wl=max_wl,
            max_results=max_results,
            accept_rac=accept_rac,
            search_deeper=search_deeper,
            settings=settings,
        )

    st.divider()
    split_result = st.session_state.get("split_result")
    if split_result:
        render_split_results(
            split_result,
            st.session_state.get("split_route_rows") or [],
            st.session_state.get("split_params") or {},
            show_raw=bool(settings["show_raw"]),
        )
    else:
        st.info("👋 Enter your journey details above and hit search to find split tickets.")


def run_split_search(
    *,
    train_number: str,
    from_station: str,
    to_station: str,
    journey_day: date,
    selected_classes: Sequence[str],
    max_segments: int,
    max_wl: int,
    max_results: int,
    accept_rac: bool,
    search_deeper: bool,
    settings: Mapping[str, Any],
) -> None:
    try:
        normalized_train = validate_train_number(train_number)
        normalized_from, normalized_to = validate_route(from_station, to_station)
        journey_date = date_to_api(journey_day)
        class_codes = normalize_classes(selected_classes)

        session = create_session(retries=int(settings["retries"]))
        with st.status("Analyzing route and checking availability...", expanded=True) as status:
            st.write(f"📥 Loading timetable for train {normalized_train}...")
            schedule_data = fetch_schedule_cached(
                normalized_train,
                int(settings["timeout"]),
                int(settings["retries"]),
            )
            route_rows = route_rows_for_schedule(schedule_data, normalized_from, normalized_to)

            st.write("🔄 Checking segment availability and permutations...")
            split_data = find_same_train_split_journeys(
                train_number=normalized_train,
                from_station=normalized_from,
                to_station=normalized_to,
                journey_date=journey_date,
                quota=str(settings["quota"]),
                provider=str(settings["provider"]),
                classes=",".join(class_codes) if class_codes else None,
                max_segments=max_segments,
                max_wl=max_wl,
                accept_rac=accept_rac,
                max_results=max_results,
                search_deeper=search_deeper,
                session=session,
                timeout=float(settings["timeout"]),
                schedule_data=schedule_data,
            )
            status.update(label="✅ Split search completed successfully", state="complete")

        st.session_state["split_result"] = split_data
        st.session_state["split_route_rows"] = route_rows
        st.session_state["split_params"] = {
            "train": normalized_train,
            "from": normalized_from,
            "to": normalized_to,
            "date": journey_date,
            "classes": class_codes or ["All returned classes"],
            "quota": settings["quota"],
            "provider": settings["provider"],
            "searched_at": now_label(),
        }
    except (RailwayApiError, SplitJourneyError, ValueError) as exc:
        st.error(f"Error: {str(exc)}")


def render_split_results(
    split_data: Mapping[str, Any],
    route_rows: Sequence[Mapping[str, Any]],
    params: Mapping[str, Any],
    *,
    show_raw: bool,
) -> None:
    results = split_data.get("results", [])
    
    st.subheader("📊 Search Summary")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Valid Options", len(results))
    metric_cols[1].metric("Route Stops", split_data.get("route_stop_count", 0))
    metric_cols[2].metric("Combinations Tested", split_data.get("checked_combinations", 0))
    metric_cols[3].metric("API Lookups", split_data.get("checked_segments", 0))
    metric_cols[4].metric("Max Waitlist allowed", split_data.get("max_wl", "N/A"))

    render_search_caption(params)

    if route_rows:
        with st.expander("🗺️ View Scheduled Route Traversed", expanded=False):
            st.dataframe(pd.DataFrame(route_rows), width='stretch', hide_index=True)

    if not results:
        st.warning("⚠️ No acceptable same-train split routes found with the current rules. Try increasing the Max WL or searching deeper.")
        if show_raw:
            st.json(split_data)
        return

    summary_df = split_summary_frame(results)
    segment_df = split_segment_frame(results)

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🏆 Best Split Options Available")
    st.dataframe(summary_df, width='stretch', hide_index=True)
    
    render_downloads(
        base_name=f"split_{params.get('train', 'train')}_{params.get('from', 'from')}_{params.get('to', 'to')}",
        payload=split_data,
        frames={"Summary": summary_df, "Segments": segment_df},
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🧩 Detailed Segments")
    for index, result in enumerate(results, start=1):
        label = split_result_label(index, result)
        with st.expander(label, expanded=(index == 1)):
            rows = segment_rows(result.get("segments", []))
            st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

    if show_raw:
        st.markdown("---")
        st.subheader("Raw JSON Response")
        st.json(split_data)


def render_direct_trains_tab(settings: Mapping[str, Any]) -> None:
    with st.form("direct_trains_form", clear_on_submit=False):
        st.subheader("Search Direct Trains")
        cols = st.columns([1, 1, 1, 1.5])
        from_station = cols[0].text_input("From Station", value=DEFAULT_FROM_STATION, key="direct_from")
        to_station = cols[1].text_input("To Station", value=DEFAULT_TO_STATION, key="direct_to")
        journey_day = cols[2].date_input(
            "Journey Date",
            value=parse_default_date(DEFAULT_JOURNEY_DATE),
            format="DD-MM-YYYY",
            key="direct_date",
        )
        class_filter = cols[3].multiselect("Filter by Classes (Optional)", options=CLASS_OPTIONS, default=[])
        
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        submitted = col2.form_submit_button("🚆 Check Direct Availability", type="primary", width='stretch')

    if submitted:
        try:
            normalized_from, normalized_to = validate_route(from_station, to_station)
            journey_date = date_to_api(journey_day)
            session = create_session(retries=int(settings["retries"]))
            with st.spinner("Fetching direct train availabilities..."):
                train_data = get_trains_between_stations(
                    normalized_from,
                    normalized_to,
                    journey_date,
                    quota=str(settings["quota"]),
                    provider=str(settings["provider"]),
                    session=session,
                    timeout=float(settings["timeout"]),
                    use_fetch_availability=True,
                )

            st.session_state["direct_train_result"] = train_data
            st.session_state["direct_train_params"] = {
                "from": normalized_from,
                "to": normalized_to,
                "date": journey_date,
                "classes": normalize_classes(class_filter),
                "quota": settings["quota"],
                "provider": settings["provider"],
                "searched_at": now_label(),
            }
        except (RailwayApiError, ValueError) as exc:
            st.error(f"Error: {str(exc)}")

    st.divider()
    train_data = st.session_state.get("direct_train_result")
    params = st.session_state.get("direct_train_params") or {}
    if train_data:
        render_direct_train_results(train_data, params, show_raw=bool(settings["show_raw"]))
    else:
        st.info("👋 Enter your source and destination to view direct trains.")


def render_direct_train_results(
    train_data: Mapping[str, Any],
    params: Mapping[str, Any],
    *,
    show_raw: bool,
) -> None:
    if not train_data.get("success"):
        st.error(train_data.get("message") or train_data.get("error") or "Could not fetch trains.")
        if show_raw:
            st.json(train_data)
        return

    rows = direct_train_rows(
        train_data.get("train_between_stations", []),
        class_filter=params.get("classes") or [],
    )
    
    if not rows:
        st.warning("⚠️ No direct trains found matching your criteria.")
        if show_raw:
            st.json(train_data)
        return

    direct_df = pd.DataFrame(rows)
    
    st.subheader("📊 Direct Availability Summary")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Unique Trains", direct_df["Number"].nunique())
    metric_cols[1].metric("Total Class Options", len(direct_df))
    metric_cols[2].metric("Available Seats", int((direct_df["Kind"] == "available").sum()))
    metric_cols[3].metric("RAC/WL Tickets", int(direct_df["Kind"].isin(["rac", "wl"]).sum()))

    render_search_caption(params)
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.dataframe(direct_df, width='stretch', hide_index=True)
    
    render_downloads(
        base_name=f"direct_{params.get('from', 'from')}_{params.get('to', 'to')}",
        payload=train_data,
        frames={"Direct Trains": direct_df},
    )

    if show_raw:
        st.markdown("---")
        st.subheader("Raw JSON Response")
        st.json(train_data)


def render_schedule_tab(settings: Mapping[str, Any]) -> None:
    with st.form("schedule_form", clear_on_submit=False):
        st.subheader("View Train Schedule")
        cols = st.columns([2, 1, 1])
        train_number = cols[0].text_input("Train Number", value=DEFAULT_SCHEDULE_TRAIN, max_chars=8)
        
        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("📅 Fetch Schedule", type="primary")

    if submitted:
        try:
            normalized_train = validate_train_number(train_number)
            with st.spinner("Fetching full schedule..."):
                schedule_data = fetch_schedule_cached(
                    normalized_train,
                    int(settings["timeout"]),
                    int(settings["retries"]),
                )
            st.session_state["schedule_result"] = schedule_data
            st.session_state["schedule_params"] = {
                "train": normalized_train,
                "searched_at": now_label(),
            }
        except (RailwayApiError, ValueError) as exc:
            st.error(f"Error: {str(exc)}")

    st.divider()
    schedule_data = st.session_state.get("schedule_result")
    params = st.session_state.get("schedule_params") or {}
    if schedule_data:
        render_schedule_results(schedule_data, params, show_raw=bool(settings["show_raw"]))
    else:
        st.info("👋 Enter a train number to view its full schedule.")


def render_schedule_results(
    schedule_data: Mapping[str, Any],
    params: Mapping[str, Any],
    *,
    show_raw: bool,
) -> None:
    rows = schedule_rows(schedule_data)
    title = f"{schedule_data.get('train_name', 'N/A')} ({schedule_data.get('train_number', 'N/A')})"
    st.subheader(f"🚂 {title}")

    run_days = " ".join(str(day) for day in schedule_data.get("run_days", []) if day)
    caption_parts = [part for part in [run_days, params.get("searched_at")] if part]
    if caption_parts:
        st.caption(" | ".join(caption_parts))

    if not rows:
        st.warning("⚠️ No scheduled stops returned by the provider.")
        return

    schedule_df = pd.DataFrame(rows)
    
    metric_cols = st.columns(3)
    metric_cols[0].metric("Total Stops", len(schedule_df))
    metric_cols[1].metric("Source", schedule_df.iloc[0]["Code"])
    metric_cols[2].metric("Destination", schedule_df.iloc[-1]["Code"])
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.dataframe(schedule_df, width='stretch', hide_index=True)
    
    render_downloads(
        base_name=f"schedule_{params.get('train', schedule_data.get('train_number', 'train'))}",
        payload=schedule_data,
        frames={"Schedule": schedule_df},
    )

    if show_raw:
        st.markdown("---")
        st.subheader("Raw JSON Response")
        st.json(schedule_data)


def render_station_tab(settings: Mapping[str, Any]) -> None:
    with st.form("station_form", clear_on_submit=False):
        st.subheader("Search Station Codes")
        cols = st.columns([3, 1])
        query = cols[0].text_input("Station Name or Code", value=DEFAULT_STATION_QUERY, placeholder="e.g. Bangalore")
        limit = int(
            cols[1].number_input(
                "Result Limit",
                min_value=1,
                max_value=250,
                value=int(DEFAULT_STATION_LIMIT),
            )
        )
        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("🚉 Search Stations", type="primary")

    if submitted:
        try:
            station_data = load_station_cache_cached(str(settings["cache_path"]))
            stations = search_station_local(query, station_data, limit=limit)
            st.session_state["station_result"] = stations
            st.session_state["station_params"] = {
                "query": query,
                "limit": limit,
                "searched_at": now_label(),
            }
        except StationCacheError as exc:
            st.error(f"Error: {str(exc)}")

    st.divider()
    stations = st.session_state.get("station_result")
    params = st.session_state.get("station_params") or {}
    
    if stations:
        station_df = pd.DataFrame(stations)
        st.subheader("📊 Station Results")
        metric_cols = st.columns(2)
        metric_cols[0].metric("Matches Found", len(station_df))
        metric_cols[1].metric("Search Limit applied", params.get("limit", DEFAULT_STATION_LIMIT))
        
        render_search_caption(params)
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(station_df, width='stretch', hide_index=True)
        
        render_downloads(
            base_name=f"stations_{safe_filename(str(params.get('query', 'query')))}",
            payload={"stations": stations, "params": params},
            frames={"Stations": station_df},
        )
    elif stations == []:
        st.warning("⚠️ No stations found matching your query.")
    else:
        st.info("👋 Search for a station name to find its official railway code.")


@st.cache_data(show_spinner=False)
def load_station_cache_cached(cache_path: str) -> list[dict[str, Any]]:
    return load_station_cache(Path(cache_path))


@st.cache_data(ttl=SCHEDULE_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_schedule_cached(train_number: str, timeout: int, retries: int) -> dict[str, Any]:
    session = create_session(retries=retries)
    return get_schedule_from_page(train_number, session=session, timeout=float(timeout))


def route_rows_for_schedule(
    schedule_data: Mapping[str, Any],
    from_station: str,
    to_station: str,
) -> list[dict[str, Any]]:
    route_stops = find_route_slice(
        extract_route_stops(schedule_data),
        from_station,
        to_station,
    )
    rows = []
    for route_index, stop in enumerate(route_stops, start=1):
        rows.append(
            {
                "#": route_index,
                "Station": stop.name,
                "Code": stop.code,
                "Arrival": minutes_to_clock(stop.arrival_minutes, empty_text="START"),
                "Departure": minutes_to_clock(stop.departure_minutes, empty_text="END"),
                "Day": stop.day,
            }
        )
    return rows


def schedule_rows(schedule_data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    stop_count = 1
    for day_group in schedule_data.get("timeTableDaysGroup", []):
        if not isinstance(day_group, Mapping):
            continue
        for stop in day_group.get("items", []):
            if not isinstance(stop, Mapping) or not stop.get("stop"):
                continue
            rows.append(
                {
                    "#": stop_count,
                    "Station": stop.get("station_name"),
                    "Code": stop.get("station_code"),
                    "Arrival": minutes_to_clock(stop.get("sta_min"), empty_text="START"),
                    "Departure": minutes_to_clock(stop.get("std_min"), empty_text="END"),
                    "Day": stop.get("day"),
                }
            )
            stop_count += 1
    return rows


def split_summary_frame(results: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for index, result in enumerate(results, start=1):
        segments = result.get("segments", [])
        status_counts = count_status_kinds(segments)
        rows.append(
            {
                "#": index,
                "Class": result.get("class"),
                "Segments": result.get("segment_count"),
                "Via": split_codes(result),
                "Statuses": " | ".join(
                    f"{segment.get('from', {}).get('code')}->{segment.get('to', {}).get('code')}: "
                    f"{segment.get('status', 'N/A')}"
                    for segment in segments
                ),
                "AVL": status_counts.get("available", 0),
                "RAC": status_counts.get("rac", 0),
                "WL": status_counts.get("wl", 0),
                "Fare (₹)": sum_segment_fares(segments),
            }
        )
    return pd.DataFrame(rows)


def split_segment_frame(results: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for index, result in enumerate(results, start=1):
        for row in segment_rows(result.get("segments", [])):
            row["Option"] = index
            row["Via"] = split_codes(result)
            rows.append(row)
    return pd.DataFrame(rows)


def segment_rows(segments: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for segment in segments:
        rows.append(
            {
                "From": segment.get("from", {}).get("code"),
                "From Name": segment.get("from", {}).get("name"),
                "To": segment.get("to", {}).get("code"),
                "To Name": segment.get("to", {}).get("name"),
                "Date": segment.get("journey_date"),
                "Class": segment.get("class"),
                "Status": segment.get("status"),
                "Kind": segment.get("kind"),
                "Wait Qty": segment.get("count"),
                "Fare": segment.get("fare"),
                "Prediction": segment.get("prediction") or "",
                "Acceptable": bool(segment.get("acceptable")),
            }
        )
    return rows


def direct_train_rows(
    trains: Sequence[Mapping[str, Any]],
    *,
    class_filter: Sequence[str],
) -> list[dict[str, Any]]:
    selected = set(normalize_classes(class_filter))
    rows = []
    for train in trains:
        availability_items = train.get("sa_data", [])
        if not isinstance(availability_items, list):
            availability_items = []

        matched = False
        for class_data in availability_items:
            if not isinstance(class_data, Mapping) or not class_data.get("success"):
                continue
            class_code = clean_text(class_data.get("booking_class")).upper()
            if selected and class_code not in selected:
                continue

            seat_list = class_data.get("seat_availibility") or []
            status_info = seat_list[0] if seat_list and isinstance(seat_list[0], Mapping) else {}
            status = status_info.get(f"Class - {class_code}") or status_info.get("availability") or "N/A"
            parsed = parse_availability_status(status)
            rows.append(
                {
                    "Train Name": train.get("train_name"),
                    "Number": train.get("train_number"),
                    "Depart": train.get("from_std"),
                    "Arrive": train.get("to_sta"),
                    "Duration": train.get("duration"),
                    "Class": class_code,
                    "Status": parsed.get("status"),
                    "Kind": parsed.get("kind"),
                    "Wait Qty": parsed.get("count"),
                    "Fare (₹)": status_info.get("total_fare", "N/A"),
                    "Prediction": status_info.get("prediction") or "",
                }
            )
            matched = True

        if not matched and not selected:
            rows.append(
                {
                    "Train Name": train.get("train_name"),
                    "Number": train.get("train_number"),
                    "Depart": train.get("from_std"),
                    "Arrive": train.get("to_sta"),
                    "Duration": train.get("duration"),
                    "Class": "N/A",
                    "Status": "No availability data",
                    "Kind": "unknown",
                    "Wait Qty": None,
                    "Fare (₹)": "N/A",
                    "Prediction": "",
                }
            )
    return rows


def split_result_label(index: int, result: Mapping[str, Any]) -> str:
    segments = result.get("segments", [])
    via = split_codes(result)
    fare = sum_segment_fares(segments)
    statuses = ", ".join(str(segment.get("status", "N/A")) for segment in segments)
    return (
        f"Option {index} | Class {result.get('class', 'N/A')} | "
        f"{result.get('segment_count', 'N/A')} Segments via {via} | "
        f"Fare: ₹{fare} | Status: {statuses}"
    )


def count_status_kinds(segments: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for segment in segments:
        kind = str(segment.get("kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def split_codes(result: Mapping[str, Any]) -> str:
    split_stations = result.get("split_stations", [])
    if not split_stations:
        return "Direct"
    return " ➝ ".join(str(station.get("code", "N/A")) for station in split_stations)


def sum_segment_fares(segments: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for segment in segments:
        try:
            total += int(segment.get("fare"))
        except (TypeError, ValueError):
            continue
    return total


def render_search_caption(params: Mapping[str, Any]) -> None:
    if not params:
        return
    visible = []
    for key in ("train", "from", "to", "date", "classes", "quota", "provider", "searched_at"):
        value = params.get(key)
        if not value:
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        visible.append(f"**{key.replace('_', ' ').title()}**: {value}")
    if visible:
        st.markdown(" ".join([f"`{item}`" for item in visible]))


def render_downloads(
    *,
    base_name: str,
    payload: Mapping[str, Any],
    frames: Mapping[str, pd.DataFrame],
) -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    col_count = min(4, len(frames) + 1)
    cols = st.columns(col_count)
    
    cols[0].download_button(
        "📄 Download JSON",
        data=json_bytes(payload),
        file_name=f"{safe_filename(base_name)}.json",
        mime="application/json",
        width='stretch'
    )
    for index, (name, frame) in enumerate(frames.items(), start=1):
        if index >= col_count:
            break
        cols[index].download_button(
            f"📊 Download {name} CSV",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name=f"{safe_filename(base_name)}_{safe_filename(name)}.csv",
            mime="text/csv",
            width='stretch'
        )


def validate_train_number(value: str) -> str:
    train_number = clean_text(value)
    if not train_number:
        raise ValueError("Train number is required.")
    if not train_number.isdigit():
        raise ValueError("Train number must contain digits only.")
    return train_number


def validate_route(from_station: str, to_station: str) -> tuple[str, str]:
    source = validate_station_code(from_station, "From")
    destination = validate_station_code(to_station, "To")
    if source == destination:
        raise ValueError("From and To stations must be different.")
    return source, destination


def validate_station_code(value: str, label: str) -> str:
    station_code = clean_text(value).upper()
    if not station_code:
        raise ValueError(f"{label} station is required.")
    if not re.fullmatch(r"[A-Z0-9]{1,6}", station_code):
        raise ValueError(f"{label} station must be a valid station code.")
    return station_code


def normalize_classes(values: Sequence[str] | str | None) -> list[str]:
    parsed = parse_class_list(values)
    return [class_code for class_code in parsed if class_code]


def default_classes(value: str | None) -> list[str]:
    parsed = normalize_classes(value)
    return [class_code for class_code in parsed if class_code in CLASS_OPTIONS]


def parse_default_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%d-%m-%Y").date()
    except ValueError:
        return date.today()


def date_to_api(value: date) -> str:
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d-%m-%Y")


def minutes_to_clock(value: Any, *, empty_text: str) -> str:
    if value in (None, ""):
        return empty_text
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return "N/A"
    if minutes == 0:
        return empty_text
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_index(options: Sequence[str], value: str) -> int:
    try:
        return list(options).index(value)
    except ValueError:
        return 0


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    return cleaned or "railway_export"


def json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode("utf-8")


def now_label() -> str:
    return datetime.now().strftime("%d-%m-%Y %H:%M")


def inject_css() -> None:
    st.markdown(
        """
        <style>
        /* Import clean font */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif !important;
        }

        /* Standardize Container */
        .block-container {
            max-width: 1200px !important;
            padding-top: 2rem !important;
            padding-bottom: 3rem !important;
        }

        /* Clean up standard Streamlit UI items for production */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}

        /* Form Styling: Theme agnostic transparent overlay */
        [data-testid="stForm"] {
            border-radius: 12px !important;
            border: 1px solid rgba(150, 150, 150, 0.2) !important;
            padding: 1.8rem !important;
            background-color: rgba(150, 150, 150, 0.03) !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03) !important;
        }

        /* Primary Call-to-action Button */
        [data-testid="stFormSubmitButton"] button,
        button[kind="primary"] {
            background: linear-gradient(135deg, #0b5aa7 0%, #083d6b 100%) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            padding: 0.6rem 2rem !important;
            transition: all 0.2s ease-in-out !important;
            box-shadow: 0 2px 6px rgba(11, 90, 167, 0.3) !important;
        }
        
        [data-testid="stFormSubmitButton"] button:hover,
        button[kind="primary"]:hover {
            background: linear-gradient(135deg, #083d6b 0%, #0b5aa7 100%) !important;
            box-shadow: 0 4px 12px rgba(11, 90, 167, 0.4) !important;
            transform: translateY(-1px);
        }

        /* Metric Cards */
        [data-testid="stMetric"] {
            background-color: rgba(150, 150, 150, 0.05) !important;
            border: 1px solid rgba(150, 150, 150, 0.2) !important;
            padding: 1rem 1.2rem !important;
            border-radius: 10px !important;
        }

        /* Tabs Polish */
        .stTabs [data-baseweb="tab-list"] {
            gap: 12px;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 0.6rem 1.2rem;
            font-weight: 500;
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(150, 150, 150, 0.1) !important;
            font-weight: 700;
        }

        /* Expanders */
        [data-testid="stExpander"] {
            border: 1px solid rgba(150, 150, 150, 0.2) !important;
            border-radius: 8px !important;
            background-color: transparent !important;
        }
        
        /* Fix sidebar padding */
        [data-testid="stSidebar"] {
            padding-top: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    if _running_in_streamlit():
        main()