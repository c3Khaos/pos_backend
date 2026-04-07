from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import db ,User

class UserListResource(Resource):
    @jwt_required()
    def get(self):
        users = User.query.all()
        return[user.to_dict() for user in users],200
    
    @jwt_required
    def post(self):
        data = request.get_json()

        username = data.get('username')
        password = data.get('password') 
        role = data.get('role', 'user')
        active = data.get('active', True)
        email = data.get('email', f"{username}@gmail.com") 

        if not username or not password:
            return {"message": "Username and password are required"}, 400

        if User.query.filter_by(username=username).first():
            return {"message": "User already exists"}, 400

        new_user = User(
            username=username,
            email=email,
            role=role,
            active=active
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        return new_user.to_dict(), 201

class UserResource(Resource):
    @jwt_required()
    def patch(self, user_id):
        # This matches your handleToggle function
        user = User.query.get_or_404(user_id)
        data = request.get_json()

        # If you add an 'active' column to your model:
        if 'active' in data:
            user.active = data['active']
        
        # You can also update roles or emails here if needed
        if 'role' in data:
            user.role = data['role']

        db.session.commit()
        return user.to_dict(), 200

    @jwt_required()
    def delete(self, user_id):
        user = User.query.get_or_404(user_id)
        db.session.delete(user)
        db.session.commit()
        return {"message": "User deleted successfully"}, 200

