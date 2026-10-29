import os
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-" + "a" * 64)
os.environ.setdefault("HC_ENV", "test")
os.environ.setdefault("METRICS_TOKEN", "test-metrics-token")
from .settings import *
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ENABLE_DEMO = True
METRICS_TOKEN = "test-metrics-token"
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
LOGGING["loggers"]["harborcart"]["level"] = "WARNING"
