from flask import request
from flask_restful import Resource
from models import Product
from extensions import db
import cloudinary.uploader

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
        

        image_url = None
        if "image" in request.files:
           file = request.files["image"]
           if file.filename != "":
                result = cloudinary.uploader.upload(file, folder="pos/products")
                image_url = result["secure_url"]

        new_product = Product(
            name = name,
            category =category,
            price = price,
            unit_price = unit_price,
            stock = stock,
            image_url  = image_url,
        )

        db.session.add(new_product)
        db.session.commit()
        return new_product.to_dict(),201