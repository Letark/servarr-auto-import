#!/usr/bin/env python3
"""Polls Sonarr/Radarr for importBlocked items with valid grab history and auto-imports them."""

import html
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("auto-import")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "120"))
SONARR_URL = os.environ.get("SONARR_URL", "").rstrip("/")
SONARR_API_KEY = os.environ.get("SONARR_API_KEY", "")
RADARR_URL = os.environ.get("RADARR_URL", "").rstrip("/")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "")

ID_MATCH_PHRASES = [
    "matched to series by id",
    "matched to movie by id",
]


def api(base_url, key, path, method="GET", body=None):
    sep = "&" if "?" in path else "?"
    url = f"{base_url}{path}{sep}apikey={key}"
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.error("HTTP %s on %s %s", e.code, method, path)
        return None
    except Exception as e:
        log.error("Request failed: %s %s — %s", method, path, e)
        return None


def is_id_matched_block(record):
    for msg in record.get("statusMessages", []):
        for m in msg.get("messages", []):
            if any(p in m.lower() for p in ID_MATCH_PHRASES):
                return True
    return False


def clean_title(record):
    return html.unescape(record.get("title", "?"))


# ── Sonarr ──────────────────────────────────────────────────────────────────


def process_sonarr():
    if not SONARR_URL or not SONARR_API_KEY:
        return
    data = api(SONARR_URL, SONARR_API_KEY, "/api/v3/queue?page=1&pageSize=200&includeUnknownSeriesItems=true")
    if not data:
        return
    blocked = [r for r in data.get("records", []) if r.get("trackedDownloadState") == "importBlocked" and is_id_matched_block(r)]
    if not blocked:
        return
    # Deduplicate by downloadId — season packs create one record per episode
    seen = {}
    for r in blocked:
        did = r.get("downloadId", "")
        if did and did not in seen:
            seen[did] = r
    log.info("Sonarr: %d blocked import(s) to process", len(seen))
    for did, record in seen.items():
        sonarr_import(record)


def sonarr_import(record):
    title = clean_title(record)
    series_id = record.get("seriesId")
    download_id = record.get("downloadId", "")
    if not series_id:
        log.warning("Sonarr: no seriesId for '%s', skipping", title)
        return
    # Get the output path from the queue record
    output_path = html.unescape(record.get("outputPath", ""))
    if not output_path:
        log.warning("Sonarr: no outputPath for '%s', skipping", title)
        return
    # Use manual import scan to get file details with correct series context
    items = api(SONARR_URL, SONARR_API_KEY, f"/api/v3/manualimport?folder={urllib.request.quote(output_path, safe='')}&seriesId={series_id}&filterExistingFiles=true")
    if not items:
        log.warning("Sonarr: manual import scan returned nothing for '%s'", title)
        return
    files = []
    for item in items:
        episodes = item.get("episodes", [])
        if not episodes or item.get("rejections"):
            continue
        files.append({
            "path": item["path"],
            "seriesId": series_id,
            "seasonNumber": item.get("seasonNumber"),
            "episodeIds": [e["id"] for e in episodes],
            "quality": item.get("quality", {}),
            "language": item.get("language") or item.get("languages", [{}])[0] if item.get("languages") else {"id": 1, "name": "English"},
            "indexerFlags": item.get("indexerFlags", 0),
            "releaseType": item.get("releaseType", "unknown"),
        })
    if not files:
        log.warning("Sonarr: no importable files found for '%s'", title)
        return
    result = api(SONARR_URL, SONARR_API_KEY, "/api/v3/command", method="POST", body={
        "name": "ManualImport",
        "files": files,
        "importMode": "move",
    })
    if result:
        log.info("Sonarr: triggered import for '%s' (%d file(s))", title, len(files))
    else:
        log.error("Sonarr: failed to trigger import for '%s'", title)


# ── Radarr ──────────────────────────────────────────────────────────────────


def process_radarr():
    if not RADARR_URL or not RADARR_API_KEY:
        return
    data = api(RADARR_URL, RADARR_API_KEY, "/api/v3/queue?page=1&pageSize=200&includeUnknownMovieItems=true")
    if not data:
        return
    blocked = [r for r in data.get("records", []) if r.get("trackedDownloadState") == "importBlocked" and is_id_matched_block(r)]
    if not blocked:
        return
    log.info("Radarr: %d blocked import(s) to process", len(blocked))
    for record in blocked:
        radarr_import(record)


def radarr_import(record):
    title = clean_title(record)
    movie_id = record.get("movieId")
    if not movie_id:
        log.warning("Radarr: no movieId for '%s', skipping", title)
        return
    output_path = html.unescape(record.get("outputPath", ""))
    if not output_path:
        log.warning("Radarr: no outputPath for '%s', skipping", title)
        return
    items = api(RADARR_URL, RADARR_API_KEY, f"/api/v3/manualimport?folder={urllib.request.quote(output_path, safe='')}&movieId={movie_id}&filterExistingFiles=true")
    if not items:
        log.warning("Radarr: manual import scan returned nothing for '%s'", title)
        return
    files = []
    for item in items:
        if item.get("rejections") or not item.get("movie"):
            continue
        files.append({
            "path": item["path"],
            "movieId": movie_id,
            "quality": item.get("quality", {}),
            "language": item.get("language") or (item.get("languages", [{}])[0] if item.get("languages") else {"id": 1, "name": "English"}),
            "indexerFlags": item.get("indexerFlags", 0),
        })
    if not files:
        log.warning("Radarr: no importable files found for '%s'", title)
        return
    result = api(RADARR_URL, RADARR_API_KEY, "/api/v3/command", method="POST", body={
        "name": "ManualImport",
        "files": files,
        "importMode": "move",
    })
    if result:
        log.info("Radarr: triggered import for '%s' (%d file(s))", title, len(files))
    else:
        log.error("Radarr: failed to trigger import for '%s'", title)


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    apps = []
    if SONARR_URL and SONARR_API_KEY:
        apps.append("Sonarr")
    if RADARR_URL and RADARR_API_KEY:
        apps.append("Radarr")
    if not apps:
        log.error("No apps configured. Set SONARR_URL/SONARR_API_KEY and/or RADARR_URL/RADARR_API_KEY.")
        sys.exit(1)
    log.info("Starting auto-import for %s (poll every %ds)", ", ".join(apps), POLL_INTERVAL)
    while True:
        try:
            process_sonarr()
            process_radarr()
        except Exception:
            log.exception("Unexpected error in poll loop")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
