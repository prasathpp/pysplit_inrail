# PyInRail - Indian Railways Split Journey Search Tool

A Python-based utility to search Indian Railways trains and intelligently find **split journey** alternatives when direct bookings are unavailable. Split journey booking allows you to book multiple segments of the same train when the direct route shows no availability.

## 🎯 Overview

**PyInRail** is a comprehensive tool for Indian railway ticket hunters. It provides:

1. **Station Search** - Find railway station codes and details
2. **Train Search** - Search trains between two stations with availability and fare information
3. **Schedule Lookup** - View complete train timetables and stop information
4. **Split Journey Search** ⭐ - Intelligently find booking opportunities by splitting long journeys into multiple segments on the same train

The project includes both a **command-line interface (CLI)** and an interactive **Streamlit web application** for easy access.

## 📦 Project Structure

```
pyinrail-master/
├── railway_api.py              # Core API wrapper for RailYatri and Ixigo
├── split_journey.py            # Split journey search algorithm (main feature)
├── rail_scrapper.py            # CLI interface
├── streamlit_app.py            # Web UI
├── stations.py                 # Station cache management
├── formatters.py               # Output formatting utilities
├── create_station_cache.py     # Generate station database cache
├── create_stations_endpoint.py # Create station API endpoint
├── stations_cache.json         # Pre-built station data cache
├── requirements.txt            # Python dependencies
├── tests/                      # Unit tests
│   ├── test_railway_api.py
│   ├── test_split_journey.py
│   ├── test_stations.py
│   ├── test_formatters.py
│   └── test_cli.py
└── README.md                   # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- pip or conda

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/pyinrail.git
   cd pyinrail
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Usage

#### Option 1: Web Application (Recommended for Most Users)

```bash
streamlit run streamlit_app.py
```

This opens an interactive web interface in your browser where you can:
- Search stations
- Check train availability
- View schedules
- Find split journey options with visual results

#### Option 2: Command-Line Interface

```bash
# Search stations
python rail_scrapper.py station mumbai --limit 5

# Find trains between stations
python rail_scrapper.py trains --from BBS --to MAS --date 31-07-2026

# View train schedule
python rail_scrapper.py schedule 16021

# Find split journey opportunities (main feature)
python rail_scrapper.py split --train 16021 --from MAS --to MYS --date 31-07-2026 --classes SL,3A,2A
```

#### Option 3: Use as a Python Library

```python
from railway_api import get_trains_between_stations, create_session
from split_journey import find_same_train_split_journeys

# Create a session with retry logic
session = create_session(retries=2)

# Find split journey options
results = find_same_train_split_journeys(
    train_number="16021",
    from_station="MAS",
    to_station="MYS",
    journey_date="31-07-2026",
    classes="SL,3A,2A",
    max_segments=3,
    session=session,
)

print(results)
```

## ⭐ Core Feature: Split Journey Search

### What is Split Journey Booking?

Split journey booking is a **legal alternative** to traditional direct booking. Instead of booking a single ticket from A → C, you book multiple segment tickets:
- A → B (Segment 1)
- B → C (Segment 2)
- ... all on the **same train**

All segments are on the same train, same date, and same class, making it functionally equivalent to a direct booking.

### Why Use Split Journey?

Indian Railways often show "No Availability" for direct routes during peak seasons, even when the train isn't fully booked. Split journey booking helps because:

1. **More Availability** - Different segments may have different occupancy levels
2. **Algorithmic Search** - Checks multiple segment combinations automatically
3. **Better Success Rate** - Increases chances of getting tickets during high-demand periods
4. **Same Train Experience** - You stay on the same train; no need to change

### Algorithm Overview

The `find_same_train_split_journeys()` function:

1. **Fetches Train Schedule** - Gets all stops for the specified train
2. **Generates Combinations** - Creates all possible segment combinations (2-N segments)
3. **Checks Availability** - Queries availability for each segment combination
4. **Filters Results** - Keeps only combinations with acceptable availability status:
   - ✅ Available (best)
   - ⚠️ RAC (Reservation Against Cancellation) - optional
   - ⏳ WL (Waiting List) - with configurable limit
5. **Ranks Results** - Prioritizes by:
   - Fewest segments
   - Preferred travel class
   - Best availability status
6. **Returns Top Results** - Delivers N best options for user selection

### Configuration Parameters

When using split journey search, you can customize:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `train_number` | Required | Train number (e.g., "16021") |
| `from_station` | Required | Source station code (e.g., "MAS") |
| `to_station` | Required | Destination station code (e.g., "MYS") |
| `journey_date` | Required | Travel date in DD-MM-YYYY format |
| `classes` | "SL,3A,2A" | Comma-separated preferred classes |
| `max_segments` | 3 | Maximum segments to try (2-8) |
| `max_wl` | 20 | Max waiting list position to accept |
| `accept_rac` | True | Accept RAC (Reservation Against Cancellation) |
| `quota` | "GN" | Booking quota (GN, TQ, PT, LD, etc.) |
| `provider` | "ixigo" | API provider: "ixigo" or "railyatri" |
| `max_results` | 10 | Maximum results to return |
| `search_deeper` | False | Continue searching all depths if True |

### Example: Split Journey Search

```python
from railway_api import create_session
from split_journey import find_same_train_split_journeys

