#!/usr/bin/env bash
# exit on error
set -o errexit

echo "$(poetry --version)"
poetry self install
#poetry self update --dry-run
#poetry update
#poetry install

python manage.py collectstatic --no-input
python manage.py makemigrations
python manage.py migrate