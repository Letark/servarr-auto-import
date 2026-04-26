#!/usr/bin/env python3
"""
servarr-auto-import

Polls Sonarr, Radarr, and Lidarr for downloads blocked by ID-based matching
and triggers manual import automatically.

When Prowlarr sends a release to an *arr app using an indexer ID (TVDB, IMDB,
etc.), the *arr app may refuse to auto-import because the filename alone doesn't
confirm the match. This tool trusts the grab history and completes the import.
"""

import html
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

__version__ = "0.1.0"

# ── Configuration ───────────────────────────────────────────────────────────

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "120"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

SONARR_URL = os.environ.get("SONARR_URL", "").rstrip("/")
SONARR_API_KEY = os.environ.get("SONARR_API_KEY", "")
RADARR_URL = os.environ.get("RADARR_URL", "").rstrip("/")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "")
LIDARR_URL = os.environ.get("LIDARR_URL", "").rstrip("/")
LIDARR_API_KEY = os.environ.get("LIDARR_API_KEY", "")

# Phrases in status messages that indicate an ID-based match block.
# These are the only blocks this tool will act on — they have a confirmed
# grab history match and are safe to import.
ID_MATCH_PHRASES = [
    "matched to series by id",
    "matched to movie by id",
    "matched to artist by id",
    "matched to album by id",
]

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("servarr-auto-import")

# ── HTTP helpers ────────────────────────────────────────────────────────────


def _request(url, method="GET", body=None, timeout=30):
    """Make an HTTP request and return parsed JSON, or None on failure."""
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        log.error("HTTP %s %s %s", exc.code, method, _redact_url(url))
        return None
    except Exception as exc:
        log.error("Request failed: %s %s — %s", method, _redact_url(url), exc)
        return None


def _redact_url(url):
    """Remove API key from URL for safe logging."""
    return url.split("apikey=")[0].rstrip("?&") + "..." if "apikey=" in url else url


def api(base_url, key, path, method="GET", body=None):
    """Call an *arr API endpoint."""
    sep = "&" if "?" in path else "?"
    url = f"{base_url}{path}{sep}apikey={key}"
    return _request(url, method=method, body=body)


# ── Shared helpers ──────────────────────────────────────────────────────────


def is_id_matched_block(record):
    """Check if a queue record is blocked specifically due to ID-based matching."""
    for msg in record.get("statusMessages", []):
        for text in msg.get("messages", []):
            if any(phrase in text.lower() for phrase in ID_MATCH_PHRASES):
                return True
    return False


def clean_title(record):
    """Return the record title with HTML entities decoded."""
    return html.unescape(record.get("title", "unknown"))


def get_output_path(record):
    """Return the decoded output path from a queue record."""
    raw = record.get("outputPath", "")
    return html.unescape(raw) if raw else ""


# ── Sonarr ──────────────────────────────────────────────────────────────────


def process_sonarr():
    """Check Sonarr queue for blocked imports and process them."""
    if not SONARR_URL or not SONARR_API_KEY:
        return

    data = api(SONARR_URL, SONARR_API_KEY,
               "/api/v3/queue?page=1&pageSize=200&includeUnknownSeriesItems=true")
    if not data:
        return

    blocked = [
        r for r in data.get("records", [])
        if r.get("trackedDownloadState") == "importBlocked"
        and is_id_matched_block(r)
    ]
    if not blocked:
        log.debug("Sonarr: no blocked imports found")
        return

    # Season packs create one queue record per episode — deduplicate by downloadId
    seen = {}
    for record in blocked:
        did = record.get("downloadId", "")
        if did and did not in seen:
            seen[did] = record

    log.info("Sonarr: found %d blocked import(s)", len(seen))

    for record in seen.values():
        _import_sonarr(record)


