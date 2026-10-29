import os
from pathlib import Path
from urllib.parse import urlparse, unquote
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
# Generated local .env; environment variables always take precedence.
env_path = BASE_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

ENV = os.getenv("HC_ENV", "local")
if ENV not in {"local", "test", "production"}:
    raise ImproperlyConfigured("HC_ENV must be local, test or production")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Run python3 scripts/bootstrap.py to generate local settings.")
DEBUG = False
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",")
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")
ENABLE_DEMO = os.getenv("ENABLE_DEMO", "0") == "1"
WORKER_FAIL_KIND = os.getenv("WORKER_FAIL_KIND", "")
MAX_JOB_ATTEMPTS = int(os.getenv("MAX_JOB_ATTEMPTS", "5"))
RESERVATION_MINUTES = int(os.getenv("RESERVATION_MINUTES", "30"))
WORKER_LEASE_SECONDS = 30
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
    url = urlparse(DATABASE_URL)
    if url.scheme not in {"postgres", "postgresql"} or not url.hostname or not url.path.strip("/"):
        raise ImproperlyConfigured("DATABASE_URL must identify a PostgreSQL database")
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql", "NAME": unquote(url.path.lstrip("/")),
        "USER": unquote(url.username or ""), "PASSWORD": unquote(url.password or ""),
        "HOST": url.hostname, "PORT": str(url.port or 5432),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5, "options": "-c statement_timeout=8000 -c lock_timeout=4000",
                    "sslmode": os.getenv("DB_SSLMODE", "prefer")},
    }}
else:
    if ENV == "production":
        raise ImproperlyConfigured("Production requires PostgreSQL")
    (BASE_DIR / ".local").mkdir(exist_ok=True)
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
                             "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / ".local/harborcart.sqlite3")),
                             "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"}}}

if ENV == "production":
    if WORKER_FAIL_KIND:
        raise ImproperlyConfigured("Failure injection must be disabled in production")
    if len(SECRET_KEY) < 50 or ENABLE_DEMO or not METRICS_TOKEN:
        raise ImproperlyConfigured("Production needs strong secrets, metrics token and demo disabled")
    if "*" in ALLOWED_HOSTS or "testserver" in ALLOWED_HOSTS:
        raise ImproperlyConfigured("Production requires explicit allowed hosts")
    if os.getenv("DB_SSLMODE") != "verify-full":
        raise ImproperlyConfigured("Production requires DB_SSLMODE=verify-full and a trusted CA")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Only enable behind an ingress that strips and sets this header.
    if os.getenv("TRUST_PROXY_HEADERS") == "1":
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes",
                  "django.contrib.sessions", "django.contrib.messages",
                  "django.contrib.staticfiles", "commerce"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware",
              "whitenoise.middleware.WhiteNoiseMiddleware",
              "django.contrib.sessions.middleware.SessionMiddleware",
              "django.middleware.common.CommonMiddleware",
              "django.middleware.csrf.CsrfViewMiddleware",
              "django.contrib.auth.middleware.AuthenticationMiddleware",
              "django.contrib.messages.middleware.MessageMiddleware",
              "django.middleware.clickjacking.XFrameOptionsMiddleware",
              "commerce.middleware.RequestLogMiddleware"]
ROOT_URLCONF = "harbor.urls"
WSGI_APPLICATION = "harbor.wsgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates",
              "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
              "OPTIONS": {"context_processors": [
                  "django.template.context_processors.request",
                  "django.contrib.auth.context_processors.auth",
                  "django.contrib.messages.context_processors.messages",
                  "commerce.context.workspace"]}}]
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / ".static"
STATICFILES_DIRS = [BASE_DIR / "static"]
WHITENOISE_USE_FINDERS = ENV != "production"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536
FILE_UPLOAD_MAX_MEMORY_SIZE = 65536
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "formatters": {"plain": {"format": "%(message)s"}},
           "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
           "loggers": {"harborcart": {"handlers": ["console"], "level": "INFO", "propagate": False}}}
