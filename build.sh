#!/usr/bin/env bash
# Render build script
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py test --noinput -v 2
python manage.py migrate --no-input
python manage.py seed_demo
