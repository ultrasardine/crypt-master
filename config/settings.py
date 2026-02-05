"""
Django settings for crypt-master project.

Automated cryptocurrency trading system with Pionex exchange integration.
Supports PostgreSQL, Redis, and Celery for background tasks.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-key-change-in-production-12345678901234567890",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Application definition
INSTALLED_APPS = [
    "daphne",  # ASGI server for channels
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "rest_framework.authtoken",  # Token authentication for API access
    "corsheaders",
    "channels",
    "django_celery_beat",  # Database-backed periodic task scheduler
    # Local apps
    "apps.core",
    "apps.dashboard",
    "apps.trading",
    "apps.bots",
    "apps.analysis",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Login required middleware for portal authentication
    # Requirements: 8.4, 8.5 - Require authentication for all portal pages
    "lib.multitenancy.middleware.LoginRequiredMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://cryptmaster:cryptmaster@localhost:5432/cryptmaster",
)

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Fallback to SQLite for development if PostgreSQL is not available
if os.environ.get("USE_SQLITE", "False").lower() in ("true", "1", "yes"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Authentication settings
# Requirements:
# - 8.1: Support Django's built-in session authentication for portal access
# - 8.2: Create a session and redirect to the dashboard on login
# - 8.3: Invalidate the session and clear cookies on logout
# - 8.4: Require authentication for all pages except login and registration
# - 8.5: Redirect unauthenticated users to the login page
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"  # Redirect to dashboard after login
LOGOUT_REDIRECT_URL = "/accounts/login/"  # Redirect to login after logout

# URLs exempt from login requirement (used by LoginRequiredMiddleware)
# These paths don't require authentication
LOGIN_EXEMPT_URLS = [
    r"^/accounts/login/?$",
    r"^/accounts/logout/?$",
    r"^/accounts/register/?$",
    r"^/health/?$",
    r"^/api/",  # API uses token authentication
    r"^/admin/",  # Admin has its own authentication
    r"^/static/",  # Static files
    r"^/__debug__/",  # Django debug toolbar
]

# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Redis Configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Django Channels Configuration
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Celery Configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes

# Django REST Framework Configuration
# Requirements:
# - 9.1: Support token-based authentication for API access using TokenAuthentication
# - 9.5: Support both session authentication (for portal) and token authentication (for API)
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")
CORS_ALLOW_CREDENTIALS = True

# Logging Configuration
# Uses the structured logging library for comprehensive logging
# with file rotation, JSON format, and separate log files for
# trading decisions, bot events, and errors.
#
# Requirements:
# - 8.1: Log all trading decisions with full context
# - 8.2: Log order details including symbol, side, type, price, quantity, order ID
# - 8.3: Log errors with full context, stack trace, and recovery action
# - 8.4: Support configurable log levels (DEBUG, INFO, WARNING, ERROR)
# - 8.5: Log configuration parameters and mode at startup
# - 8.6: Persist logs to files with configurable rotation policy
# - 10.11: Log all bot creation, modification, and termination events

# Ensure logs directory exists
(BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

# Log file settings
LOG_DIR = BASE_DIR / "logs"
LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "json": {
            "()": "lib.logging.StructuredFormatter",
            "include_timestamp": True,
            "include_module": True,
            "include_process": False,
            "include_thread": False,
        },
        "json_detailed": {
            "()": "lib.logging.StructuredFormatter",
            "include_timestamp": True,
            "include_module": True,
            "include_process": True,
            "include_thread": True,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "crypt-master.log",
            "maxBytes": LOG_MAX_BYTES,
            "backupCount": LOG_BACKUP_COUNT,
            "formatter": "json",
            "encoding": "utf-8",
        },
        "trading_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "trading.log",
            "maxBytes": LOG_MAX_BYTES,
            "backupCount": LOG_BACKUP_COUNT,
            "formatter": "json",
            "encoding": "utf-8",
        },
        "bot_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "bots.log",
            "maxBytes": LOG_MAX_BYTES,
            "backupCount": LOG_BACKUP_COUNT,
            "formatter": "json",
            "encoding": "utf-8",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "errors.log",
            "maxBytes": LOG_MAX_BYTES,
            "backupCount": LOG_BACKUP_COUNT,
            "formatter": "json_detailed",
            "level": "ERROR",
            "encoding": "utf-8",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file"],
            "level": os.environ.get("APP_LOG_LEVEL", "DEBUG"),
            "propagate": False,
        },
        "agents": {
            "handlers": ["console", "file"],
            "level": os.environ.get("AGENT_LOG_LEVEL", "DEBUG"),
            "propagate": False,
        },
        "trading": {
            "handlers": ["console", "trading_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "bots": {
            "handlers": ["console", "bot_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "system": {
            "handlers": ["console", "file", "error_file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# Pionex API Configuration (loaded from environment)
PIONEX_API_KEY = os.environ.get("PIONEX_API_KEY", "")
PIONEX_API_SECRET = os.environ.get("PIONEX_API_SECRET", "")

# Trading Configuration
DRY_RUN = os.environ.get("DRY_RUN", "True").lower() in ("true", "1", "yes")

# Risk Management Defaults
RISK_MAX_POSITION_PCT = float(os.environ.get("RISK_MAX_POSITION_PCT", "0.10"))
RISK_MAX_PER_TRADE = float(os.environ.get("RISK_MAX_PER_TRADE", "0.02"))
RISK_MAX_DRAWDOWN = float(os.environ.get("RISK_MAX_DRAWDOWN", "0.20"))
RISK_MIN_CONFIDENCE = float(os.environ.get("RISK_MIN_CONFIDENCE", "0.85"))
RISK_BOT_LOSS_THRESHOLD = float(os.environ.get("RISK_BOT_LOSS_THRESHOLD", "0.10"))

# Analysis Configuration
ANALYSIS_INTERVAL_SECONDS = int(os.environ.get("ANALYSIS_INTERVAL_SECONDS", "60"))
RSI_PERIOD = int(os.environ.get("RSI_PERIOD", "14"))
MACD_FAST = int(os.environ.get("MACD_FAST", "12"))
MACD_SLOW = int(os.environ.get("MACD_SLOW", "26"))
MACD_SIGNAL = int(os.environ.get("MACD_SIGNAL", "9"))
BOLLINGER_PERIOD = int(os.environ.get("BOLLINGER_PERIOD", "20"))
BOLLINGER_STD = float(os.environ.get("BOLLINGER_STD", "2.0"))

# Optional LLM Configuration
LLM_ENABLED = os.environ.get("LLM_ENABLED", "False").lower() in ("true", "1", "yes")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
