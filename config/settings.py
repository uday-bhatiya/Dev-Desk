
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    return int(os.environ.get(name, default))


def env_list(name, default=""):
    return [
        item.strip()
        for item in os.environ.get(name, default).split(",")
        if item.strip()
    ]


# --- Core security settings -------------------------------------------------

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = env_bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# --- Applications -----------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "accounts",
    "tickets",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
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
        # Project-level templates folder, shared by all apps.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database (PostgreSQL) --------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# --- Authentication ---------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = ["accounts.backends.ThrottledModelBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"                 
LOGIN_REDIRECT_URL = "ticket_list"   
LOGOUT_REDIRECT_URL = "login"       

# --- Sessions, cookies and request limits -----------------------------------

SESSION_COOKIE_AGE = 60 * 60 * 12   
SESSION_COOKIE_HTTPONLY = True     
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024

# --- Browser-facing security headers ----------------------------------------

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"


HTTPS_ENABLED = env_bool("DJANGO_HTTPS", default=False)

SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SECURE_SSL_REDIRECT = HTTPS_ENABLED

SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 3600) if HTTPS_ENABLED else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False


THROTTLE_TRUST_PROXY_HEADER = False
if env_bool("DJANGO_BEHIND_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    THROTTLE_TRUST_PROXY_HEADER = True

# --- Internationalization ---------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
# Store datetimes as UTC in the database, display in TIME_ZONE.
USE_TZ = True

# --- Static files -----------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]   # our own CSS/JS during development
STATIC_ROOT = BASE_DIR / "staticfiles"     # where collectstatic gathers files for deployment

# --- Logging ----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{asctime} {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "devdesk.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# --- Misc -------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"