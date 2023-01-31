#!/usr/bin/env bash
# exit on error
set -o errexit

poetry install

python3 manage.py collectstatic
python3 manage.py makemigrations
python3 manage.py migrate

echo "Build Complete"