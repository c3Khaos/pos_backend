from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from flask_restful import Resource
from models import Product, User
from extensions import db

HARDWARE_CATEGORY = 'Hardware & Utilities'


class ProductListResource(Resource):

    def get(self):
        department = request.args.get('department')  # 👈 optional filter

        if department == 'hardware':
            # Hardware admin page — only hardware products
            products = Product.query.filter(
                Product.category == HARDWARE_CATEGORY
            ).all()

        elif department == 'shop':
            # Shop admin page — exclude hardware products
            products = Product.query.filter(
                Product.category != HARDWARE_CATEGORY
            ).all()

        else:
            # POS cashier — all products (no filter)
            products = Product.query.all()

        return [product.to_dict() for product in products], 200

    @jwt_required()
    def post(self):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        name       = request.form.get("name",       "").strip()
        category   = request.form.get("category",   "").strip()
        barcode    = request.form.get("barcode",    "").strip()
        sold_loose = request.form.get("sold_loose", "false").lower() == "true"

        if not name or not category:
            return {"message": "Name and category are required."}, 400

        try:
            price      = float(request.form.get("price"))
            unit_price = float(request.form.get("unit_price"))
            stock      = int(request.form.get("stock"))
            if price <= 0 or unit_price <= 0 or stock < 0:
                return {"message": "Price and unit price must be positive. Stock cannot be negative."}, 400
        except (TypeError, ValueError):
            return {"message": "Price, unit price and stock must be valid numbers."}, 400

        if barcode:
            existing = Product.query.filter_by(barcode=barcode).first()
            if existing:
                return {"message": f"A product with barcode {barcode} already exists."}, 409

        new_product = Product(
            name       = name,
            category   = category,
            price      = price,
            unit_price = unit_price,
            stock      = stock,
            barcode    = barcode or None,
            sold_loose = sold_loose
        )
        db.session.add(new_product)
        db.session.commit()
        return new_product.to_dict(), 201


class ProductResource(Resource):

    @jwt_required()
    def patch(self, product_id):
        user_id = get_jwt_identity()
        user    = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        product            = Product.query.get_or_404(product_id)
        data               = request.get_json()
        product.name       = data.get("name",       product.name)
        product.category   = data.get("category",   product.category)
        product.price      = data.get("price",      product.price)
        product.unit_price = data.get("unit_price", product.unit_price)
        product.stock      = data.get("stock",      product.stock)
        product.barcode    = data.get("barcode",    product.barcode)
        if "sold_loose" in data:
            product.sold_loose = data.get("sold_loose")

        db.session.commit()
        return product.to_dict(), 200

    @jwt_required()
    def delete(self, product_id):
        user_id = get_jwt_identity()
        user    = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        return {"message": "Product deleted"}, 200