session = create_session()

# Search for split journeys on train 16021
# from Chennai Central (MAS) to Mysore (MYS)
results = find_same_train_split_journeys(
    train_number="16021",
    from_station="MAS",
    to_station="MYS",
    journey_date="31-07-2026",
    classes="SL,3A,2A,1A",  # Check multiple classes
    max_segments=4,          # Try up to 4 segments
    max_wl=15,              # Accept WL up to position 15
    accept_rac=True,        # Accept RAC status
    session=session,
)

# Results contain:
# - split_journeys: List of viable segment combinations
# - schedule: Full train schedule
# - route_analysis: Detailed breakdown
```

## 🗂️ Module Reference

### `railway_api.py`

**Core API wrapper** for train data providers (RailYatri and Ixigo).

**Key Functions:**
- `create_session(retries, backoff_factor)` - Creates resilient HTTP session
- `get_trains_between_stations()` - Searches trains with availability
- `get_ixigo_train_availability()` - Ixigo-specific availability fetch
- `get_schedule_from_page(train_number)` - Scrapes train timetable
- `validate_journey_date()` - Validates date format

**Supported Providers:**
- **Ixigo** - More detailed class-wise availability
- **RailYatri** - Alternative data source with caching support

---

### `split_journey.py`

**Split journey search engine** - The main feature!

**Key Classes:**
- `RouteStop` - Represents a train stop with timing info
- `Segment` - Represents a journey segment (from_stop → to_stop)

**Key Functions:**
- `find_same_train_split_journeys()` - Main split journey search algorithm
- `extract_route_stops()` - Parses schedule into structured stops
- `find_route_slice()` - Finds relevant stops between source and destination
- `generate_split_segments()` - Creates all possible segment combinations
- `parse_availability_status()` - Classifies availability strings (Available, RAC, WL, etc.)
- `is_acceptable_status()` - Checks if availability meets criteria

**Algorithm Complexity:**
- Time: O(2^n) where n = number of stops (mitigated by early exit and caching)
- Space: O(n) for stop storage + cache storage
- Practical performance: Searches 100+ combinations in < 5 seconds typically

---

### `rail_scrapper.py`

**Command-line interface** with subcommands for different operations.

**Available Commands:**
```
station      Search stations by name or code
trains       Find trains between two stations
schedule     View full train timetable
split        Find split journey opportunities (main command)
demo         Run demonstration with sample data
```

**Example CLI Usage:**
```bash
# Search for stations starting with "delhi"
python rail_scrapper.py station delhi --limit 10

# List trains from Chennai to Mysore on July 31, 2026
python rail_scrapper.py trains --from MAS --to MYS --date 31-07-2026

# Find split journeys for train 16021
python rail_scrapper.py split --train 16021 --from MAS --to MYS --date 31-07-2026 --max-segments 4 --classes SL,3A,2A
```

---

### `streamlit_app.py`

**Interactive web application** built with Streamlit.

**Features:**
- 🔍 Station search with autocomplete
- 🚆 Train search with real-time availability
- 📅 Schedule viewer with visual stop timeline
- 🎫 Split journey search with result visualization
- ⚙️ Advanced filtering and preferences
- 📊 Result ranking and comparison

**To Run:**
```bash
streamlit run streamlit_app.py
```

---

### `stations.py`

**Station cache management** for offline station search.

**Functions:**
- `load_station_cache()` - Loads pre-built station database
- `search_station_local()` - Searches stations by name/code
- Station data includes: code, name, zone, state, etc.

**Note:** Run `create_station_cache.py` to generate or update the station cache.

---

### `formatters.py`

**Output formatting** utilities for CLI and terminal display.

**Key Functions:**
- `format_station_results()` - Formats station search results
- `format_train_info()` - Formats train search output
- `format_schedule_info()` - Formats timetable display
- `format_split_journey_results()` - Formats split journey results
- `minutes_to_hhmm()` - Converts minutes to HH:MM format

---

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_split_journey.py -v

# Run with coverage
pip install pytest-cov
python -m pytest tests/ --cov=. --cov-report=html
```

**Test Files:**
- `test_split_journey.py` - Split journey algorithm tests
- `test_railway_api.py` - API wrapper tests
- `test_stations.py` - Station search tests
- `test_formatters.py` - Output formatting tests
- `test_cli.py` - CLI interface tests

## 🔧 Configuration

### Hardcoded Defaults

Edit `rail_scrapper.py` lines 24-42 to change defaults:

```python
DEFAULT_COMMAND = "split"           # Default subcommand
DEFAULT_FROM_STATION = "MAS"        # Default source
DEFAULT_TO_STATION = "MYS"          # Default destination
DEFAULT_JOURNEY_DATE = "31-07-2026" # Default travel date
DEFAULT_SPLIT_CLASSES = "SL,3A,2A" # Default class preferences
DEFAULT_SPLIT_MAX_SEGMENTS = 3      # Default max segments
DEFAULT_SPLIT_MAX_WL = 20           # Default WL limit
DEFAULT_SPLIT_MAX_RESULTS = 10      # Default result limit
```

