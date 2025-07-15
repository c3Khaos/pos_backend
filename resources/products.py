from flask import request
from flask_restful import Resource
from models import Product
from extensions import db

class ProductListResource(Resource):
    def get(self):
        products = Product.query.all()
        return [product.to_dict() for product in products], 200
    
    def post(self):
        data = request.get_json()
        
        new_product = Product(
            name = data.get('name'),
            category =data.get('category'),
            price = data.get("price"),
            stock = data.get('stock')
        )

        db.session.add(new_product)
        db.session.commit()
        return new_product.to_dict(),201