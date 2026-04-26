FROM python:3.13-alpine

LABEL org.opencontainers.image.title="servarr-auto-import" \
      org.opencontainers.image.description="Auto-imports blocked Sonarr/Radarr/Lidarr downloads matched by indexer ID" \
      org.opencontainers.image.source="https://github.com/Letark/servarr-auto-import" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="0.1.0"

COPY auto_import.py /app/auto_import.py

CMD ["python3", "-u", "/app/auto_import.py"]
