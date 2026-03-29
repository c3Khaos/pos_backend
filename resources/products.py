from flask import request
from flask_restful import Resource
from models import Product
from extensions import db


class ProductListResource(Resource):
    def get(self):
        products = Product.query.all()
        return [product.to_dict() for product in products], 200
    
    def post(self):
        name = request.form.get("name")
        category = request.form.get("category")
        price = request.form.get("price")
        unit_price = request.form.get("unit_price")
        stock = request.form.get("stock")
        


        new_product = Product(
            name = name,
            category =category,
            price = price,
            unit_price = unit_price,
            stock = stock,
          
        )

        db.session.add(new_product)
        db.session.commit()
        return new_product.to_dict(),201