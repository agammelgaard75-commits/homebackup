# Single application image for the modular Django portal.
FROM python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ARG APP_VERSION=1.0.0
ARG GIT_REVISION=unknown
LABEL org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.revision=$GIT_REVISION
ENV APP_VERSION=$APP_VERSION GIT_REVISION=$GIT_REVISION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies are locked to concrete versions in requirements.txt.
COPY requirements.txt ./
RUN pip install --no-cache-dir pip==26.2.2 \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.12/ensurepip \
    && groupadd --system --gid 10001 portal \
    && useradd --system --uid 10001 --gid portal --home-dir /app portal

COPY --chown=portal:portal . .
# WhiteNoise assets are collected without a database connection.
# No database access is allowed while building the image.
RUN DJANGO_SECRET_KEY=build-only-not-for-production \
    POSTGRES_PASSWORD=build-only-not-for-production \
    DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
    python manage.py collectstatic --noinput \
    && chown -R portal:portal /app/staticfiles

USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "--access-logformat", "%(s)s %(m)s %(D)s", "--error-logfile", "-"]
