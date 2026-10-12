web: bash -c "cd backend && python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}"