def _import_sonarr(record):
    """Trigger manual import for a blocked Sonarr download."""
    title = clean_title(record)
    series_id = record.get("seriesId")
    output_path = get_output_path(record)

    if not series_id:
        log.warning("Sonarr: skipping '%s' — no series ID", title)
        return
    if not output_path:
        log.warning("Sonarr: skipping '%s' — no output path", title)
        return

    log.info("Sonarr: processing '%s'", title)

    encoded_path = urllib.parse.quote(output_path, safe="")
    items = api(SONARR_URL, SONARR_API_KEY,
                f"/api/v3/manualimport?folder={encoded_path}"
                f"&seriesId={series_id}&filterExistingFiles=true")
    if not items:
        log.warning("Sonarr: no files returned for '%s'", title)
        return

    files = []
    for item in items:
        episodes = item.get("episodes", [])
        if not episodes or item.get("rejections"):
            continue
        languages = item.get("languages", [])
        files.append({
            "path": item["path"],
            "seriesId": series_id,
            "seasonNumber": item.get("seasonNumber"),
            "episodeIds": [e["id"] for e in episodes],
            "quality": item.get("quality", {}),
            "languages": languages if languages else [{"id": 1, "name": "English"}],
            "indexerFlags": item.get("indexerFlags", 0),
            "releaseType": item.get("releaseType", "unknown"),
        })

    if not files:
        log.warning("Sonarr: no importable files for '%s'", title)
        return

    if DRY_RUN:
        log.info("Sonarr: [DRY RUN] would import %d file(s) for '%s'", len(files), title)
        return

    result = api(SONARR_URL, SONARR_API_KEY, "/api/v3/command", method="POST", body={
        "name": "ManualImport",
        "files": files,
        "importMode": "move",
    })
    if result:
        log.info("Sonarr: imported %d file(s) for '%s'", len(files), title)
    else:
        log.error("Sonarr: import failed for '%s'", title)


# ── Radarr ──────────────────────────────────────────────────────────────────


def process_radarr():
    """Check Radarr queue for blocked imports and process them."""
    if not RADARR_URL or not RADARR_API_KEY:
        return

    data = api(RADARR_URL, RADARR_API_KEY,
               "/api/v3/queue?page=1&pageSize=200&includeUnknownMovieItems=true")
    if not data:
        return

    blocked = [
        r for r in data.get("records", [])
        if r.get("trackedDownloadState") == "importBlocked"
        and is_id_matched_block(r)
    ]
    if not blocked:
        log.debug("Radarr: no blocked imports found")
        return

    log.info("Radarr: found %d blocked import(s)", len(blocked))

    for record in blocked:
        _import_radarr(record)


def _import_radarr(record):
    """Trigger manual import for a blocked Radarr download."""
    title = clean_title(record)
    movie_id = record.get("movieId")
    output_path = get_output_path(record)

    if not movie_id:
        log.warning("Radarr: skipping '%s' — no movie ID", title)
        return
    if not output_path:
        log.warning("Radarr: skipping '%s' — no output path", title)
        return

    log.info("Radarr: processing '%s'", title)

    encoded_path = urllib.parse.quote(output_path, safe="")
    items = api(RADARR_URL, RADARR_API_KEY,
                f"/api/v3/manualimport?folder={encoded_path}"
                f"&movieId={movie_id}&filterExistingFiles=true")
    if not items:
        log.warning("Radarr: no files returned for '%s'", title)
        return

    files = []
    for item in items:
        if item.get("rejections") or not item.get("movie"):
            continue
        languages = item.get("languages", [])
        files.append({
            "path": item["path"],
            "movieId": movie_id,
            "quality": item.get("quality", {}),
            "languages": languages if languages else [{"id": 1, "name": "English"}],
            "indexerFlags": item.get("indexerFlags", 0),
        })

    if not files:
        log.warning("Radarr: no importable files for '%s'", title)
        return

    if DRY_RUN:
        log.info("Radarr: [DRY RUN] would import %d file(s) for '%s'", len(files), title)
        return

    result = api(RADARR_URL, RADARR_API_KEY, "/api/v3/command", method="POST", body={
        "name": "ManualImport",
        "files": files,
        "importMode": "move",
    })
    if result:
        log.info("Radarr: imported %d file(s) for '%s'", len(files), title)
    else:
        log.error("Radarr: import failed for '%s'", title)


