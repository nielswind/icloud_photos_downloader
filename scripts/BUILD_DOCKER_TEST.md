# build_docker_test

Builds a Docker image from the current branch and pushes it to the GitHub Container Registry (GHCR) for manual testing.

## Prerequisites

- Docker with [buildx](https://docs.docker.com/buildx/working-with-buildx/) support (included in Docker Desktop and Docker Engine ≥ 19.03)
- A GitHub account
- A GitHub Personal Access Token (PAT) — see [Setup](#setup) below

## Setup

### Create a GitHub Personal Access Token

1. Go to **github.com → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **Generate new token (classic)**
3. Give it a name (e.g. `icloudpd-docker-test`)
4. Select the following scopes:
   - `write:packages`
   - `read:packages`
5. Click **Generate token** and copy the value — you will not see it again

You can either export it as an environment variable to avoid being prompted each run:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

Or leave it unset and the script will prompt for it securely (input is hidden).

## Usage

Run from the repository root:

```bash
# Prompt for both username and PAT
./scripts/build_docker_test

# Pass username as argument; PAT read from GITHUB_TOKEN env var
GITHUB_TOKEN=ghp_xxxx ./scripts/build_docker_test YOUR_GITHUB_USERNAME
```

## What it does

| Step | Description |
|------|-------------|
| 1 | Creates (or reuses) a Docker buildx builder named `icloudpd-builder` |
| 2 | Builds static `linux/amd64` binaries inside Docker using `Dockerfile.build-musl` and outputs them to `dist/` |
| 3 | Renames the binaries to match the pattern `Dockerfile` expects (e.g. `icloud-1.32.2-linux-musl-amd64`) |
| 4 | Logs in to `ghcr.io` using your GitHub username and PAT |
| 5 | Builds the final Alpine-based runtime image using `Dockerfile` and pushes it to GHCR |

## Output image

The image is tagged based on the current branch name (with `/` replaced by `-`):

```
ghcr.io/<YOUR_GITHUB_USERNAME>/icloud_photos_downloader:<branch-name>
```

For example, on branch `fix/notify-before-password-status-clear`:

```
ghcr.io/yourname/icloud_photos_downloader:fix-notify-before-password-status-clear
```

## Testing the image

After the script completes:

```bash
# Verify the binary runs
docker run --rm ghcr.io/yourname/icloud_photos_downloader:fix-notify-before-password-status-clear icloudpd --version

# Run icloudpd
docker run --rm -v "$HOME/Photos:/data" \
  ghcr.io/yourname/icloud_photos_downloader:fix-notify-before-password-status-clear \
  icloudpd --directory /data --username your@email.com

# Run icloud
docker run --rm \
  ghcr.io/yourname/icloud_photos_downloader:fix-notify-before-password-status-clear \
  icloud --username your@email.com
```

## Image visibility

The package is created as **private** by default on first push. To make it public:

1. Go to **github.com → Your profile → Packages**
2. Select `icloud_photos_downloader`
3. Go to **Package settings → Change visibility → Public**
