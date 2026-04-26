FROM python:3.13-alpine
COPY auto_import.py /app/auto_import.py
CMD ["python3", "-u", "/app/auto_import.py"]
