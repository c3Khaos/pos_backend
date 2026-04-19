from dotenv import load_dotenv
load_dotenv()

from app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    existing = User.query.filter_by(email="chege@gmail.com").first()

    if existing:
        print("Admin already exists")
    else:
        user = User(
            username="chris",
            email="chege@gmail.com",
            password_hash=generate_password_hash("chege"),
            role="admin",   # ← critical
            active=True
        )

        db.session.add(user)
        db.session.commit()
        print("Admin created")
