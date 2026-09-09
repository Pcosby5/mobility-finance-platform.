#!/usr/bin/env bash
# Render build command: set -euo pipefail makes the deploy fail loudly if any
# step fails, so a broken release never replaces a working one.
set -euo pipefail

echo "==> Installing dependencies"
pip install --no-cache-dir -r requirements/base.txt

echo "==> Applying migrations"
# DATABASE_URL and DJANGO_SECRET_KEY are provided by the Render environment.
python backend/manage.py migrate --noinput

echo "==> Collecting static files"
python backend/manage.py collectstatic --noinput

echo "==> Build complete."
