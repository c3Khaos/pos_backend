from flask import request
from flask_restful import Resource
from models import User
from extensions import db, limiter
from flask_jwt_extended import create_access_token, create_refresh_token


class LoginResource(Resource):
    @limiter.limit("5 per minute")
    def post(self):
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return {"error": "Username and password are required."}, 400

        user = User.query.filter_by(username=username).first()

        # 1. Check if user exists
        if not user:
            return {"error": "Invalid username or password."}, 401

        # 2. Check if the account is deactivated first so it doesn't bypass to 401
        if not user.active:
            return {"message": "Account deactivated. Contact Admin."}, 403

        # 3. Verify password
        if not user.check_password(password):
            return {"error": "Invalid username or password."}, 401

        # 4. Generate tokens on successful validation
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.role}
        )

        refresh_token = create_refresh_token(identity=str(user.id))

        return {
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict()
        }, 200


class RegisterResource(Resource):
    def post(self):
        data = request.get_json()
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not username or not email or not password:
            return {"error": "All fields are required"}, 400

        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            return {"error": "Username or email already exists"}, 409

        # Default role logic
        determined_role = 'user' 
        if username.lower() == 'admin':
            determined_role = 'admin'

        # Create user and set hashed password
        new_user = User(username=username, email=email, role=determined_role)
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            return {"message": "User registered successfully"}, 201
        except Exception as e:
            db.session.rollback()
            print("DB Error:", e)
            return {"error": "Server error while creating user"}, 500