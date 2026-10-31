"""
Django settings for the Brightloop Subscription Management System.

Everything that differs between machines is read from environment variables
(optionally from a `.env` file) and has a safe local default, so a fresh clone
runs with zero configuration: `python manage.py migrate && python manage.py runserver`.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from django.contrib.messages import constants as messages
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str = "") -> str:
    """Read a string setting from the environment."""
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    """Read a boolean setting ("1", "true", "yes", "on" are truthy)."""
    return env(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-local-dev-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# Apps that make up this product, in dependency order. Each app exposes
# `<app>/urls.py` (mounted at `/<app>/`, except `core` at `/`) and may declare
# navigation entries on its AppConfig (see core/navigation.py).
PROJECT_APPS = [
    "core",
    "accounts",
    "customers",
    "catalog",
    "subscriptions",
    "billing",
    "payments",
    "portal",
    "reports",
    "api",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    *PROJECT_APPS,
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database: SQLite by default, PostgreSQL when DATABASE_URL is set.
# ---------------------------------------------------------------------------
_database_url = env("DATABASE_URL")
if _database_url.startswith(("postgres://", "postgresql://")):
    _parsed = urlparse(_database_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _parsed.path.lstrip("/"),
            "USER": _parsed.username,
            "PASSWORD": _parsed.password,
            "HOST": _parsed.hostname,
            "PORT": _parsed.port or 5432,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                # Better concurrency for a local multi-tab demo.
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;",
                "transaction_mode": "IMMEDIATE",
            },
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# Problem statement: more than eight characters, with an uppercase letter,
# a lowercase letter and a special character.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 9}},
    {"NAME": "accounts.validators.PasswordComplexityValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# Fast password hashing while running the test suite (PBKDF2 is deliberately slow).
if "test" in sys.argv[1:2]:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ---------------------------------------------------------------------------
# Email (password reset links, invoice sending)
# ---------------------------------------------------------------------------
# EMAIL_BACKEND: "outbox" (default: stored in the database and shown under Email outbox,
# works offline), "console" (printed in the terminal) or "smtp" (real delivery, e.g. Brevo).
_email_backend = env("EMAIL_BACKEND", "outbox").strip().lower()
if _email_backend == "smtp":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", "10"))  # seconds; a slow mail server must not hang a page
elif _email_backend == "console":
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "core.mail.OutboxEmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "billing@brightloop.local")

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files (served by Django in DEBUG; vendored libraries live in static/vendor)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Messages -> Bootstrap alert classes
# ---------------------------------------------------------------------------
MESSAGE_TAGS = {
    messages.DEBUG: "secondary",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}

# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# ---------------------------------------------------------------------------
# Product settings
# ---------------------------------------------------------------------------
APP_NAME = env("APP_NAME", "Brightloop")
CURRENCY_SYMBOL = env("CURRENCY_SYMBOL", "₹")
CURRENCY_CODE = env("CURRENCY_CODE", "INR")
PAGINATE_BY = 25

# ---------------------------------------------------------------------------
# Production hardening (only when DEBUG is off)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
if "test" in sys.argv[1:2]:
    # Tests deliberately trigger 403/404 responses; don't print them as tracebacks.
    LOGGING["loggers"] = {"django.request": {"level": "ERROR"}}
