# Resolve and pin the digest of this reviewed tag before an approved release.
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm
FROM ${PYTHON_IMAGE} AS build
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN python -m pip install --no-cache-dir --require-hashes --prefix=/install -r requirements.lock
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY --from=build /install /usr/local
COPY --chown=10001:10001 . /app
# Build-only dummy secret: no runtime secrets or database access.
RUN DJANGO_SECRET_KEY=build-only-not-a-runtime-secret HC_ENV=local python manage.py collectstatic --noinput
USER 10001:10001
EXPOSE 8080
CMD ["gunicorn","harbor.wsgi:application","--bind","0.0.0.0:8080","--workers","2","--threads","2","--timeout","30","--graceful-timeout","25","--worker-tmp-dir","/tmp","--access-logfile","-","--error-logfile","-"]
