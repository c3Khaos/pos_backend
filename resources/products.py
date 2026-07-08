import csv
import io
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from flask_restful import Resource
from models import Product, User
from extensions import db


class ProductListResource(Resource):

    def get(self):
        # Single shop — no department filtering needed
        products = Product.query.all()
        return [product.to_dict() for product in products], 200

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        user    = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        name            = request.form.get("name",            "").strip()
        category        = request.form.get("category",        "").strip()
        barcode         = request.form.get("barcode",         "").strip()
        sold_loose      = request.form.get("sold_loose",      "false").lower() == "true"
        wholesale_price = request.form.get("wholesale_price", "").strip()
        carton_qty      = request.form.get("carton_qty",      "").strip()

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

        parsed_wholesale = None
        parsed_carton    = None

        if wholesale_price:
            try:
                parsed_wholesale = float(wholesale_price)
                if parsed_wholesale <= 0:
                    return {"message": "Wholesale price must be positive."}, 400
            except ValueError:
                return {"message": "Invalid wholesale price."}, 400

        if carton_qty:
            try:
                parsed_carton = int(carton_qty)
                if parsed_carton <= 0:
                    return {"message": "Carton quantity must be greater than 0."}, 400
            except ValueError:
                return {"message": "Invalid carton quantity."}, 400

        if barcode:
            existing = Product.query.filter_by(barcode=barcode).first()
            if existing:
                return {"message": f"A product with barcode {barcode} already exists."}, 409

        new_product = Product(
            name            = name,
            category        = category,
            price           = price,
            unit_price      = unit_price,
            wholesale_price = parsed_wholesale,
            carton_qty      = parsed_carton,
            stock           = stock,
            barcode         = barcode or None,
            sold_loose      = sold_loose,
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

        product = Product.query.get_or_404(product_id)
        data    = request.get_json()

        product.name            = data.get("name",            product.name)
        product.category        = data.get("category",        product.category)
        product.price           = data.get("price",           product.price)
        product.unit_price      = data.get("unit_price",      product.unit_price)
        product.wholesale_price = data.get("wholesale_price", product.wholesale_price)
        product.carton_qty      = data.get("carton_qty",      product.carton_qty)
        product.stock           = data.get("stock",           product.stock)
        product.barcode         = data.get("barcode",         product.barcode)
        if "sold_loose" in data:
            product.sold_loose  = data.get("sold_loose")

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


class ProductCSVUploadResource(Resource):
    """POST /products/upload-csv — bulk upload products from CSV"""

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user or user.role != 'admin':
            return {"message": "Admin access required."}, 403

        if 'file' not in request.files:
            return {"message": "No file uploaded."}, 400

        file = request.files['file']

        if not file.filename.endswith('.csv'):
            return {"message": "File must be a CSV."}, 400

        try:
            # Stream the file lines instead of loading everything raw at once
            stream = io.StringIO(file.stream.read().decode('utf-8'))
            reader = csv.DictReader(stream)

            # --- OPTIMIZATION: Cache existing database entries into memory sets ---
            # This turns 2 database calls per CSV row into simple, fast RAM lookups.
            existing_products = db.session.query(Product.name, Product.category, Product.barcode).all()
            
            existing_barcodes = {p.barcode for p in existing_products if p.barcode}
            existing_combos = {(p.name, p.category) for p in existing_products}
            # ----------------------------------------------------------------------

            added_count = 0
            skipped = []
            errors = []
            
            batch_size = 500
            current_batch = []

            for i, row in enumerate(reader, start=2):
                try:
                    name = row.get('name', '').strip()
                    category = row.get('category', '').strip()
                    price = row.get('price', '').strip()
                    unit_price = row.get('unit_price', '').strip()
                    stock = row.get('stock', '').strip()
                    barcode = row.get('barcode', '').strip() or None
                    wholesale_price = row.get('wholesale_price', '').strip() or None
                    carton_qty = row.get('carton_qty', '').strip() or None

                    if not name or not category or not price or not unit_price or not stock:
                        errors.append(f"Row {i}: missing required fields — skipped")
                        current_batch = []  # Clear tracking
                        continue

                    price = float(price)
                    unit_price = float(unit_price)
                    stock = int(stock)

                    if price <= 0 or unit_price <= 0 or stock < 0:
                        errors.append(f"Row {i}: invalid price/stock values — skipped")
                        continue

                    parsed_wholesale = float(wholesale_price) if wholesale_price else None
                    parsed_carton = int(carton_qty) if carton_qty else None

                    # Fast RAM duplicate checking
                    if barcode and barcode in existing_barcodes:
                        skipped.append(f"Row {i}: barcode {barcode} already exists — skipped")
                        continue

                    if (name, category) in existing_combos:
                        skipped.append(f"Row {i}: '{name}' in '{category}' already exists — skipped")
                        continue

                    # Prep object instantiation mapping
                    product = Product(
                        name=name,
                        category=category,
                        price=price,
                        unit_price=unit_price,
                        wholesale_price=parsed_wholesale,
                        carton_qty=parsed_carton,
                        stock=stock,
                        barcode=barcode,
                        sold_loose=False,
                    )
                    
                    db.session.add(product)
                    
                    # Track newly added elements for subsequent duplicate lines within the same CSV
                    if barcode:
                        existing_barcodes.add(barcode)
                    existing_combos.add((name, category))
                    
                    added_count += 1
                    current_batch.append(product)

                    # Periodically flush data to DB to keep RAM usage low
                    if len(current_batch) >= batch_size:
                        db.session.commit()
                        current_batch = []

                except (ValueError, KeyError) as e:
                    errors.append(f"Row {i}: {str(e)} — skipped")
                    continue

            # Final commit for remaining rows
            if current_batch:
                db.session.commit()

            return {
                "message": f"Upload complete! {added_count} products added.",
                "added": added_count,
                "skipped": len(skipped),
                "errors": len(errors),
                "details": {
                    "skipped": skipped[:10],
                    "errors": errors[:10],
                }
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": f"Upload failed: {str(e)}"}, 500