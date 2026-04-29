import csv
import io
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from flask_restful import Resource
from models import Product, User
from extensions import db

HARDWARE_CATEGORY = 'Hardware & Utilities'


class ProductListResource(Resource):

    def get(self):
        department = request.args.get('department')

        if department == 'hardware':
            products = Product.query.filter(
                Product.category == HARDWARE_CATEGORY
            ).all()
        elif department == 'shop':
            products = Product.query.filter(
                Product.category != HARDWARE_CATEGORY
            ).all()
        else:
            products = Product.query.all()

        return [product.to_dict() for product in products], 200

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        user    = User.query.get(user_id)
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
            stock      = float(request.form.get("stock"))
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
        user_id = int(get_jwt_identity())
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
        user_id = int(get_jwt_identity())
        user    = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        return {"message": "Product deleted"}, 200


# ─────────────────────────────────────────────────────────────────────────────
# CSV BULK UPLOAD
# ─────────────────────────────────────────────────────────────────────────────
class ProductCSVUploadResource(Resource):
    """POST /products/upload-csv — bulk upload products from CSV"""

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        user    = User.query.get(user_id)
        if not user or user.role != 'admin':
            return {"message": "Admin access required."}, 403

        if 'file' not in request.files:
            return {"message": "No file uploaded."}, 400

        file = request.files['file']

        if not file.filename.endswith('.csv'):
            return {"message": "File must be a CSV."}, 400

        try:
            stream = io.StringIO(file.stream.read().decode('utf-8'))
            reader = csv.DictReader(stream)

            added   = []
            skipped = []
            errors  = []

            for i, row in enumerate(reader, start=2):
                try:
                    name       = row.get('name',       '').strip()
                    category   = row.get('category',   '').strip()
                    price      = row.get('price',      '').strip()
                    unit_price = row.get('unit_price', '').strip()
                    stock      = row.get('stock',      '').strip()
                    barcode    = row.get('barcode',    '').strip() or None

                    # ── Validate required fields ──────────────────────────
                    if not name or not category or not price or not unit_price or not stock:
                        errors.append(f"Row {i}: missing required fields — skipped")
                        continue

                    price      = float(price)
                    unit_price = float(unit_price)
                    stock      = int(stock)

                    if price <= 0 or unit_price <= 0 or stock < 0:
                        errors.append(f"Row {i}: invalid price/stock values — skipped")
                        continue

                    # ── Skip duplicate barcodes ───────────────────────────
                    if barcode:
                        existing = Product.query.filter_by(barcode=barcode).first()
                        if existing:
                            skipped.append(
                                f"Row {i}: barcode {barcode} already exists — skipped"
                            )
                            continue

                    # ── Skip duplicate name + category ────────────────────
                    existing_name = Product.query.filter_by(
                        name=name, category=category
                    ).first()
                    if existing_name:
                        skipped.append(
                            f"Row {i}: '{name}' in '{category}' already exists — skipped"
                        )
                        continue

                    product = Product(
                        name       = name,
                        category   = category,
                        price      = price,
                        unit_price = unit_price,
                        stock      = stock,
                        barcode    = barcode,
                        sold_loose = False,
                    )
                    db.session.add(product)
                    added.append(name)

                except (ValueError, KeyError) as e:
                    errors.append(f"Row {i}: {str(e)} — skipped")
                    continue

            db.session.commit()

            return {
                "message": f"Upload complete! {len(added)} products added.",
                "added":   len(added),
                "skipped": len(skipped),
                "errors":  len(errors),
                "details": {
                    "skipped": skipped[:10],
                    "errors":  errors[:10],
                }
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": f"Upload failed: {str(e)}"}, 500