# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**iCloud Photos Downloader** (`icloudpd`) is a CLI tool that downloads photos and videos from Apple iCloud to local storage. It supports copy, sync (with `--auto-delete`), and move (with `--keep-icloud-recent-days`) operation modes.

## Commands

```bash
# Install dependencies
./scripts/install_deps

# Format code (run before committing)
./scripts/format

# Lint
./scripts/lint

# Type checking
./scripts/type_check

# Run all tests (auto-detects parallelism)
./scripts/test

# Run tests with explicit parallelism
./scripts/test 4

# Run a single test file
python -m pytest tests/test_authentication.py -v

# Run a specific test
python -m pytest tests/test_authentication.py::test_name -v

# Run all quality checks at once
./scripts/run_all_checks

# Build wheel
./scripts/build
```

Tests produce an HTML coverage report at `htmlcov/index.html`. **100% test coverage is required** for all PRs.

## Architecture

```
src/
├── icloudpd/         # Main application
├── pyicloud_ipd/     # Forked iCloud API client
├── foundation/       # Shared functional utilities
└── starters/         # Entry point scripts
```

### Key Modules

**`icloudpd/cli.py`** — CLI argument parsing and user config. Entry point is `cli()`.

**`icloudpd/base.py`** — Core business logic: photo enumeration, filtering, deduplication, status tracking, and orchestration of the download loop.

**`icloudpd/authentication.py`** — Authentication flows: 2FA/2SA handling, web UI server (Flask/waitress) for interactive auth, email notifications, keyring credential storage.

**`icloudpd/download.py`** — Asset downloading logic and file version handling.

**`icloudpd/autodelete.py`** — Sync mode: deletes local files that were removed from iCloud.

**`pyicloud_ipd/base.py`** — `PyiCloudService` class — the primary iCloud API client. This is a forked version of the `pyicloud` library maintained within this project.

**`foundation/`** — Functional programming utilities (compose, chain, predicates, optional handling) shared across modules.

### Authentication Flow

1. CLI parses credentials → `authentication.py` orchestrates
2. For interactive 2FA: Flask web server starts, sends email notification, waits for user input via web UI
3. Credentials cached via `keyring` and session cookies

### Test Infrastructure

Tests use **VCR.py** cassettes in `tests/vcr_cassettes/` to record/replay HTTP interactions. When adding tests for new API behavior, record cassettes with real iCloud traffic then scrub personal data.

## Code Standards

- **Python 3.10–3.13** compatibility required
- **Ruff** for formatting and linting (100-char line length)
- **mypy** with strict type checking enabled
- Tests must cover all new code paths; 100% coverage enforced by CI

## Changelog

Update `CHANGELOG.md` (Unreleased section) for every PR. Releases happen weekly on Fridays when changes are present.
