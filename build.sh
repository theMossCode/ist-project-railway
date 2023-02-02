#!/usr/bin/env bash
# exit on error
set -o errexit

poetry install

poetry run python3 manage.py collectstatic
poetry run python3 manage.py makemigrations
poetry run python3 manage.py migrate

echo "Build Complete"