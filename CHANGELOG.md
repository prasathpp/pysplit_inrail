# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-11

### Added

#### Core Features
- **Split Journey Search** - Main feature to find booking opportunities by splitting long journeys into multiple segments on the same train
- **CLI Interface** (`rail_scrapper.py`) - Command-line tool with subcommands:
  - `station` - Search railway stations
  - `trains` - Find trains between stations with availability
  - `schedule` - View train timetables
  - `split` - Find split journey alternatives
  - `demo` - Run demonstration
- **Web Application** (`streamlit_app.py`) - Interactive Streamlit-based UI with:
  - Station search with autocomplete
  - Train search with real-time availability
  - Split journey finder with visual results
  - Advanced filtering options

#### Core Modules
- `railway_api.py` - API wrapper for RailYatri and Ixigo train data providers
  - Train search with multiple providers
  - Availability fetching
  - Schedule scraping
  - Session management with retry logic
- `split_journey.py` - Split journey algorithm implementation
  - Route stop parsing
  - Segment generation
  - Availability status classification
  - Result ranking and scoring
- `stations.py` - Station cache management with local search
- `formatters.py` - Output formatting for CLI and terminal display

#### Utilities
- `create_station_cache.py` - Generate station database cache
- `create_stations_endpoint.py` - Create station API endpoint
- Pre-built `stations_cache.json` with comprehensive station data

#### Documentation
- Comprehensive README with examples and API reference
- Contributing guidelines (CONTRIBUTING.md)
- LICENSE (MIT)
- This CHANGELOG

#### Testing
- Unit tests for all core modules:
  - `test_split_journey.py` - Split journey algorithm tests
  - `test_railway_api.py` - API wrapper tests
  - `test_stations.py` - Station search tests
  - `test_formatters.py` - Formatter tests
  - `test_cli.py` - CLI interface tests

#### Configuration
- Support for hardcoded defaults in `rail_scrapper.py`
- CLI argument parsing for all parameters
- Configurable quotas, classes, segments, and search depth

### Features Detail

#### Split Journey Search
- Generate all possible segment combinations up to max depth
- Check availability for each combination in parallel
- Filter by:
  - Availability status (Available, RAC, WL)
  - Waiting list position limit
  - Preferred travel classes
- Rank results by:
  - Fewest segments required
  - Best availability status
  - Preferred class match
- Return top N results

#### API Integration
- Support for Ixigo and RailYatri data providers
- Robust error handling with custom exceptions
- Session management with automatic retries
- Connection pooling for efficiency
- User-Agent rotation to avoid blocking

#### User Interface
- CLI with intuitive subcommand structure
- Streamlit web app with interactive components
- Formatted table output with color support
- Progress indicators for long-running searches

## Future Roadmap

### Planned Features (v1.1.0)
- [ ] Support for more train data providers
- [ ] Return journey search
- [ ] Multi-train split journeys
- [ ] API caching layer
- [ ] Historical availability analysis

### Performance Improvements (v1.2.0)
- [ ] Parallel segment availability checking
- [ ] Redis-based caching
- [ ] Database backend for historical data
- [ ] Query optimization

### UI Enhancements (v1.3.0)
- [ ] Mobile app version
- [ ] Export results to PDF
- [ ] Email notifications
- [ ] Price trend analysis
- [ ] Saved searches and preferences

## Known Issues

- API endpoints may change without notice
- Some availability data may have slight delays (5-10 minutes)
- Rate limiting on upstream servers for excessive requests
- Split journey results not guaranteed if waiting list positions exceed limits

## Project Structure

```
pyinrail-master/
├── railway_api.py           # Core API wrapper
├── split_journey.py         # Split journey algorithm
├── rail_scrapper.py         # CLI interface
├── streamlit_app.py         # Web UI
├── stations.py              # Station management
├── formatters.py            # Output formatting
├── create_station_cache.py  # Cache generation
├── create_stations_endpoint.py
├── stations_cache.json      # Station database
├── requirements.txt         # Dependencies
├── tests/                   # Unit tests
├── README.md               # Documentation
├── CONTRIBUTING.md         # Contribution guide
├── LICENSE                 # MIT License
├── CHANGELOG.md           # This file
└── .gitignore             # Git ignore rules
```

## Dependencies

Core dependencies:
- `requests>=2.31.0` - HTTP client library
- `streamlit>=1.36.0` - Web framework for UI
- `pandas>=2.2.0` - Data manipulation

Development dependencies:
- `pytest` - Testing framework
- `pytest-cov` - Code coverage
- `black` - Code formatter
- `pylint` - Code quality checker
- `mypy` - Static type checker

## Version History

### v1.0.0 (2026-07-11)
- Initial release
- Core split journey search functionality
- CLI and web UI interfaces
- Comprehensive documentation
- Full test coverage

---

## How to File a Bug Report

When reporting bugs, please include:
1. Python version
2. Operating system
3. Steps to reproduce
4. Expected behavior
5. Actual behavior
6. Error messages/tracebacks
7. Train number and date used (if applicable)

## How to Request a Feature

Describe:
1. What problem does it solve?
2. Why is this important?
3. How would users interact with it?
4. Any related issues or discussions

---

**Last Updated:** July 11, 2026
