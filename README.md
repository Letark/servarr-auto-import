# servarr-auto-import

Polls Sonarr and Radarr for `importBlocked` queue items that were matched by ID via grab history, and triggers manual import automatically.

This works around Sonarr/Radarr's refusal to auto-import when the release was matched to a series/movie by indexer ID rather than filename parsing (common with Prowlarr + Newznab/usenet indexers).

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SONARR_URL` | No | — | Sonarr base URL (e.g. `http://localhost:8989`) |
| `SONARR_API_KEY` | No | — | Sonarr API key |
| `RADARR_URL` | No | — | Radarr base URL (e.g. `http://localhost:7878`) |
| `RADARR_API_KEY` | No | — | Radarr API key |
| `POLL_INTERVAL` | No | `120` | Seconds between queue checks |

At least one app (Sonarr or Radarr) must be configured.

## How It Works

1. Polls the queue API for items with `trackedDownloadState: importBlocked`
2. Filters to only items blocked because of ID-based matching (safe — grab history confirms the match)
3. Calls the manual import scan endpoint with the correct series/movie ID
4. Triggers the `ManualImport` command with the resolved file details