# ── Lidarr ──────────────────────────────────────────────────────────────────


def process_lidarr():
    """Check Lidarr queue for blocked imports and process them."""
    if not LIDARR_URL or not LIDARR_API_KEY:
        return

    data = api(LIDARR_URL, LIDARR_API_KEY,
               "/api/v1/queue?page=1&pageSize=200&includeUnknownArtistItems=true")
    if not data:
        return

    blocked = [
        r for r in data.get("records", [])
        if r.get("trackedDownloadState") == "importBlocked"
        and is_id_matched_block(r)
    ]
    if not blocked:
        log.debug("Lidarr: no blocked imports found")
        return

    log.info("Lidarr: found %d blocked import(s)", len(blocked))

    for record in blocked:
        _import_lidarr(record)


def _import_lidarr(record):
    """Trigger manual import for a blocked Lidarr download."""
    title = clean_title(record)
    artist_id = record.get("artistId")
    album_id = record.get("albumId")
    output_path = get_output_path(record)

    if not artist_id:
        log.warning("Lidarr: skipping '%s' — no artist ID", title)
        return
    if not output_path:
        log.warning("Lidarr: skipping '%s' — no output path", title)
        return

    log.info("Lidarr: processing '%s'", title)

    encoded_path = urllib.parse.quote(output_path, safe="")
    items = api(LIDARR_URL, LIDARR_API_KEY,
                f"/api/v1/manualimport?folder={encoded_path}"
                f"&artistId={artist_id}&filterExistingFiles=true")
    if not items:
        log.warning("Lidarr: no files returned for '%s'", title)
        return

    files = []
    for item in items:
        if item.get("rejections"):
            continue
        entry = {
            "path": item["path"],
            "artistId": artist_id,
            "quality": item.get("quality", {}),
            "indexerFlags": item.get("indexerFlags", 0),
        }
        # Include album/track IDs if available from the scan
        if item.get("albumId"):
            entry["albumId"] = item["albumId"]
        if item.get("trackIds"):
            entry["trackIds"] = item["trackIds"]
        elif item.get("tracks"):
            entry["trackIds"] = [t["id"] for t in item["tracks"]]
        files.append(entry)

    if not files:
        log.warning("Lidarr: no importable files for '%s'", title)
        return

    if DRY_RUN:
        log.info("Lidarr: [DRY RUN] would import %d file(s) for '%s'", len(files), title)
        return

    result = api(LIDARR_URL, LIDARR_API_KEY, "/api/v1/command", method="POST", body={
        "name": "ManualImport",
        "files": files,
        "importMode": "move",
    })
    if result:
        log.info("Lidarr: imported %d file(s) for '%s'", len(files), title)
    else:
        log.error("Lidarr: import failed for '%s'", title)


# ── Main loop ───────────────────────────────────────────────────────────────


def main():
    apps = []
    if SONARR_URL and SONARR_API_KEY:
        apps.append("Sonarr")
    if RADARR_URL and RADARR_API_KEY:
        apps.append("Radarr")
    if LIDARR_URL and LIDARR_API_KEY:
        apps.append("Lidarr")

    if not apps:
        log.error("No apps configured. Set at least one of: "
                   "SONARR_URL/SONARR_API_KEY, RADARR_URL/RADARR_API_KEY, "
                   "LIDARR_URL/LIDARR_API_KEY")
        sys.exit(1)

    mode = "[DRY RUN] " if DRY_RUN else ""
    log.info("servarr-auto-import v%s — %smonitoring %s (every %ds)",
             __version__, mode, ", ".join(apps), POLL_INTERVAL)

    while True:
        try:
            process_sonarr()
            process_radarr()
            process_lidarr()
        except Exception:
            log.exception("Unexpected error in poll loop")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
