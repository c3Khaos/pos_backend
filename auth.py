from flask import request
from flask_restful import Resource
from models import User
from extensions import db
# --- New JWT imports for token creation ---
from flask_jwt_extended import create_access_token, create_refresh_token

class LoginResource(Resource):
    def post(self):
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return {"error": "Username and password are required."}, 408

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            #implement the jwt
            #"identy" is wht you get back after you verify the token ie user.id
            access_token = create_access_token(identity=user.id)
            refresh_token = create_refresh_token(identity = user.id)
            
            #return the token to the frontend
            return {
                "message": "Login successful",
                "access_token":access_token,
                "refresh_token":refresh_token,
                "user": user.to_dict()
             }, 200

        return {"error": "Invalid username or password."}, 401

class RegisterResource(Resource):
    def post(self):
        data = request.get_json()
        if User.query.filter_by(username=data['username']).first():
            return {"error": "Username already exists"}, 402

        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not username or not email or not password:
            return {"error": "All fields are required"}, 403

        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            return {"error": "Username or email already exists"}, 404


        # Default role since no role comes from the front end
        determined_role = 'user' 
        if username.lower() == 'admin':
            determined_role= 'admin'

        # ✅ Create user and set hashed password
        new_user = User(username=username, email=email, role = determined_role)
        new_user.set_password(password)
        try:
            db.session.add(new_user)
            db.session.commit()
            return {"message": "User registered successfully"}, 201
        except Exception as e:
            print("DB Error:", e)
            return {"error": "Server error while creating user"}, 500