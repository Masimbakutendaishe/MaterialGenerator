# Flask entrypoint (gunicorn target)
"""Entrypoint for running the app (flask run, gunicorn, etc.)."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)