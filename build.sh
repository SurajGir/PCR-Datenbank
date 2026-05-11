#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

# These two are the most important right now:
python manage.py migrate --no-input
python manage.py createsuperuser --no-input || true