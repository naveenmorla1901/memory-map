# Memory Map backend

Django + Django REST Framework API for the [memory-map-v0](https://github.com/naveenmorla1901/memory-map-v0)
mobile app: user accounts (JWT auth) and saved locations.

## Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv venv
   source venv/bin/activate  # venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in `SECRET_KEY`. `GOOGLE_API_KEY` and
   `INSTAGRAM_OEMBED_ACCESS_TOKEN` are optional and only affect the Instagram-reel
   location-extraction endpoints (auth and saved locations work fully without them):

   ```bash
   cp .env.example .env
   ```

   - `GOOGLE_API_KEY`: a [Gemini API key](https://aistudio.google.com/apikey) - used to pull
     structured location data out of a reel's caption once we have it.
   - `INSTAGRAM_OEMBED_ACCESS_TOKEN`: without this, reading a reel's caption at all almost always
     fails - Instagram blocks unauthenticated scraping. The reliable path is a Meta developer app
     with the "oEmbed Read" permission (requires [App Review](https://developers.facebook.com/docs/app-review)),
     giving you an access token as `{app-id}|{client-token}`. Until you set this up,
     `/api/v1/analyze-reel/` and `/api/v1/analyze-save-reel/` will just respond with
     `{"status": "manual_required", ...}` instead of extracted locations - by design, so the app
     falls back to letting the user pick the location themselves rather than erroring.

3. Run migrations and start the server:

   ```bash
   python manage.py migrate
   python manage.py runserver 0.0.0.0:8002
   ```

4. (Optional) Create an admin user for `/admin/`:

   ```bash
   python manage.py createsuperuser
   ```

The API is served under `/api/v1/`:
- `POST /api/v1/auth/register/`, `POST /api/v1/auth/token/`, `POST /api/v1/auth/token/refresh/`,
  `GET /api/v1/auth/me/`, `POST /api/v1/auth/change-password/`, `POST /api/v1/auth/logout/`
- `GET/POST /api/v1/locations/`, `GET/PATCH/DELETE /api/v1/locations/{id}/`
- `GET/POST /api/v1/user-locations/`, `GET/PATCH/DELETE /api/v1/user-locations/{id}/`,
  `GET /api/v1/user-locations/favorites/`
- `POST /api/v1/analyze-reel/`, `POST /api/v1/analyze-save-reel/`

Interactive docs: `/swagger/` or `/redoc/`.

`0.0.0.0:8002` (rather than the `127.0.0.1` default) matters if you're testing against the mobile
app on a real device or the Android emulator - see the frontend repo's README for pointing the
app at this server.

## Tests

```bash
python manage.py test
```
