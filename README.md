# servarr-auto-import

[![Build and Publish Docker Image](https://github.com/Letark/servarr-auto-import/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Letark/servarr-auto-import/actions/workflows/docker-publish.yml)
[![GitHub release](https://img.shields.io/github/v/release/Letark/servarr-auto-import)](https://github.com/Letark/servarr-auto-import/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/letark/servarr-auto-import)](https://hub.docker.com/r/letark/servarr-auto-import)
[![Docker Image](https://img.shields.io/badge/ghcr.io-letark-blue)](https://github.com/Letark/servarr-auto-import/pkgs/container/servarr-auto-import)

Automatically imports downloads that Sonarr, Radarr, and Lidarr refuse to import because the release was matched by indexer ID instead of filename.

> **Created by [Kiro](https://kiro.dev)** — an AI software development assistant — in collaboration with the Letark homelab project.

---

## The problem

When [Prowlarr](https://prowlarr.com) sends a release to Sonarr/Radarr/Lidarr using an indexer ID (TVDB, IMDB, TMDB, etc.), the *arr app grabs it successfully. But when the download completes, the app refuses to auto-import because the **filename alone doesn't confirm the match** — even though the grab history proves it's correct.

You see this in your queue:

> *Found matching series via grab history, but release was matched to series by ID. Automatic import is not possible.*

This is especially common with:
- **Usenet** downloads via Newznab indexers (NZBgeek, NZBFinder, etc.)
- Series with **country qualifiers** — "Love on the Spectrum (US)" vs "Love on the Spectrum"
- Series with **year suffixes** — "Guilt (2019)" vs "Guilt"
- Any release where the **filename differs from the *arr's series/movie title**

The *arr devs consider this a safety feature and have [declined to add a toggle](https://github.com/Sonarr/Sonarr/issues/4935). Existing tools like [Cleanuparr](https://github.com/Cleanuparr/Cleanuparr) and [Decluttarr](https://github.com/ManiMatter/decluttarr) handle this by **deleting the download and re-searching** — wasting bandwidth and indexer API hits.

**servarr-auto-import** takes a different approach: it **trusts the grab history and completes the import**.

---

## How it works

1. Polls the queue API for items with `trackedDownloadState: importBlocked`
2. Filters to **only** items blocked because of ID-based matching (confirmed by grab history)
3. Calls the manual import scan endpoint with the correct series/movie/artist ID
4. Triggers the `ManualImport` command with the resolved file details

It does **not** touch downloads blocked for other reasons (quality mismatches, missing files, permissions errors, etc.).

---

## Quick start

```yaml
services:
  servarr-auto-import:
    image: ghcr.io/letark/servarr-auto-import:latest
    container_name: servarr-auto-import
    restart: unless-stopped
    environment:
      - SONARR_URL=http://sonarr:8989
      - SONARR_API_KEY=your_sonarr_api_key
      - RADARR_URL=http://radarr:7878
      - RADARR_API_KEY=your_radarr_api_key
```

> **Note:** The container must be able to reach your *arr apps over the network. If your *arr apps run behind a VPN container (e.g., Gluetun), use `network_mode: service:gluetun` so they share the same network namespace.

---

## Configuration

All configuration is via environment variables. Configure only the apps you use.

| Variable | Required | Default | Description |
|---|---|---|---|
| `SONARR_URL` | No | — | Sonarr base URL (e.g. `http://sonarr:8989`) |
| `SONARR_API_KEY` | No | — | Sonarr API key |
| `RADARR_URL` | No | — | Radarr base URL (e.g. `http://radarr:7878`) |
| `RADARR_API_KEY` | No | — | Radarr API key |
| `LIDARR_URL` | No | — | Lidarr base URL (e.g. `http://lidarr:8686`) |
| `LIDARR_API_KEY` | No | — | Lidarr API key |
| `POLL_INTERVAL` | No | `120` | Seconds between queue checks |
| `DRY_RUN` | No | `false` | Log what would be imported without doing it |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

At least one app (Sonarr, Radarr, or Lidarr) must be configured.

### Finding your API key

In each *arr app: **Settings → General → API Key**

---

## Dry run mode

Set `DRY_RUN=true` to see what the tool would import without actually triggering any imports. Useful for verifying your setup.

```
2026-04-26 11:36:16 [INFO] Sonarr: [DRY RUN] would import 1 file(s) for 'Love.on.the.Spectrum.S04E01...'
```

---

## Network setup

### Standard Docker networking

If your *arr apps are on the same Docker network:

```yaml
services:
  servarr-auto-import:
    image: ghcr.io/letark/servarr-auto-import:latest
    environment:
      - SONARR_URL=http://sonarr:8989
      - SONARR_API_KEY=your_key
    networks:
      - your_network
```

### VPN / Gluetun setup

If your *arr apps share a VPN container's network (common with Gluetun), the auto-importer needs to be on the same network to reach `localhost` ports:

```yaml
services:
  servarr-auto-import:
    image: ghcr.io/letark/servarr-auto-import:latest
    network_mode: service:gluetun
    environment:
      - SONARR_URL=http://localhost:8989
      - SONARR_API_KEY=your_key
      - RADARR_URL=http://localhost:7878
      - RADARR_API_KEY=your_key
    depends_on:
      gluetun:
        condition: service_healthy
```

---

## Building locally

```bash
git clone https://github.com/Letark/servarr-auto-import.git
cd servarr-auto-import
docker build -t servarr-auto-import .
```

No external Python dependencies — uses only the standard library.

---

## Releases

Docker images are published to both [Docker Hub](https://hub.docker.com/r/letark/servarr-auto-import) and the [GitHub Container Registry](https://github.com/Letark/servarr-auto-import/pkgs/container/servarr-auto-import) on every tagged release, built for `linux/amd64` and `linux/arm64`.

```bash
# Docker Hub
docker pull letark/servarr-auto-import:latest

# GitHub Container Registry
docker pull ghcr.io/letark/servarr-auto-import:latest
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

- [Sonarr](https://sonarr.tv), [Radarr](https://radarr.video), [Lidarr](https://lidarr.audio) — the *arr apps this tool supports
- [Prowlarr](https://prowlarr.com) — the indexer manager that makes this issue common
- [Kiro](https://kiro.dev) — the AI assistant that designed and built this project
