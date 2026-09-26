# Memory Map backend

The API behind the [Memory Map app](https://github.com/naveenmorla1901/memory-map-v0): share an
Instagram reel to the app, it finds the places the reel mentions, and you save them to your map.

Django 5.2 LTS · Django REST Framework · JWT auth · Postgres · yt-dlp · Gemini · Photon (OpenStreetMap)

## What it does

- **Accounts** - sign up with name/email/password, email-or-username login, JWT access + rotating
  refresh tokens, sign out, change password (signs out other devices), password reset by email,
  profile edits, and account deletion from the app or the web (required by both app stores).
- **Saved places** - each user's own places with category, notes, favorite/visited flags and
  nearby-alert settings; search, filter, sort, bulk save, and stats.
- **Reel analysis** - `POST /api/v1/reels/analyze/` reads the reel's caption with yt-dlp, asks
  Gemini for the specific places it names, and finds each on the map. Results are cached per reel,
  so a viral reel shared by thousands of people is analyzed once.
- **Place search** - a server-side proxy to Photon (OpenStreetMap search) with caching and rate
  limits, for search-as-you-type and tap-to-drop-a-pin.
- **Web pages** - landing page, privacy policy, terms, password-reset form, account deletion.

## Quick start (development)

```bash
python -m venv venv && source venv/bin/activate      # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env                                 # defaults work for local dev
python manage.py migrate
python manage.py createsuperuser                     # optional, for /admin/
python manage.py runserver 0.0.0.0:8002
```

- API docs: http://localhost:8002/api/docs/ (enabled when `DEBUG=True`)
- Emails (password reset) are printed to the console until `EMAIL_HOST` is set.
- Point the app at your machine's LAN IP, e.g. `EXPO_PUBLIC_API_URL=http://192.168.1.20:8002`.

Reel analysis needs `GOOGLE_API_KEY` ([get one](https://aistudio.google.com/apikey)). Without it,
sharing a reel still works - the app goes straight to manual place search.

### Tests

```bash
DEBUG=True python manage.py test
```

Every external service (Instagram, Gemini, Photon) is mocked, so tests run offline in about a
second. CI (`.github/workflows/ci.yml`) also runs them on Postgres, validates the OpenAPI schema,
checks for missing migrations, runs Django's production `check --deploy`, and builds the Docker image.

## API

All endpoints are under `/api/v1/`, take and return JSON, and (except where noted) need
`Authorization: Bearer <access token>`. Errors always look like
`{"detail": "Human-readable message", "errors": {...field errors, when relevant}}`.

| Method | Path | |
| --- | --- | --- |
| POST | `auth/register/` | `{name, email, password}` → `{user, tokens}` (no auth) |
| POST | `auth/token/` | `{email, password}` → `{access, refresh, user}` (no auth) |
| POST | `auth/token/refresh/` | `{refresh}` → `{access, refresh}`; the old refresh token is revoked |
| POST | `auth/logout/` | `{refresh}` → 204 (no auth; holding the token is the proof) |
| GET/PATCH | `auth/me/` | read / update `{name, email}` |
| DELETE | `auth/me/` | `{password}` → 204; deletes the account and all its places |
| POST | `auth/change-password/` | `{current_password, new_password}` → `{tokens}` |
| POST | `auth/password-reset/` | `{email}` → always the same response (no auth) |
| GET/POST | `locations/` | list (`?category=&favorite=&visited=&search=&ordering=newest\|oldest\|name\|updated`) / create |
| GET/PATCH/DELETE | `locations/{id}/` | one place (only your own - others' are a 404) |
| POST | `locations/bulk/` | `{locations: [...]}` - save up to 20 at once, all-or-nothing |
| GET | `locations/stats/` | totals, favorites, visited, from Instagram, per category |
| GET | `categories/` | the 12 categories with labels (no auth) |
| POST | `reels/analyze/` | `{url}` → `{status: "found", places}` or `{status: "manual_required", reason}` |
| GET | `geocode/search/?q=&lat=&lon=` | place search, biased toward `lat/lon` |
| GET | `geocode/reverse/?lat=&lon=` | the place at a point (always returns something) |

Also: `GET /healthz/` (database check for your host's health probe).

Rate limits (per user, or per IP when signed out) are set with the `THROTTLE_*` variables; the
defaults are 10/min for login-type endpoints, 30/hour for reel analysis and 60/min for search.

### How reel analysis works

1. The link is canonicalized (`instagram.com/reels/X/?igsh=...` → `https://www.instagram.com/reel/X/`)
   and looked up in `InstagramReelCache`. Results are reused for 30 days; failures for 1 day.
2. yt-dlp reads the caption. It works anonymously for many public reels; Instagram limits
   anonymous access, so for reliability set `INSTAGRAM_YTDLP_COOKIES_FILE` to a `cookies.txt`
   exported from a logged-in Instagram account (use a dedicated account, not your personal one).
3. Gemini (`GEMINI_MODEL`, default `gemini-2.5-flash`) returns structured JSON - name, category,
   city, country, confidence - under a prompt tuned for precision (a wrong pin is worse than a
   missing one). Low-confidence guesses are dropped.
4. Each place is looked up on Photon using its name, city and country.

A reel that can't be read, or names no specific place, returns `manual_required` rather than an
error, and the app moves straight to search.

> Automated access to Instagram may conflict with Instagram's Terms of Use. Keep
> `REEL_ANALYSIS_ENABLED` as a kill switch; turning it off makes every share go to manual search.

## Deploying

The repo ships a production `Dockerfile` (gunicorn, static files served by WhiteNoise,
migrations on start, non-root user, health check), so any container host works - Render,
Railway, Fly.io, Google Cloud Run, a VPS, etc. You need:

1. **Postgres** - set `DATABASE_URL`.
2. **Redis** (recommended; required with more than one instance) - set `REDIS_URL` so rate limits
   are shared between server processes.
3. **Environment** - at minimum:

   ```
   SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(50))">
   ALLOWED_HOSTS=api.yourdomain.com
   PUBLIC_BASE_URL=https://api.yourdomain.com
   NUM_PROXIES=1                  # behind your host's load balancer
   ADMIN_URL=some-hard-to-guess-path/
   EMAIL_HOST=... EMAIL_HOST_USER=... EMAIL_HOST_PASSWORD=...
   DEFAULT_FROM_EMAIL=Memory Map <no-reply@yourdomain.com>
   SUPPORT_EMAIL=support@yourdomain.com
   GOOGLE_API_KEY=...
   ```

   See `.env.example` for everything else. If your platform runs migrations as a separate release
   step, set `RUN_MIGRATIONS=0`.
4. Create an admin user: `python manage.py createsuperuser` (in your host's shell).

To try the production setup locally: `docker compose up --build` (Postgres + Redis + the API on
http://localhost:8000).

### Before going public

- [ ] `DEBUG` is off and `SECRET_KEY` is a fresh random value used nowhere else.
- [ ] HTTPS works on your domain; `https://<domain>/healthz/` returns `{"status": "ok"}`.
- [ ] Password-reset emails arrive (check spam; set up SPF/DKIM for your sending domain).
- [ ] `https://<domain>/privacy/`, `/terms/` and `/delete-account/` read correctly for your
      situation - they're a starting point, not legal advice. Use these URLs in the App Store and
      Play Console listings.
- [ ] Database backups are enabled on your Postgres host.
- [ ] You have your own Photon instance or a commercial Photon-compatible provider if you expect
      heavy traffic (the public `photon.komoot.io` is a shared, best-effort service).
- [ ] Any secret ever committed to this repository's history has been rotated.

## Project layout

```
config/            settings (all configuration via environment variables), URLs, WSGI
apps/users/        registration, login, profile, password flows, account deletion
apps/core/
  models.py        SavedLocation, InstagramReelCache
  categories.py    the category list shared by the database, Gemini prompt and search
  views.py         locations, categories, reel analysis, geocoding, health check
  services/        reels.py (analysis pipeline + cache), geocoding.py (Photon)
  instagram/       yt-dlp caption fetcher, Gemini place extractor
  web_views.py     landing, legal pages, web account deletion, error pages
templates/         web pages and password-reset emails
```
