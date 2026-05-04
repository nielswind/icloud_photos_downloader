# Build Guide

Steps to build and publish a Docker image from the current branch.

## 1. Install dependencies

```bash
./scripts/install_deps
```

Sets up the Python development environment with all required packages.

## 2. Run all quality checks

```bash
./scripts/run_all_checks
```

Runs in order: `format` → `lint` → `type_check` → `test`. Fix any failures before proceeding.

## 3. Build the Docker test image

```bash
./scripts/build_docker_test [GITHUB_USERNAME]
```

Builds a Docker image from the current branch and pushes it to GHCR. Requires:
- Docker with buildx support
- A GitHub PAT with `write:packages` and `read:packages` scopes (set as `GITHUB_TOKEN` env var or enter when prompted)

The image is tagged from the current branch name:
```
ghcr.io/<GITHUB_USERNAME>/icloud_photos_downloader:<branch-tag>
```

For example, on branch `fix/notify-before-password-status-clear`:
```
ghcr.io/<GITHUB_USERNAME>/icloud_photos_downloader:fix-notify-before-password-status-clear
```

See `scripts/BUILD_DOCKER_TEST.md` for full details including how to create a GitHub PAT.

## 4. Verify the image

```bash
docker pull ghcr.io/<GITHUB_USERNAME>/icloud_photos_downloader:<branch-tag>
docker run --rm ghcr.io/<GITHUB_USERNAME>/icloud_photos_downloader:<branch-tag> icloudpd --version
```

## Quick reference

| Script | Purpose |
|--------|---------|
| `./scripts/install_deps` | Install Python dependencies |
| `./scripts/run_all_checks` | Format, lint, type-check, and test |
| `./scripts/build_docker_test` | Build and push Docker image to GHCR |
