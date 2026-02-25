from dotenv import load_dotenv
load_dotenv()

from app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
        user1 = User(
            username="chege",
            email="dev.chris@gmail.com",
            password_hash=generate_password_hash("chris")  # hashed, not plaintext
        )
        db.session.add(user1)
        db.session.commit()
        print("User created")
