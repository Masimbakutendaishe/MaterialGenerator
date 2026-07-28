from app import create_app
from app.extensions import db
from app.models.user import User

app = create_app()
with app.app_context():
    existing = User.query.filter_by(email="mngara@teemshee.co.za").first()
    if existing:
        print("Already exists:", existing.email)
    else:
        user = User(email="mngara@teemshee.co.za", role="superadmin", organization_id=None, is_active=True)
        user.set_password("Kutendaishe1!")
        db.session.add(user)
        db.session.commit()
        print("Created superadmin:", user.email)
