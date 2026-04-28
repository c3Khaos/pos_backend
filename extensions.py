# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["2000 per day","200 per hour"])

# These are like specialized tools you'll use throughout your app
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()