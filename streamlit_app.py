import time
import json
import os
import streamlit as st
import pandas as pd
import string
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# ==========================================
# 0. BACKEND MONKEY-PATCH (Fixing Fare & Rich Data)
# ==========================================
# We patch the backend parsers dynamically here so you don't have to rewrite your package.
import pysplit_inrail.railway_api as backend_api
_original_normalize = backend_api._normalize_ixigo_fetch_availability

def _patched_normalize_ixigo_fetch_availability(payload, *, journey_date, quota=None):
    res = _original_normalize(payload, journey_date=journey_date, quota=quota)
    if not res: return res

    data = payload.get("data", {})

    # 1. Fix Fare by digging into fareInfo
    fare_info = data.get("fareInfo", {})
    if "totalFare" in fare_info:
        res["fare"] = fare_info["totalFare"]
    elif "baseFare" in fare_info:
        res["fare"] = fare_info["baseFare"]

    # 2. Extract rich prediction and confirmation status from avlDayList
    avl_list = data.get("avlDayList", [])
    chosen_entry = None
    for entry in avl_list:
        # Match based on status string to find the correct day object
        if entry.get("availablityStatus") == res.get("availability") or entry.get("availability") == res.get("availability"):
            chosen_entry = entry
            break

    if not chosen_entry and avl_list:
        chosen_entry = avl_list[0]

    if chosen_entry:
        res["predictionPercentage"] = chosen_entry.get("predictionPercentage")
        res["confirmTktStatus"] = chosen_entry.get("confirmTktStatus")

        # Override prediction text with richer data if available
        if res.get("predictionPercentage"):
            res["prediction"] = f"{res['predictionPercentage']}% Chance ({res['confirmTktStatus']})"

    return res

# Apply the patch globally
backend_api._normalize_ixigo_fetch_availability = _patched_normalize_ixigo_fetch_availability

from pysplit_inrail.railway_api import get_trains_between_stations, get_schedule_from_page, RailwayApiError
from pysplit_inrail.split_journey import find_same_train_split_journeys, SplitJourneyError


# ==========================================
# 1. PAGE CONFIGURATION & CUSTOM CSS
# ==========================================
st.set_page_config(page_title="InRail Smart Search", page_icon="🚆", layout="wide")

