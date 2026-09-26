FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Build static files with production storage (hashed, compressed names).
RUN SECRET_KEY=build-only-not-secret python manage.py collectstatic --noinput \
    && useradd --create-home --uid 10001 app \
    && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.getenv('PORT', '8000')}/healthz/\", timeout=4)"

# Set RUN_MIGRATIONS=0 if your platform runs migrations as a separate release step.
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS:-1}\" = \"1\" ]; then python manage.py migrate --noinput; fi && exec gunicorn config.wsgi"]
