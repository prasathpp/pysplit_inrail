# PyInRail Project Structure Guide

## Directory Layout

```
pyinrail-master/
│
├── 📄 README.md                    # Main documentation - START HERE
├── 📄 CONTRIBUTING.md              # Contribution guidelines
├── 📄 LICENSE                      # MIT License
├── 📄 CHANGELOG.md                 # Version history and changes
│
├── � PYINRAIL PACKAGE (core library)
│   └── pyinrail/
│       ├── __init__.py             # Package initialization
│       ├── railway_api.py          # API wrapper for train data providers
│       ├── split_journey.py        # Split journey search algorithm (⭐ MAIN FEATURE)
│       ├── stations.py             # Station cache & search utilities
│       └── formatters.py           # Output formatting helpers
│
├── 🖥️ USER INTERFACES & UTILITIES (at root)
│   ├── rail_scrapper.py            # Command-line interface (CLI)
│   ├── streamlit_app.py            # Web application (recommended for users)
│   ├── create_station_cache.py     # Generate station database
│   └── create_stations_endpoint.py # API endpoint creation
│
├── 📊 DATA FILES
│   ├── stations_cache.json         # Pre-built station data (~ 2000+ stations)
│   └── stations_endpoint.json      # Station endpoint reference
│
├── 🧪 TESTS (tests/)
│   ├── test_railway_api.py         # API wrapper tests
│   ├── test_split_journey.py       # Split journey algorithm tests
│   ├── test_stations.py            # Station search tests
│   ├── test_formatters.py          # Formatter tests
│   ├── test_cli.py                 # CLI interface tests
│   └── __init__.py
│
├── 📋 CONFIGURATION
│   ├── requirements.txt            # Python dependencies
│   ├── .gitignore                  # Git ignore rules
│   └── .venv/                      # Virtual environment (do not commit)
│
└── 🗂️ GENERATED (do not commit)
    ├── __pycache__/                # Python bytecode cache
    ├── .pytest_cache/              # Pytest cache
    └── .venv/                      # Virtual environment
```

## File Descriptions

### Core Modules (in `pyinrail/` package)

#### `pyinrail.railway_api` (633 lines)
**Purpose:** Central API wrapper for train data providers

**Import:**
```python
from pyinrail.railway_api import (
    create_session,
    get_trains_between_stations,
    get_schedule_from_page,
)
```

**Key Components:**
- `create_session()` - Creates HTTP session with retry logic
- `get_trains_between_stations()` - Main train search function
- `get_ixigo_train_availability()` - Ixigo-specific availability data
- `get_schedule_from_page()` - Scrapes train schedules
- `validate_journey_date()` - Date validation
- Custom error class: `RailwayApiError`

**Supported Providers:**
- Ixigo (ixigo)
- RailYatri (railyatri)

**Dependencies:**
- `requests` - HTTP requests
- `urllib3` - Connection pooling

---

#### `pyinrail.split_journey` (611 lines) ⭐
**Purpose:** Core split journey search algorithm

**Import:**
```python
from pyinrail.split_journey import (
    find_same_train_split_journeys,
    extract_route_stops,
    parse_availability_status,
)
```

**Key Classes:**
```
RouteStop      → Represents a train stop (code, name, time)
Segment        → Represents a journey segment (from → to)
SplitJourneyError → Custom exception
```

**Key Functions:**
- `find_same_train_split_journeys()` - Main algorithm (410 lines!)
- `extract_route_stops()` - Parse schedule into stops
- `find_route_slice()` - Extract relevant stops
- `generate_split_segments()` - Create segment combinations
- `parse_availability_status()` - Classify availability (Available/RAC/WL)
- `is_acceptable_status()` - Check acceptability

**Algorithm Steps:**
1. Fetch train schedule
2. Extract stops between source and destination
3. Generate combinations from 2 to max_segments
4. Query availability for each combination
5. Filter by criteria (class, WL limit, RAC)
6. Rank by preference
7. Return top results

**Complexity:** O(2^n) reduced by early exit and caching

---

#### `stations.py` (90 lines)
**Purpose:** Station cache management and local search

**Key Functions:**
- `load_station_cache()` - Load JSON station database
- `search_station_local()` - Search by name/code with ranking
- Custom exception: `StationCacheError`

**Station Data Fields:**
- code - Station code (e.g., "MAS")
- name - Station name (e.g., "Chennai Central")
- zone - Railway zone
- state - State/territory

---

#### `formatters.py` (220 lines)
**Purpose:** Format output for CLI and terminal display

