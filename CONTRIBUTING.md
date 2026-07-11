# Contributing to PyInRail

Thank you for your interest in contributing to PyInRail! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help others learn and grow

## Getting Started

### 1. Fork & Clone

```bash
# Fork the repository on GitHub
# Clone your fork
git clone https://github.com/YOUR-USERNAME/pyinrail.git
cd pyinrail

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL-OWNER/pyinrail.git
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies with dev tools
pip install -r requirements.txt
pip install pytest pytest-cov black pylint mypy
```

### 3. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

## Development Workflow

### Writing Code

1. **Follow PEP 8** - Use type hints where possible
   ```python
   def find_routes(
       from_station: str,
       to_station: str,
       max_results: int = 10,
   ) -> list[dict[str, Any]]:
       """Search routes between stations."""
   ```

2. **Add Docstrings** - Explain what functions do
   ```python
   def parse_availability_status(status: Any) -> dict[str, Any]:
       """Classify availability text from RailYatri/Ixigo into a sortable shape.
       
       Args:
           status: Raw availability string from API
           
       Returns:
           Dict with 'status', 'kind', 'count', and 'rank' keys
       """
   ```

3. **Keep Functions Focused** - Single responsibility principle
4. **Use Descriptive Names** - `find_available_segments` not `get_data`

### Testing

**Write tests for new features:**

```python
# tests/test_new_feature.py
import pytest
from new_module import new_function

def test_new_function_basic():
    """Test basic functionality."""
    result = new_function("test_input")
    assert result == "expected_output"

def test_new_function_edge_case():
    """Test edge cases."""
    with pytest.raises(ValueError):
        new_function(None)
```

**Run tests:**

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_split_journey.py::test_find_split_journeys -v

# Generate coverage report
pytest tests/ --cov=. --cov-report=html
```

### Code Quality

**Format code with Black:**
```bash
black *.py
```

**Check with Pylint:**
```bash
pylint *.py
```

**Type checking with mypy:**
```bash
mypy *.py --ignore-missing-imports
```

## Commit Guidelines

### Commit Messages

Use clear, descriptive commit messages:

```
[Feature] Add split journey depth-first search
- Implement `search_deeper` parameter
- Add test cases for new algorithm
- Update documentation

Fixes #123
```

**Format:**
- Type: [Feature], [Fix], [Docs], [Test], [Refactor], [Performance]
- Clear subject line (50 chars max)
- Detailed body if needed
- Reference issues with `Fixes #123` or `Related to #456`

### Don't Commit

- `__pycache__/` directories
- `.venv/` or other virtual environments
- API keys or secrets
- Generated cache files (unless intentional)
- IDE settings

## Pull Request Process

### 1. Prepare Your PR

```bash
# Sync with main branch
git fetch upstream
git rebase upstream/main

# Run tests locally
pytest tests/ -v
black *.py
pylint *.py
```

### 2. Push & Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub with:

**Title:** `[Type] Brief description`
- Example: `[Feature] Implement split journey depth search`

**Description:**
```markdown
## Description
Brief explanation of what this PR does.

## Related Issue
Fixes #123

## Changes
- Change 1
- Change 2

## Testing
- [ ] Added unit tests
- [ ] Tested locally
- [ ] No breaking changes

## Screenshots (if applicable)
Attach images for UI changes.
```

### 3. Review & Iterate

- Address feedback promptly
- Keep commits clean (rebase if needed)
- Request re-review once changes are made

### 4. Merge

After approval, PR will be merged by maintainers.

## Areas Needing Contribution

### High Priority
- [ ] Support for more train data providers
- [ ] Performance optimization for large searches
- [ ] Better error handling and user feedback
- [ ] Expanded test coverage (target: 85%+)

### Medium Priority
- [ ] Support for return journeys
- [ ] Multi-train split journey (different trains)
- [ ] Caching layer for API responses
- [ ] Historical data analysis

### Low Priority
- [ ] Additional output formats (CSV, PDF)
- [ ] API documentation
- [ ] Example notebooks
- [ ] Docker support

## Documentation

### Updating README

If your changes affect usage:
1. Update README.md with new information
2. Update docstrings in code
3. Add examples if new feature

### Adding Examples

Create example scripts in `examples/` directory:

```python
# examples/split_journey_basic.py
"""Basic split journey search example."""

from railway_api import create_session
from split_journey import find_same_train_split_journeys

if __name__ == "__main__":
    session = create_session()
    results = find_same_train_split_journeys(
        train_number="16021",
        from_station="MAS",
        to_station="MYS",
        journey_date="31-07-2026",
        session=session,
    )
    print(results)
```

## Performance Considerations

- **Avoid nested loops** where possible (use combinations/itertools)
- **Cache API responses** when making multiple requests
- **Profile code** if adding time-intensive operations:
  ```bash
  python -m cProfile -s cumulative script.py
  ```
- **Test with large datasets** to catch performance issues

## API Integration

When adding new data providers:

1. Create wrapper function in `railway_api.py`
2. Follow existing naming conventions
3. Handle errors gracefully
4. Add to `SUPPORTED_TRAIN_SEARCH_PROVIDERS`
5. Document API endpoint details
6. Add tests

## Troubleshooting for Contributors

**Q: Tests pass locally but fail in CI**
- Ensure Python version matches (3.8+)
- Check for hardcoded paths
- Verify API endpoints are accessible

**Q: My PR conflicts with main**
```bash
git fetch upstream
git rebase upstream/main
# Resolve conflicts, then force push
git push origin feature/your-feature-name --force
```

**Q: How do I handle API changes?**
- Wrap in try-except
- Add fallback to previous format
- Document the change
- Bump version number

## Questions?

- Open a GitHub Issue with tag `[Question]`
- Check existing Issues/Discussions
- Review project documentation

---

**Thank you for contributing to PyInRail! 🎉**

Your efforts help make train ticket booking easier for everyone!
