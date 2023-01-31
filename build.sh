#!/usr/bin/env bash
# exit on error
set -o errexit

p_ver = $(poetry --version)
echo '$p_ver'
poetry self install --sync
poetry self update --dry-run
poetry update
poetry install

python manage.py collectstatic --no-input
python manage.py makemigrations
python manage.py migrate