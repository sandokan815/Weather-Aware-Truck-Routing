"""
Django settings for the Truck Safe Route Planner API.

The app is stateless (no models, no auth). All provider settings are read from
environment variables / a `.env` file in the backend folder - see `.env.example`.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "routes",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "trip_planner.urls"
WSGI_APPLICATION = "trip_planner.wsgi.application"

# No database is needed - routes, weather and results are computed on the fly.
DATABASES = {}

# In-process cache for geocoding / weather lookups.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "truck-route-planner",
        "TIMEOUT": 60 * 60,
        "OPTIONS": {"MAX_ENTRIES": 5000},
    }
}

USE_TZ = True
TIME_ZONE = "UTC"

# No auth: DRF must not touch django.contrib.auth.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", False)

# ---------------------------------------------------------------------------
# External providers
# ---------------------------------------------------------------------------
HTTP_USER_AGENT = os.getenv(
    "HTTP_USER_AGENT", "TruckSafeRoutePlanner/1.0 (https://github.com/)"
)
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "25"))

# Routing: osrm (default, free) | ors | mapbox | mock
ROUTING_PROVIDER = os.getenv("ROUTING_PROVIDER", "osrm").lower()
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN", "")

# Geocoding: nominatim (default, free) | photon | mapbox
GEOCODING_PROVIDER = os.getenv("GEOCODING_PROVIDER", "nominatim").lower()
NOMINATIM_BASE_URL = os.getenv(
    "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
)
PHOTON_BASE_URL = os.getenv("PHOTON_BASE_URL", "https://photon.komoot.io")
GEOCODE_COUNTRY_CODES = os.getenv("GEOCODE_COUNTRY_CODES", "us,ca,mx")

# Weather: open-meteo (default, free) | mock
WEATHER_PROVIDER = os.getenv("WEATHER_PROVIDER", "open-meteo").lower()
OPEN_METEO_BASE_URL = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com")

# When a real provider fails, fall back to deterministic mock data (flagged in
# the response `warnings`) instead of returning an error.
ALLOW_MOCK_FALLBACK = env_bool("ALLOW_MOCK_FALLBACK", True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    # DEBUG level prints the raw third-party API responses (OSRM, Nominatim, Photon, Open-Meteo).
    "loggers": {"routes": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO"}},
}