st.markdown("""
<style>
    .badge {
        display: inline-block; padding: 0.4em 0.7em; font-size: 0.85em; font-weight: 700;
        line-height: 1; text-align: center; white-space: nowrap; vertical-align: baseline;
        border-radius: 0.25rem; margin-right: 5px; margin-bottom: 5px;
    }
    .badge-avail { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .badge-rac { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
    .badge-wl { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .badge-cancel { background-color: #f5c6cb; color: #721c24; border: 1px solid #f5c6cb; text-decoration: line-through; }
    .badge-na { background-color: #e2e3e5; color: #383d41; border: 1px solid #d6d8db; }

    .seat-card {
        border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; margin-bottom: 10px;
        background-color: #fdfdfd; box-shadow: 1px 1px 4px rgba(0,0,0,0.05);
    }
    .split-step {
        border-left: 4px solid #4CAF50; padding-left: 15px; margin-bottom: 15px;
    }
    .time-badge { font-family: monospace; color: #555; font-size: 0.9em; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. DATA LOADERS & HELPERS
# ==========================================

@st.cache_data
def load_all_stations():
    """
    Loads all stations from stations_cache.json.
    Matches Name and Code for searchability.
    """
    stations = set()
    cache_file = "stations_cache.json"

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                # Handle dictionary format { "MAS": {"name": "Chennai", "code": "MAS"}, ... }
                if isinstance(data, dict):
                    for k, v in data.items():
                        code = v.get('code', k).upper()
                        name = v.get('name', k).upper()
                        stations.add(f"{code} - {name}")
                # Handle list format [ {"code": "MAS", "name": "Chennai"}, ... ]
                elif isinstance(data, list):
                    for item in data:
                        code = str(item.get('code', '')).upper()
                        name = str(item.get('name', '')).upper()
                        if code and name:
                            stations.add(f"{code} - {name}")
        except Exception as e:
            st.error(f"Error reading station cache: {e}")

    if not stations:
        # Emergency fallback stations
        stations.update(["MAS - CHENNAI CENTRAL", "MYS - MYSURU JN", "SBC - KSR BENGALURU", "NDLS - NEW DELHI"])

    return sorted(list(stations))


@st.cache_data
def load_all_trains():
    """
    Loads the complete Indian Railways train database from RailYatri.

    Uses ThreadPoolExecutor to fetch A-Z and 0-9 from RailYatri in ~2 seconds.
    Saves to trains_cache.json for instant subsequent loads.

    Returns a lookup dictionary keyed by train_number, where each value holds
    the full RailYatri metadata:
        {
            "train_number": "58719",
            "train_name": "ABHANPUR RAJIM PASENGER",
            "train_src": "AVP",
            "train_dstn": "RIM",
            "src_name": "Abhanpur Junction",
            "dstn_name": "Rajim",
        }
    """
    train_lookup = {}
    cache_file = "trains_cache.json"

    def add_record(rec):
        """Normalizes a raw record (from API or cache, in any known shape) into
        the lookup dict, keyed by train number."""
        if not isinstance(rec, dict):
            return
        num = str(rec.get("train_number") or rec.get("trainNo") or rec.get("trainNumber") or "").strip()
        name = str(rec.get("train_name") or rec.get("trainName") or "").strip().upper()
        if not num or not name:
            return
        train_lookup[num] = {
            "train_number": num,
            "train_name": name,
            "train_src": str(rec.get("train_src") or rec.get("src") or rec.get("trainSrc") or "").strip().upper(),
            "train_dstn": str(rec.get("train_dstn") or rec.get("dstn") or rec.get("trainDstn") or "").strip().upper(),
            "src_name": str(rec.get("src_name") or rec.get("srcName") or "").strip(),
            "dstn_name": str(rec.get("dstn_name") or rec.get("dstnName") or "").strip(),
        }

    # 1. Try loading from local cache first
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for t in data:
                        if isinstance(t, str):
                            # Legacy "12345 - NAME" cache format
                            parts = t.split(" - ", 1)
                            if len(parts) == 2:
                                add_record({"train_number": parts[0], "train_name": parts[1]})
                        elif isinstance(t, dict):
                            add_record(t)
                elif isinstance(data, dict):
                    # Legacy "{code: {...}}" cache format, or a raw {"trains": [...]} payload
                    if "trains" in data and isinstance(data["trains"], list):
                        for t in data["trains"]:
                            add_record(t)
                    else:
                        for k, v in data.items():
                            if isinstance(v, dict):
                                v = dict(v)
                                v.setdefault("train_number", k)
                                add_record(v)
        except Exception:
            pass

    # 2. If cache is empty or missing, fetch dynamically from RailYatri
    if not train_lookup:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        }

        def fetch_char_batch(char):
            try:
                url = f"https://www.railyatri.in/trains/sort_by_char/{char}"
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json().get("trains", [])
            except Exception:
                return []
            return []

        # All characters: a-z and 0-9
        search_chars = list(string.ascii_lowercase) + [str(i) for i in range(10)]

        with st.status("Initializing Train Database (fetching ~4,000 trains)...", expanded=False) as status:
            with ThreadPoolExecutor(max_workers=12) as executor:
                future_to_char = {executor.submit(fetch_char_batch, c): c for c in search_chars}
                for future in as_completed(future_to_char):
                    results = future.result()
                    for t in results:
                        add_record(t)

            status.update(label=f"Database Loaded! Found {len(train_lookup)} trains.", state="complete")

        # 3. Save to local cache for future use (full metadata, not just "NUM - NAME")
        if train_lookup:
            try:
                with open(cache_file, "w") as f:
                    json.dump(
                        sorted(train_lookup.values(), key=lambda r: r["train_number"]),
                        f, indent=4
                    )
            except Exception:
                pass

    # 4. Fallback if everything failed
    if not train_lookup:
        fallback_records = [
            {"train_number": "16021", "train_name": "KAVERI EXPRESS", "train_src": "MYS", "train_dstn": "MAS",
             "src_name": "Mysuru Jn", "dstn_name": "Chennai Central"},
            {"train_number": "12627", "train_name": "KARNATAKA EXPRESS", "train_src": "SBC", "train_dstn": "NDLS",
             "src_name": "KSR Bengaluru", "dstn_name": "New Delhi"},
            {"train_number": "12007", "train_name": "SHATABDI EXPRESS", "train_src": "MAS", "train_dstn": "MYS",
             "src_name": "Chennai Central", "dstn_name": "Mysuru Jn"},
        ]
        for rec in fallback_records:
            add_record(rec)

    return train_lookup


def build_train_display_options(train_lookup: dict) -> list:
    """
    Builds the sorted "suggestion" strings shown in the selectboxes, e.g.:
        "58719 - ABHANPUR RAJIM PASENGER (AVP RIM)"
    These are suggestions only -- the fields also accept arbitrary free text.

    NOTE: the source/destination codes are joined with a plain space (not an
    arrow/dash) on purpose. Streamlit's built-in dropdown search can fall back
    to a strict "contains" substring match depending on version, and typing
    e.g. "mas eknr" needs "MAS EKNR" to appear as a literal contiguous
    substring to be found -- an arrow or dash in between would break that.
    """
    options = []
    for info in train_lookup.values():
        route = ""
        if info.get("train_src") or info.get("train_dstn"):
            route = f" ({info.get('train_src', '')} {info.get('train_dstn', '')})"
        options.append(f"{info['train_number']} - {info['train_name']}{route}")
    return sorted(options)


def extract_code(selection: str) -> str:
    """
    Extracts the leading Code or Train Number from a selection.

    Accepts BOTH:
      - A suggestion picked from the dropdown, e.g. "12345 - SOME TRAIN (AVP -> RIM)"
        or "MAS - CHENNAI CENTRAL"  -> returns "12345" / "MAS"
      - Arbitrary free-form text typed by the user (since fields now allow
        entries outside the suggestion list), e.g. "12345" or "mas" or a
        train name typed directly -> returned as-is (trimmed/uppercased where
        it looks like a bare code).
    """
    if not selection:
        return ""
    selection = str(selection).strip()
    if not selection:
        return ""
    if " - " in selection:
        return selection.split(" - ")[0].strip()
    return selection


def render_badge(status: str, prediction: str = None) -> str:
    """Generates HTML for colored status badges and predictions."""
    status_upper = str(status).upper()
    css_class = "badge-na"

    if "CANCELLED" in status_upper:
        css_class = "badge-cancel"
    elif "AVL" in status_upper or "AVAILABLE" in status_upper:
        css_class = "badge-avail"
    elif "RAC" in status_upper:
        css_class = "badge-rac"
    elif "WL" in status_upper:
        css_class = "badge-wl"

    html = f'<span class="badge {css_class}">{status}</span>'

    # Add Prediction text if it exists
    if prediction and str(prediction).strip() not in ["None", "", "null"]:
        html += f'<br><small style="color: #666; font-size: 0.8em;">📈 {prediction}</small>'

    return html


def sync_train_route():
    """
    Callback fired whenever the Tab 1 train field changes (either by typing +
    Enter/blur, or by picking a suggestion).
    Auto-fills the From/To station fields from the selected train's metadata,
    if that train number is a known one. The user can still freely edit
    From/To afterwards, since those are plain free-text fields too.
    """
    selected = st.session_state.get("t1_train_input", "")
    code = extract_code(selected)
    info = TRAIN_LOOKUP.get(code)
    if not info:
        return
    if info.get("train_src") and info.get("src_name"):
        st.session_state["t1_from_input"] = f"{info['train_src']} - {info['src_name'].upper()}"
    if info.get("train_dstn") and info.get("dstn_name"):
        st.session_state["t1_to_input"] = f"{info['train_dstn']} - {info['dstn_name'].upper()}"


def free_choice_field(label, options, key, default=None, placeholder=None, help_text=None, on_change=None):
    """
    A SINGLE combo box: pick a suggestion from the dropdown, or type any
    arbitrary value. Streamlit's underlying widget only commits typed text
    that isn't in the list when you press Enter (or Tab) while it's
    highlighted -- clicking elsewhere without pressing Enter does not commit
    it, since that's a limitation of the widget itself, not something we can
    configure around. The placeholder text below reminds the user to press
    Enter.

    filter_mode="fuzzy" is requested explicitly (matches when the typed
    characters appear in order, even with other text in between -- e.g.
    "mas eknr" matches "...(MAS EKNR)...").
    Streamlit versions before ~1.56 don't support this parameter, so we fall
    back to the plain call (whatever that version's default matching is) if
    it raises a TypeError.
    """
    st.session_state.setdefault(key, default)
    kwargs = dict(
        options=options,
        accept_new_options=True,
        placeholder=placeholder or "Select a suggestion, or type a value and press Enter...",
        help=help_text,
        key=key,
        on_change=on_change,
    )
    try:
        return st.selectbox(label, filter_mode="fuzzy", **kwargs)
    except TypeError:
        # Installed Streamlit version doesn't support filter_mode yet.
        return st.selectbox(label, **kwargs)


# Initialize the global lookups/lists for UI
STATION_OPTIONS = load_all_stations()
TRAIN_LOOKUP = load_all_trains()
TRAIN_OPTIONS = build_train_display_options(TRAIN_LOOKUP)
tomorrow = datetime.now() + timedelta(days=1)


# ==========================================
# 3. SIDEBAR CONFIGURATION
# ==========================================
with st.sidebar:
    st.title("🚆 InRail Settings")
    provider_pref = st.selectbox("API Provider", ["ixigo", "railyatri"])
    timeout_pref = st.slider("HTTP Timeout (sec)", 10, 60, 20)
    retry_pref = st.number_input("Retries", 0, 5, 2)
    if st.button("Clear Application Cache", width='stretch'):
        st.cache_data.clear()
        st.success("Cache cleared!")


# ==========================================
# 4. MAIN APPLICATION TABS
# ==========================================
tab1, tab2, tab3 = st.tabs(["🧩 Smart Split Optimizer", "🚆 Direct Train Search", "🕒 Schedule & Route"])

# ---------------------------------------------------------
# TAB 1: SMART SPLIT OPTIMIZER
# ---------------------------------------------------------
with tab1:
    st.header("Find Split Journeys on the Same Train")
    st.caption("When direct tickets are waitlisted, this searches multiple combinations to find confirmed/RAC tickets on the exact same train by splitting the journey.")

    col1, col2, col3 = st.columns(3)
    with col1:
        train_sel = free_choice_field(
            "Train (Name or Number)", TRAIN_OPTIONS, key="t1_train_input",
            placeholder="Pick a suggestion, or type e.g. 12345 and press Enter",
            help_text="Picking a known train from the list auto-fills From/To below. You can also type any train number/name and press Enter to use it as-is.",
            on_change=sync_train_route,
        )
    with col2:
        from_sel = free_choice_field(
            "From Station", STATION_OPTIONS, key="t1_from_input",
            default=STATION_OPTIONS[0] if STATION_OPTIONS else None,
            placeholder="Pick a suggestion, or type e.g. MAS and press Enter",
        )
    with col3:
        to_sel = free_choice_field(
            "To Station", STATION_OPTIONS, key="t1_to_input",
            default=STATION_OPTIONS[1] if len(STATION_OPTIONS) > 1 else (STATION_OPTIONS[0] if STATION_OPTIONS else None),
            placeholder="Pick a suggestion, or type e.g. MYS and press Enter",
        )

    date_input = st.date_input("Journey Date", value=tomorrow, key="t1_date")

    st.markdown("##### Preferences")
    # Openly visible preferences
    p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns(5)
    with p_col1: classes_sel = st.multiselect("Classes", ["SL", "3A", "2A", "1A", "CC", "EC", "2S", "3E", "FC", "EA"], default=["SL", "3A"])
    with p_col2: max_seg_sel = st.number_input("Max Segments", min_value=2, max_value=5, value=3)
    with p_col3: max_wl_sel = st.number_input("Acceptable WL", min_value=0, max_value=100, value=20)
    with p_col4:
        accept_rac_sel = st.checkbox("Accept RAC", value=True)
        search_deep_sel = st.checkbox("Search Deeper", value=False)
    with p_col5:
        st.write("")
        submit_split = st.button("Optimize Splits", type="primary", width='stretch', key="t1_submit")

    # Run the search and STORE the outcome in session_state -- this block only
    # runs on the click itself, but the render block below runs on every
    # rerun (including switching tabs), so results stay visible afterwards.
    if submit_split:
        if not classes_sel:
            st.session_state["t1_error"] = "Select at least one class."
            st.session_state["t1_result"] = None
        elif not st.session_state.get("t1_train_input"):
            st.session_state["t1_error"] = "Please select or enter a train."
            st.session_state["t1_result"] = None
        else:
            t0 = time.time()
            train_num = extract_code(st.session_state.get("t1_train_input"))
            from_stn = extract_code(st.session_state.get("t1_from_input"))
            to_stn = extract_code(st.session_state.get("t1_to_input"))
            j_date = date_input.strftime("%d-%m-%Y")

            with st.spinner(f"Analyzing route combinations for {train_num}..."):
                try:
                    split_data = find_same_train_split_journeys(
                        train_number=train_num, from_station=from_stn, to_station=to_stn,
                        journey_date=j_date, provider=provider_pref, classes=",".join(classes_sel),
                        max_segments=max_seg_sel, max_wl=max_wl_sel, accept_rac=accept_rac_sel,
                        search_deeper=search_deep_sel, timeout=timeout_pref
                    )
                    st.session_state["t1_error"] = None
                    st.session_state["t1_result"] = {
                        "split_data": split_data,
                        "elapsed": time.time() - t0,
                    }
                except Exception as e:
                    st.session_state["t1_result"] = None
                    st.session_state["t1_error"] = f"Error ({time.time() - t0:.2f}s): {e}"

    # Render whatever is currently stored -- persists across reruns/tab switches.
    if st.session_state.get("t1_error"):
        st.error(st.session_state["t1_error"])

    if st.session_state.get("t1_result"):
        split_data = st.session_state["t1_result"]["split_data"]
        elapsed = st.session_state["t1_result"]["elapsed"]
        st.success(f"⏱️ Optimization completed in **{elapsed:.2f} seconds**.")

        if not split_data.get("results"):
            st.warning("No acceptable split journeys found. Try increasing Waitlist limit or enabling 'Search Deeper'.")
        else:
            st.info(f"Analyzed {split_data['checked_combinations']} combinations across {split_data['checked_segments']} route segments.")

            for idx, res in enumerate(split_data["results"]):
                with st.container():
                    st.markdown(f"#### Option {idx + 1}: {res['class']} Class")
                    total_fare = sum(seg['fare'] for seg in res['segments'] if isinstance(seg['fare'], (int, float)))
                    st.markdown(f"**Total Fare:** ₹{total_fare} | **Splits Required:** {res['segment_count'] - 1}")

                    for seg in res['segments']:
                        badge = render_badge(seg['status'], seg.get('prediction'))
                        fare_txt = f"₹{seg['fare']}" if str(seg['fare']) != "N/A" else "N/A"

                        st.markdown(f"""
                        <div class="split-step">
                            <strong>{seg['from']['name']} ({seg['from']['code']}) ➔ {seg['to']['name']} ({seg['to']['code']})</strong><br>
                            <span class="time-badge">Date: {seg['journey_date']}</span> |
                            <span style="font-weight:600; color:#2c3e50;">Fare: {fare_txt}</span><br>
                            <div style="margin-top: 8px;">{badge}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    st.divider()


# ---------------------------------------------------------
# TAB 2: DIRECT TRAIN SEARCH
# ---------------------------------------------------------
with tab2:
    st.header("Search Direct Trains & Availability")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        d_from_sel = free_choice_field(
            "From Station", STATION_OPTIONS, key="d_from",
            default=STATION_OPTIONS[0] if STATION_OPTIONS else None,
            placeholder="Pick a suggestion, or type e.g. MAS and press Enter",
        )
    with col2:
        d_to_sel = free_choice_field(
            "To Station", STATION_OPTIONS, key="d_to",
            default=STATION_OPTIONS[1] if len(STATION_OPTIONS) > 1 else (STATION_OPTIONS[0] if STATION_OPTIONS else None),
            placeholder="Pick a suggestion, or type e.g. MYS and press Enter",
        )
    with col3: d_date = st.date_input("Journey Date", value=tomorrow, key="d_date")
    with col4: d_quota = st.selectbox("Quota", ["GN", "TQ", "PT", "LD", "SS", "HP", "DF"], index=0, key="d_quota")

    submit_direct = st.button("Search Direct Trains", type="primary", key="d_submit")

    if submit_direct:
        t0 = time.time()
        d_from_code = extract_code(d_from_sel)
        d_to_code = extract_code(d_to_sel)
        d_date_str = d_date.strftime("%d-%m-%Y")

        with st.spinner(f"Fetching trains and live seat data from {d_from_code} to {d_to_code}..."):
            try:
                train_data = get_trains_between_stations(
                    from_station=d_from_code, to_station=d_to_code, journey_date=d_date_str,
                    quota=d_quota, provider=provider_pref, timeout=timeout_pref, use_fetch_availability=True
                )
                st.session_state["t2_error"] = None
                st.session_state["t2_result"] = {
                    "trains": train_data.get("train_between_stations", []),
                    "elapsed": time.time() - t0,
                }
            except Exception as e:
                st.session_state["t2_result"] = None
                st.session_state["t2_error"] = f"Error ({time.time() - t0:.2f}s): {e}"

    # Render whatever is currently stored -- persists across reruns/tab switches.
    if st.session_state.get("t2_error"):
        st.error(st.session_state["t2_error"])

    if st.session_state.get("t2_result"):
        trains = st.session_state["t2_result"]["trains"]
        elapsed = st.session_state["t2_result"]["elapsed"]
        st.success(f"⏱️ Fetched {len(trains)} trains in **{elapsed:.2f} seconds**.")

        if not trains:
            st.warning("No direct trains found for this route and date.")
        else:
            for t in trains:
                # Train Header
                with st.expander(f"🚆 {t.get('train_number')} - {t.get('train_name')} | Dep: {t.get('from_std')} ➔ Arr: {t.get('to_sta')}"):
                    st.markdown(f"<span class='time-badge'>Duration: {t.get('duration')} Hrs</span>", unsafe_allow_html=True)

                    sa_list = t.get("sa_data", [])
                    if not sa_list:
                        st.info("Availability data missing for this train.")
                    else:
                        cols = st.columns(min(len(sa_list), 4)) # Wrap if more than 4 classes
                        for i, sa in enumerate(sa_list):
                            col_idx = i % 4
                            if sa.get("success"):
                                cls = sa.get("booking_class")
                                seat_info = sa.get("seat_availibility", [{}])[0]

                                # Use our patched richer details
                                status = seat_info.get(f"Class - {cls}", "N/A")
                                fare = seat_info.get("total_fare", "N/A")
                                prediction = seat_info.get("prediction", "")

                                badge = render_badge(status, prediction)
                                fare_display = f"₹{fare}" if str(fare) != "N/A" else "Fare N/A"

                                with cols[col_idx]:
                                    st.markdown(f"""
                                    <div class="seat-card">
                                        <h4 style="margin: 0 0 10px 0; color: #333;">{cls} Class</h4>
                                        <div style="font-weight: 600; color: #1a73e8; margin-bottom: 10px;">{fare_display}</div>
                                        {badge}
                                    </div>
                                    """, unsafe_allow_html=True)


# ---------------------------------------------------------
# TAB 3: TRAIN SCHEDULE & ROUTE MAP
# ---------------------------------------------------------
with tab3:
    st.header("Train Timetable & Route Map")
    st.caption("Search by either Train Number or Train Name.")

    col1, col2 = st.columns([3, 1])
    with col1:
        sched_train_sel = free_choice_field(
            "Search Train (Autocomplete)", TRAIN_OPTIONS, key="sched_train",
            placeholder="Pick a suggestion, or type e.g. 12345 and press Enter",
        )
    with col2:
        st.write("")
        st.write("")
        submit_sched = st.button("Fetch Schedule", type="primary", width='stretch', key="sched_submit")

    if submit_sched:
        t0 = time.time()
        sched_train_num = extract_code(sched_train_sel)

        if not sched_train_num:
            st.session_state["t3_result"] = None
            st.session_state["t3_error"] = "Please select or enter a train."
        else:
            with st.spinner(f"Fetching complete route for {sched_train_num}..."):
                try:
                    schedule_data = get_schedule_from_page(train_number=sched_train_num, timeout=timeout_pref)

                    route_data = []
                    for group in schedule_data.get("timeTableDaysGroup", []):
                        for item in group.get("items", []):
                            if item.get("stop"):
                                route_data.append({
                                    "Day": item.get("day", 1),
                                    "Station": f"{item.get('station_name')} ({item.get('station_code')})",
                                    "Arrives": item.get("sta", "-"),
                                    "Departs": item.get("std", "-"),
                                    "Halt (m)": item.get("halt_time", 0),
                                    "Distance (km)": item.get("distance", 0)
                                })

                    st.session_state["t3_error"] = None
                    st.session_state["t3_result"] = {
                        "train_number": schedule_data.get("train_number"),
                        "train_name": schedule_data.get("train_name"),
                        "route_data": route_data,
                        "elapsed": time.time() - t0,
                    }
                except Exception as e:
                    st.session_state["t3_result"] = None
                    st.session_state["t3_error"] = f"Error ({time.time() - t0:.2f}s): {e}"

    # Render whatever is currently stored -- persists across reruns/tab switches.
    if st.session_state.get("t3_error"):
        st.error(st.session_state["t3_error"])

    if st.session_state.get("t3_result"):
        result = st.session_state["t3_result"]
        st.success(f"⏱️ Schedule loaded in **{result['elapsed']:.2f} seconds**.")
        st.subheader(f"🚆 {result['train_number']} - {result['train_name']}")

        if result["route_data"]:
            df = pd.DataFrame(result["route_data"])
            st.dataframe(df, width='stretch', hide_index=True)
        else:
            st.warning("No valid route data found in the schedule.")
