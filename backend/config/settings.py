"""Django settings. All environment-specific values come from env vars (see .env.example)."""

import os
from pathlib import Path

import dj_database_url
import structlog
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Local (non-Docker) development convenience: read the repo-root .env if present. Real env vars win.
load_dotenv(BASE_DIR.parent / ".env", override=False)

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# Origins (scheme://host[:port]) allowed to make session-authenticated POSTs, e.g. the Vite dev server.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "accounts",
    "core",
]

MIDDLEWARE = [
    # First, so the logged duration covers the whole middleware stack.
    "core.middleware.RequestLogMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default="postgres://requestdesk:requestdesk@localhost:55432/requestdesk",
        conn_max_age=60,
    )
}

AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]

# Session cookie stays HttpOnly (default). The CSRF cookie must be readable by the frontend so it can
# echo it back in the X-CSRFToken header; that is how Django's double-submit CSRF protection works.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = os.environ.get("DJANGO_SECURE_COOKIES", "0") == "1"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# --- Logging -----------------------------------------------------------------
# Everything (our structlog calls and Django's own stdlib logging) goes to stdout as one JSON object per line.

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

_shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]

structlog.configure(
    processors=[*_shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "foreign_pre_chain": _shared_processors,
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        # RequestLogMiddleware already logs every request; keep django.request only for 5xx tracebacks.
        "django.request": {"level": "ERROR"},
        # runserver's own plain-text access log (local dev only) would duplicate that line too.
        "django.server": {"handlers": [], "level": "ERROR", "propagate": False},
    },
}
