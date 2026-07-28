web: gunicorn wsgi:app --bind 0.0.0.0:$PORT
worker: celery -A celery_worker.celery_app worker --loglevel=info --concurrency=4