from app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    if not User.query.filter_by(username="admin").first():
        admin = User(
            username="admin",
            email="chrisshege35@gmail.com",
            password_hash=generate_password_hash("christof")  # hashed, not plaintext
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin user created")
