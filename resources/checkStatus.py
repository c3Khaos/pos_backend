from flask_restful import Resource
from models import User

class Status(Resource):
    def get(self):
        user_count = User.query.count()

        if user_count == 0:
            return {'message': 'No users registered', 'has_users': False}, 200
        else:
            return {'message': f'{user_count} users registered', 'has_users': True}, 200


