#!/usr/bin/env bash
# exit on error
set -o errexit

echo "$(poetry --version)"
curl -sSL https://install.python-poetry.org | python3 - --uninstall
curl -sSL https://install.python-poetry.org | python3 -
poetry self update
#poetry update
#poetry install

python manage.py collectstatic --no-input
python manage.py makemigrations
python manage.py migrate