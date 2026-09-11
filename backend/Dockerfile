FROM python:3.11-slim

# Prevents Python from buffering stdout/stderr -- Railway needs unbuffered
# logs to show up in real time.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg2 + pdfplumber (needs a couple of image libs).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Railway injects $PORT at runtime; default to 8000 for local docker run.
ENV PORT=8000
EXPOSE 8000

# --- Persistence fix (see README: "Login persistence -- root cause & fix") ---
# /app/data is where a volume should be mounted in any environment that
# needs data to survive a restart/redeploy. If DATABASE_URL is left on its
# SQLite default, point it here rather than a bare relative path so it lands
# on the mounted volume instead of the container's throwaway layer.
RUN mkdir -p /app/data


# Runs as a non-root user for defense in depth.
RUN useradd --create-home appuser && chown -R appuser:appuser /app/data
USER appuser

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
