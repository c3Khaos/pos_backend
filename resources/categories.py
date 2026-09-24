from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Category, Product, User
from extensions import db
from sqlalchemy import func


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


class CategoryListResource(Resource):
    """
    GET  /categories — list all (any logged-in user)
    POST /categories — add new (admin only)
    """

    @jwt_required()
    def get(self):
        categories = Category.query.order_by(Category.name).all()
        return [c.to_dict() for c in categories], 200

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        data = request.get_json()
        name = (data.get("name") or "").strip()

        if not name:
            return {"message": "Category name is required."}, 400

        existing = Category.query.filter(
            func.lower(Category.name) == name.lower()
        ).first()
        if existing:
            return {"message": f"Category '{name}' already exists."}, 409

        category = Category(name=name)
        db.session.add(category)
        db.session.commit()
        return category.to_dict(), 201


class CategoryResource(Resource):
    """DELETE /categories/<id> — remove (admin only, blocked if in use)"""

    @jwt_required()
    def delete(self, category_id):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        category = Category.query.get_or_404(category_id)

        in_use = Product.query.filter(
            func.lower(Product.category) == category.name.lower()
        ).count()

        if in_use > 0:
            return {
                "message": f"Can't delete — {in_use} product(s) still use "
                           f"'{category.name}'. Reassign them first."
            }, 409

        db.session.delete(category)
        db.session.commit()
        return {"message": f"Category '{category.name}' deleted."}, 200