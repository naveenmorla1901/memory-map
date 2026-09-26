"""
Django settings for Memory Map.

Every environment-specific value comes from environment variables (loaded
from a local .env in development) - see .env.example for the full list.
The defaults are safe for production: DEBUG is off unless explicitly
enabled, and a real SECRET_KEY is required whenever DEBUG is off.
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name: str, default: str = '') -> list:
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


# --- Core ---------------------------------------------------------------

DEBUG = env_bool('DEBUG', False)

SECRET_KEY = os.getenv('SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('SECRET_KEY must be set when DEBUG is off.')
    SECRET_KEY = 'django-insecure-development-only-key-do-not-use-in-production'

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '*' if DEBUG else '')

# Public base URL of this server, used to build absolute links in emails
# (password reset) and the web pages. No trailing slash.
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8002').rstrip('/')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',

    'apps.core.apps.CoreConfig',
    'apps.users.apps.UsersConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site',
            ],
        },
    },
]

# --- Database -----------------------------------------------------------
# DATABASE_URL, e.g. postgres://user:pass@host:5432/memorymap. Falls back
# to a local SQLite file, which is fine for development only.

DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.getenv('DB_CONN_MAX_AGE', '60')),
        conn_health_checks=True,
    )
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Cache --------------------------------------------------------------
# Used for API throttling and geocoding results. With more than one server
# process, set REDIS_URL so throttle counts are shared between them.

REDIS_URL = os.getenv('REDIS_URL', '')
if REDIS_URL:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': REDIS_URL}}
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# --- Auth ---------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

if len(sys.argv) > 1 and sys.argv[1] == 'test':
    # Real hashers are deliberately slow; tests don't need that.
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

AUTHENTICATION_BACKENDS = [
    'apps.users.backends.EmailOrUsernameModelBackend',
]

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_MINUTES', '30'))),
    # Long-lived so mobile users aren't signed out whenever they don't open
    # the app for a day; rotation + blacklisting limits a leaked token's life.
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '30'))),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

PASSWORD_RESET_TIMEOUT = 60 * 60 * 24  # seconds

# --- REST framework -----------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_RENDERER_CLASSES': ('rest_framework.renderers.JSONRenderer',),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('THROTTLE_ANON', '60/min'),
        'user': os.getenv('THROTTLE_USER', '300/min'),
        # Login/register/password reset - slows credential stuffing.
        'auth': os.getenv('THROTTLE_AUTH', '10/min'),
        # Each reel analysis costs a yt-dlp fetch and a Gemini call.
        'reel_analysis': os.getenv('THROTTLE_REEL_ANALYSIS', '30/hour'),
        # Proxied to a shared public geocoder - be a good citizen.
        'geocode': os.getenv('THROTTLE_GEOCODE', '60/min'),
    },
    'EXCEPTION_HANDLER': 'apps.core.exceptions.api_exception_handler',
    # How many reverse proxies sit in front of the app (e.g. 1 behind a PaaS
    # load balancer). Rate limits use it to find the real client IP.
    'NUM_PROXIES': int(os.getenv('NUM_PROXIES', '0')) or None,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Memory Map API',
    'DESCRIPTION': 'Save places you want to remember - by hand, or straight from an Instagram reel.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}
# Interactive API docs at /api/docs/. Off in production unless enabled.
API_DOCS_ENABLED = env_bool('API_DOCS_ENABLED', DEBUG)

# --- CORS / CSRF --------------------------------------------------------
# The mobile app doesn't need CORS; this only matters for a browser client.

CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', PUBLIC_BASE_URL if PUBLIC_BASE_URL.startswith('https') else '')

# --- Security (production) ----------------------------------------------

if not DEBUG:
    # Most PaaS hosts terminate TLS at a proxy and forward this header.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
    SECURE_REDIRECT_EXEMPT = [r'^healthz/?$']
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', str(60 * 60 * 24 * 30)))
    # Opt-in: these affect every subdomain / are hard to undo.
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
    SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', False)
    SILENCED_SYSTEM_CHECKS = [
        check for check, enabled in (('security.W005', SECURE_HSTS_INCLUDE_SUBDOMAINS),
                                     ('security.W021', SECURE_HSTS_PRELOAD))
        if not enabled
    ]
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# --- Email --------------------------------------------------------------
# Printed to the console unless EMAIL_HOST is set.

EMAIL_HOST = os.getenv('EMAIL_HOST', '')
if EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Memory Map <no-reply@memorymap.local>')
SUPPORT_EMAIL = os.getenv('SUPPORT_EMAIL', 'support@memorymap.local')

# --- Static files -------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
        if DEBUG else 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# --- I18N ---------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# --- Admin --------------------------------------------------------------
# Move the admin off the well-known /admin/ path in production.

ADMIN_URL = os.getenv('ADMIN_URL', 'admin/').strip('/') + '/'

# --- Integrations -------------------------------------------------------

# Gemini API key for extracting places from reel captions. Optional - without
# it, reel analysis falls back to "pick the place manually".
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')

# Set to false to turn off reel analysis entirely (e.g. while you evaluate
# Instagram's terms for your deployment) - the share flow then goes straight
# to manual place search.
REEL_ANALYSIS_ENABLED = env_bool('REEL_ANALYSIS_ENABLED', True)

# Optional Netscape-format cookies.txt from a logged-in Instagram session,
# passed to yt-dlp. Reading works anonymously for many public reels, but a
# session is much more reliable. See README.
INSTAGRAM_YTDLP_COOKIES_FILE = os.getenv('INSTAGRAM_YTDLP_COOKIES_FILE', '')

# Geocoder (Photon API - https://github.com/komoot/photon). The public
# instance is free for fair use; point this at your own instance for heavy
# traffic. Results are cached server-side.
GEOCODER_BASE_URL = os.getenv('GEOCODER_BASE_URL', 'https://photon.komoot.io').rstrip('/')
GEOCODER_USER_AGENT = os.getenv('GEOCODER_USER_AGENT', f'MemoryMap/1.0 (+{PUBLIC_BASE_URL})')
GEOCODER_CACHE_SECONDS = int(os.getenv('GEOCODER_CACHE_SECONDS', str(60 * 60 * 24 * 7)))

# --- Logging ------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {'format': '{levelname} {asctime} {name} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'default'},
    },
    'root': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
    'loggers': {
        'django.db.backends': {'level': 'WARNING'},
    },
}
