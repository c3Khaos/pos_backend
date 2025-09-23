from flask_restful import Resource
from models import User

class UsersExist(Resource):
    def get(self):
        user_count = User.query.count()

        return {
            "exists": user_count > 0,
            "count": user_count
        }, 200
