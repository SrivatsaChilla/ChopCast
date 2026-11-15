"""Django settings for the read-only ChopCast dashboard.

The dashboard never imports the ``chopcast`` package and never connects to a
pipeline database for writing. All pipeline locations are resolved by
``adapters.settings.AdapterSettings``; Django's own database is only used if
the optional admin is enabled.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent


def _load_dashboard_env(path: Path) -> None:
    """Load a tiny KEY=VALUE file without overriding the real environment.

    Only ``CHOPCAST_DASHBOARD_*`` keys are accepted. No shell expansion, no
    quotes games beyond a single pair of surrounding quotes. This keeps the
    dashboard independent from the core project's (unread) ``.env``.
    """
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key.startswith("CHOPCAST_DASHBOARD_"):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dashboard_env(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return [part.strip() for part in raw.split(",") if part.strip()]


SECRET_KEY = os.environ.get(
    "CHOPCAST_DASHBOARD_SECRET_KEY",
    "dev-only-insecure-key-change-me-when-exposing-the-dashboard",
)
DEBUG = _env_bool("CHOPCAST_DASHBOARD_DEBUG", False)
ALLOWED_HOSTS = _env_list(
    "CHOPCAST_DASHBOARD_ALLOWED_HOSTS", ["127.0.0.1", "localhost", "testserver"]
)

ENABLE_ADMIN = _env_bool("CHOPCAST_DASHBOARD_ENABLE_ADMIN", False)

INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.pipeline",
    "apps.geo",
]

if ENABLE_ADMIN:
    INSTALLED_APPS = [
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.messages",
        *INSTALLED_APPS,
    ]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.DashboardAdapterMiddleware",
]

if ENABLE_ADMIN:
    MIDDLEWARE.insert(2, "django.contrib.auth.middleware.AuthenticationMiddleware")
    MIDDLEWARE.insert(3, "django.contrib.messages.middleware.MessageMiddleware")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "apps.core.context_processors.dashboard",
            ],
        },
    }
]

# Django's own database. It is never used for pipeline data and is only
# migrated when the optional admin is enabled.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "var" / "dashboard.sqlite3",
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "var" / "static"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = os.environ.get("CHOPCAST_DASHBOARD_TIMEZONE", "UTC")

DASHBOARD_VERSION = "0.1.0"
ADMIN_URL = os.environ.get("CHOPCAST_DASHBOARD_ADMIN_URL", "admin/")

# Conservative security defaults; the dashboard is normally local-only.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
