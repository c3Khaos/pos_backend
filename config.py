import os
from datetime import timedelta

class Config:
     SQLALCHEMY_DATABASE_URI =os.environ.get("DATABASE_URL")
     SQLALCHEMY_TRACK_MODIFICATIONS = False
     #app secret
     SECRET_KEY = os.getenv('SECRET_KEY','dev')
      # JWT configurations
     JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY') 
     if not JWT_SECRET_KEY:
          raise RecursionError("JWT_SECRET_KEY is not set")
    
    # How long the main "access" ID card is valid 
     JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    
    # How long a "refresh" ID card is valid 
     JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

     cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
     api_key    = os.environ.get('CLOUDINARY_API_KEY')
     api_secret = os.environ.get('CLOUDINARY_API_SECRET')