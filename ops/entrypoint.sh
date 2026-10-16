#!/bin/sh
# Entrypoint web-контейнера: миграции и статика только для gunicorn.
# worker/beat приходят с entrypoint: [] и стартуют напрямую.
set -e

case "${1:-}" in
    gunicorn*)
        python manage.py migrate --noinput
        python manage.py collectstatic --noinput
        ;;
esac

exec "$@"
