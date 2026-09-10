# LabTutor backend
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so a code change does not reinstall the world.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend

# Runs unprivileged. The manual PDF is mounted read-only at /app/manual.
RUN useradd --create-home --uid 10001 labtutor \
    && mkdir -p /app/manual \
    && chown -R labtutor:labtutor /app
USER labtutor

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

# Workers sized for ~70 concurrent students on one container. Most request
# time is spent awaiting the inference backend, so the async workers stay
# responsive; raise this only alongside the database pool in backend/db.py.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
