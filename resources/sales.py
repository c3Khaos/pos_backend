from flask import request, session
from flask_restful import Resource
from models import Sale, User
from extensions import db

class SaleListResource(Resource):
    def get(self):
        sales = Sale.query.all()
        return [sale.to_dict() for sale in sales], 200

    def post(self):
        user_id = session.get('user_id')
        if not user_id:
            return {"error": "Unauthorized. Please log in."}, 401

        data = request.get_json()
        new_sale = Sale(
            product_name=data["product_name"],
            amount=data["amount"],
            user_id=user_id
        )
        db.session.add(new_sale)
        db.session.commit()

        return new_sale.to_dict(), 201