**Key Functions:**
- `format_station_results()` - Format station search output
- `format_train_info()` - Format train search results
- `format_schedule_info()` - Format timetable display
- `format_split_journey_results()` - Format split journey results
- `minutes_to_hhmm()` - Time conversion helper

**Features:**
- Table formatting
- Color support (if terminal supports)
- Readable time formats
- Availability status display

---

### User Interfaces

#### `rail_scrapper.py` (309 lines)
**Purpose:** Command-line interface for all operations

**Subcommands:**
```
station      Search stations
trains       Find trains between stations
schedule     View train schedule
split        Find split journey options
demo         Run demonstration
```

**Key Features:**
- Argument parsing with argparse
- Default values (configurable in code)
- CLI flag support
- Error handling

**Usage:**
```bash
python rail_scrapper.py split --train 16021 --from MAS --to MYS --date 31-07-2026
```

---

#### `streamlit_app.py` (1114 lines)
**Purpose:** Interactive web application

**Features:**
- 🔍 Station search with autocomplete
- 🚆 Train search with availability matrix
- 📅 Schedule viewer with timeline
- 🎫 Split journey finder with visualization
- ⚙️ Advanced filtering panel
- 📊 Result ranking and scoring

**How to Run:**
```bash
streamlit run streamlit_app.py
```

Opens browser at `http://localhost:8501`

---

### Utilities

#### `create_station_cache.py`
**Purpose:** Generate `stations_cache.json`

**Function:**
- Fetches station list from railway API
- Caches locally for offline use
- Creates searchable index

**When to Run:**
- Setup: First time initialization
- Maintenance: Update station database monthly

**Run:**
```bash
python create_station_cache.py
```

---

#### `create_stations_endpoint.py`
**Purpose:** Create API endpoint for stations

**Generates:** `stations_endpoint.json`

**Use Cases:**
- External API integration
- Third-party app integration

---

### Data Files

#### `stations_cache.json`
**Content:** Pre-built station database (JSON array)

**Structure:**
```json
[
  {
    "code": "MAS",
    "name": "Chennai Central",
    "zone": "SR",
    "state": "Tamil Nadu"
  },
  ...
]
```

**Size:** ~500KB (includes 2000+ stations)

**Update:** Run `create_station_cache.py` to refresh

---

#### `stations_endpoint.json`
**Content:** Station API endpoint reference

**Format:** Same structure as cache.json

---

### Tests (`tests/`)

#### `test_split_journey.py`
Tests for split journey algorithm:
- Route stop extraction
- Segment generation
- Availability parsing
- Status filtering
- Result scoring

#### `test_railway_api.py`
Tests for API wrapper:
- Session creation
- Train search
- Availability fetching
- Error handling

#### `test_stations.py`
Tests for station management:
- Cache loading
- Local search
- Ranking logic

#### `test_formatters.py`
Tests for output formatting:
- Time conversion
- Text formatting
- Special cases

#### `test_cli.py`
Tests for CLI interface:
- Argument parsing
- Command execution
- Error handling

---

## Data Flow

### Split Journey Search Flow

```
User Input
    ↓
cli (rail_scrapper.py) or Web (streamlit_app.py)
    ↓
split_journey.find_same_train_split_journeys()
    ├─ Fetch schedule via railway_api.get_schedule_from_page()
    ├─ Extract stops: split_journey.extract_route_stops()
    ├─ Generate segments: split_journey.generate_split_segments()
    └─ For each segment combination:
       ├─ Query availability via railway_api.get_trains_between_stations()
       ├─ Parse status: split_journey.parse_availability_status()
       ├─ Check acceptability: split_journey.is_acceptable_status()
       └─ Score result: split_journey._result_score()
    ↓
Ranked Results
    ↓
formatters (format_split_journey_results)
    ↓
Display to User (CLI table or Web UI)
```

### Station Search Flow

```
User Query
    ↓
stations.load_station_cache() → Load JSON
    ↓
stations.search_station_local(query, cache, limit)
    ├─ Normalize query
    ├─ Match by code (exact)
    ├─ Match by code (prefix)
    ├─ Match by name (substring)
    ├─ Sort by score and index
    └─ Return top N
    ↓
formatters.format_station_results()
    ↓
Display to User
```

## Development Workflow

### Adding a New Feature

1. **Identify Module**
   - Core logic → `split_journey.py` or `railway_api.py`
   - UI → `streamlit_app.py` or `rail_scrapper.py`
   - Utilities → `formatters.py` or new utility file

2. **Write Tests First** (`tests/`)
   ```python
   def test_new_feature():
       result = new_function(input)
       assert result == expected
   ```

