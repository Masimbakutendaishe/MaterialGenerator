"""One-time script: fetches a suitable background image from Unsplash and saves it as a
static file for the login page. Run once, then discard."""
from app import create_app
from app.services.image_service import fetch_stock_photo

app = create_app()
with app.app_context():
    photo_bytes = fetch_stock_photo("professional training workshop South Africa")
    if photo_bytes:
        with open("app/static/img/login_bg.jpg", "wb") as f:
            f.write(photo_bytes)
        print("Saved to app/static/img/login_bg.jpg")
    else:
        print("No image found or UNSPLASH_ACCESS_KEY not configured — check your .env")