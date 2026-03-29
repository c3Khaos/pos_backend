from dotenv import load_dotenv
load_dotenv() 

from app import app
from extensions import db
from sqlalchemy import text

with app.app_context():
    db.session.execute(text("DELETE FROM alembic_version"))
    db.session.commit()
    print("✅ alembic_version cleared!")