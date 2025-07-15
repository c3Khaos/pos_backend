# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager

# These are like specialized tools you'll use throughout your app
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()