from dotenv import load_dotenv
load_dotenv()

from app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
        user3 = User(
            username="chris",
            email="chege@gmail.com",
            password_hash=generate_password_hash("chege")  # hashed, not plaintext
        )
        db.session.add(user3)
        db.session.commit()
        print("User created")