3. **Implement Feature**
   ```python
   def new_function(param: str) -> dict:
       """Description."""
       # Implementation
   ```

4. **Update Docs**
   - Add docstring
   - Update README if user-facing
   - Add CHANGELOG entry

5. **Run Tests**
   ```bash
   pytest tests/ -v
   black *.py
   pylint *.py
   ```

6. **Commit**
   ```bash
   git add .
   git commit -m "[Feature] Description"
   ```

## Performance Considerations

### Algorithm Complexity
- **Time:** O(2^n) where n = number of stops
  - Mitigated by: Early exit, max_segments limit, caching
  - Typical: 50-100 stops → 100-500 combinations checked
  - Time: 2-5 seconds typical

- **Space:** O(n) for stops + cache
  - ~1MB for typical search

### Optimization Opportunities
- [ ] Parallel segment queries
- [ ] Redis caching of API responses
- [ ] Database indexing of historical data
- [ ] Query result pre-filtering at API level

## Dependency Management

### Core Dependencies
```
requests>=2.31.0       # HTTP client (railway_api.py)
streamlit>=1.36.0      # Web framework (streamlit_app.py)
pandas>=2.2.0          # Data manipulation (formatters.py)
```

### Development Dependencies (not in requirements.txt)
```
pytest                 # Testing
pytest-cov             # Coverage
black                  # Formatting
pylint                 # Linting
mypy                   # Type checking
```

## Configuration & Customization

### Hardcoded Defaults (in `rail_scrapper.py`)
```python
DEFAULT_COMMAND = "split"
DEFAULT_FROM_STATION = "MAS"
DEFAULT_TO_STATION = "MYS"
DEFAULT_JOURNEY_DATE = "31-07-2026"
DEFAULT_SPLIT_CLASSES = "SL,3A,2A"
DEFAULT_SPLIT_MAX_SEGMENTS = 3
DEFAULT_SPLIT_MAX_WL = 20
DEFAULT_SPLIT_MAX_RESULTS = 10
DEFAULT_SPLIT_ACCEPT_RAC = True
```

Edit these to change defaults.

### CLI Flags
All defaults can be overridden:
```bash
python rail_scrapper.py split \
  --train 16021 \
  --from MAS \
  --to MYS \
  --date 31-07-2026 \
  --classes SL,3A,2A \
  --max-segments 4
```

## Troubleshooting Guide

### Import Errors
```
ModuleNotFoundError: No module named 'streamlit'
```
**Solution:** Run `pip install -r requirements.txt`

### Station Cache Error
```
Station cache not found: .../stations_cache.json
```
**Solution:** Run `python create_station_cache.py`

### API Connection Error
```
RailwayApiError: Request failed for https://...
```
**Solution:**
- Check internet connection
- Try different provider (railyatri vs ixigo)
- Increase timeout parameter

### Split Journey Timeout
**Solution:**
- Reduce `max_segments`
- Reduce number of classes
- Increase timeout value

## Git Workflow

### Before Committing
```bash
# Ensure clean state
git status

# Stage changes
git add .

# Run tests
pytest tests/ -v

# Format code
black *.py

# Lint
pylint *.py

# Commit
git commit -m "[Type] Description"

# Push
git push origin branch-name
```

### .gitignore Coverage
Excludes:
- ✓ `__pycache__/` and `.pyc` files
- ✓ `.venv/` virtual environment
- ✓ `.pytest_cache/` test artifacts
- ✓ IDE settings (`.vscode/`, `.idea/`)
- ✓ OS files (`Thumbs.db`, `.DS_Store`)
- ✓ `.env` files with secrets

**Does NOT exclude** (intentionally committed):
- ✓ `stations_cache.json` (essential for offline use)
- ✓ `stations_endpoint.json` (reference data)
- ✓ `requirements.txt` (dependency definition)

---

## Quick Reference

### File Sizes
- `streamlit_app.py` - 1114 lines (largest, UI)
- `split_journey.py` - 611 lines (core algorithm)
- `railway_api.py` - 633 lines (API wrapper)
- `rail_scrapper.py` - 309 lines (CLI)
- Others - < 300 lines

### Total Lines of Code
- **Production Code:** ~3200 lines
- **Tests:** ~1500 lines
- **Ratio:** ~2:1 (good test coverage)

### API Endpoints Used
- RailYatri: Train search, Schedule fetching
- Ixigo: Train search, Availability fetching
- Both: Real-time data, no auth required

---

**Last Updated:** July 11, 2026
**Python:** 3.8+
**Status:** Production Ready ✅
