# Contributing to Crypt Master

Thank you for your interest in contributing to Crypt Master! This document provides guidelines for contributing to the project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors. Please read our [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:
- A clear, descriptive title
- Steps to reproduce the issue
- Expected vs actual behavior
- Your environment (OS, Python version)
- Any relevant logs or screenshots

### Suggesting Features

Feature suggestions are welcome! Please create an issue with:
- A clear description of the feature
- Use cases and benefits
- Any implementation ideas you have

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests: `uv run pytest`
5. Run linting: `uv run ruff check .`
6. Commit your changes with [Conventional Commits](https://www.conventionalcommits.org/)
7. Push to your fork
8. Open a Pull Request to the `main` branch

#### Commit Message Format

We use Conventional Commits for automatic versioning:

```
feat: add new technical indicator
fix: correct RSI calculation for edge cases
docs: update API documentation
test: add property tests for signal generator
refactor: simplify bot agent logic
perf: optimize market data fetching
```

#### PR Guidelines

- Keep changes focused and atomic
- Include tests for new functionality
- Update documentation as needed
- Follow the existing code style (ruff)
- Ensure all tests pass
- PRs require review before merging

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/crypt-master.git
cd crypt-master

# Install dependencies with dev tools
uv sync --extra dev

# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Run type checking
uv run mypy .

# Start development server
uv run python manage.py runserver
```

## Testing

We use pytest and hypothesis for testing:

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run property-based tests only
uv run pytest tests/property/

# Run unit tests only
uv run pytest tests/unit/
```

## Code Style

- Follow PEP 8 guidelines (enforced by ruff)
- Use type hints on all function signatures
- Write docstrings for public APIs
- Keep functions focused and testable
- Line length: 100 characters

## Questions?

Feel free to open an issue for any questions about contributing!
