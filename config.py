import os
from datetime import timedelta

class Config:
     SQLALCHEMY_DATABASE_URI =os.environ.get("DATABASE_URL")
     SQLALCHEMY_TRACK_MODIFICATIONS = False
     #app secret
     SECRET_KEY = os.getenv('SECRET_KEY','dev')
      # JWT configurations
     JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY','another_super_secret_jwt_key') 
    
    # How long the main "access" ID card is valid 
     JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=60)
    
    # How long a "refresh" ID card is valid 
     JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)