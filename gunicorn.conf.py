"""Gunicorn settings. Every value can be overridden with an env var."""
import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv('WEB_CONCURRENCY', min(multiprocessing.cpu_count() * 2 + 1, 4)))
# Threads keep workers responsive while a reel analysis waits on Instagram/Gemini.
worker_class = 'gthread'
threads = int(os.getenv('GUNICORN_THREADS', '4'))
# Reel analysis (yt-dlp + Gemini + geocoding) can take ~20s on a cold cache.
timeout = int(os.getenv('GUNICORN_TIMEOUT', '60'))
graceful_timeout = 30
keepalive = 5
# Recycle workers periodically to contain slow memory growth.
max_requests = 1000
max_requests_jitter = 100
accesslog = '-'
errorlog = '-'
forwarded_allow_ips = os.getenv('FORWARDED_ALLOW_IPS', '*')