### Environment Variables

You can also pass arguments via CLI flags (see `rail_scrapper.py` for full list):

```bash
python rail_scrapper.py split \
  --train 16021 \
  --from MAS \
  --to MYS \
  --date 31-07-2026 \
  --classes SL,3A,2A \
  --max-segments 4 \
  --max-wl 15 \
  --accept-rac true \
  --provider ixigo
```

## 📊 Output Examples

### Split Journey Results

```
SPLIT JOURNEY RESULTS FOR TRAIN 16021
=====================================

Train: Chennai Central to Mysore Express
Journey Date: 31-07-2026
Segments: 3-4 recommended

✅ OPTION 1 (3 Segments, Class: SL)
  Score: 0.95
  Segment 1: MAS → BWT (Available)
  Segment 2: BWT → KPD (Available)
  Segment 3: KPD → MYS (Available)
  Split Points: BWT, KPD

⚠️ OPTION 2 (2 Segments, Class: 3A)
  Score: 0.80
  Segment 1: MAS → KPD (Available)
  Segment 2: KPD → MYS (RAC - 5)

⏳ OPTION 3 (4 Segments, Class: 2A)
  Score: 0.70
  Segment 1: MAS → BWT (WL - 8)
  Segment 2: BWT → KPD (Available)
  Segment 3: KPD → AJJ (Available)
  Segment 4: AJJ → MYS (Available)
```

## 🐛 Troubleshooting

### "Station cache not found" Error

**Solution:** Generate the station cache:
```bash
python create_station_cache.py
```

### API Rate Limiting

If you get timeout errors:
- Reduce concurrent requests
- Increase `timeout` parameter
- Use `max_segments` limit to reduce API calls

### Availability Data Outdated

The API data is real-time but may have slight delays. Try:
- Refreshing the search
- Checking directly on railway websites for verification
- Using `search_deeper=True` to explore more combinations

### Split Journey Not Recommended

Reasons availability may not show splits:
1. Train is fully booked across all segments
2. No intermediate stops between source and destination
3. Waiting list position exceeds `max_wl` threshold
4. RAC status not acceptable (set `accept_rac=True`)

## 📋 Class Codes Reference

| Code | Class |
|------|-------|
| SL | Sleeper |
| 3A | 3-tier AC |
| 2A | 2-tier AC |
| 1A | 1-tier AC (First Class) |
| CC | Chair Car |
| EC | Executive Chair Car |
| 2S | Second Sitting |
| 3E | 3-tier Non-AC |
| FC | First Class Non-AC |
| EA | Economy AC |

## 🎫 Quota Codes Reference

| Code | Quota |
|------|-------|
| GN | General |
| TQ | Tatkal |
| PT | Premium Tatkal |
| LD | Ladies |
| SS | Lower Berth |
| HP | Physically Handicapped |
| DF | Defence |

## 📚 API Response Structure

Split journey results follow this structure:

```python
{
    "success": True,
    "split_journeys": [
        {
            "train_number": "16021",
            "train_name": "Chennai Central - Mysore Express",
            "class": "SL",
            "quota": "GN",
            "segment_count": 3,
            "segments": [
                {
                    "from": {"code": "MAS", "name": "Chennai Central"},
                    "to": {"code": "KPD", "name": "Katpadi"},
                    "availability": "Available",
                    "fare": 145
                },
                # ... more segments
            ],
            "split_stations": [
                {"code": "BWT", "name": "Bowenpally"}
                # ... more split points
            ],
            "score": 0.95
        }
    ],
    "schedule": {...},
    "checked_combinations": 487,
    "execution_time_ms": 3421
}
```

## 🚫 Limitations & Disclaimers

1. **Accuracy** - Data provided is as-is from public APIs. Always verify on official railway websites before booking.
2. **Reliability** - API endpoints may change or become unavailable without notice.
3. **Rate Limiting** - Excessive requests may result in temporary IP bans from upstream servers.
4. **Legal Use** - This tool is for information gathering only. Actual booking must be done through official channels.
5. **Split Journey Legality** - Split journey booking is legal, but verify with railway authorities if unsure.

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

**Areas for contribution:**
- Additional train data providers
- Performance optimization
- Web UI improvements
- Documentation
- Test coverage

## 📝 License

This project is licensed under the MIT License - see LICENSE file for details.

## 👨‍💻 Author

Created as a utility tool for Indian railway ticket hunters.

## 📞 Support & Feedback

- **Issues**: Report bugs on GitHub Issues
- **Discussions**: Share ideas and ask questions
- **Feature Requests**: Suggest improvements on GitHub Discussions

## 🔗 Related Resources

- [Indian Railways Official Website](https://www.indianrailways.gov.in/)
- [IRCTC Booking Portal](https://www.irctc.co.in/)
- [Train Schedule Information](https://www.railyatri.in/)
- [Ixigo Trains](https://www.ixigo.com/trains)

---

**Last Updated:** July 2026  
**Python Version:** 3.8+  
**Status:** Active Development
