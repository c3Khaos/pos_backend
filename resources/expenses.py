from flask import request
from flask_restful import Resource
from models import Expense
from extensions import db
from datetime import datetime
from models import User
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt


def admin_required():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if user or user.role == "admin":
            return True
    return False


class ExpenseListResource(Resource):
    @jwt_required()
    def get(self):
        if not admin_required():
            return {"message": "Admin access required."}, 403
        expenses = Expense.query.order_by(Expense.expense_date.desc()).all()
        return [e.to_dict() for e in expenses], 200

    @jwt_required()
    def post(self):
        if not admin_required():
            return {"message": "Admin access required."}, 403

        user_id = get_jwt_identity()
        data = request.get_json()

        description = data.get("description", "").strip()
        amount = data.get("amount")
        category = data.get("category", "").strip()
        expense_date_str = data.get("expense_date")

        if not description or amount is None or not category:
            return {"message": "Description, amount and category are required."}, 400

        if float(amount) <= 0:
            return {"message": "Amount must be greater than zero."}, 400

        expense_date = (
            datetime.fromisoformat(expense_date_str.replace("Z", "+00:00"))
            if expense_date_str else datetime.utcnow()
        )

        expense = Expense(
            description=description,
            amount=float(amount),
            category=category,
            expense_date=expense_date,
            recorded_by=user_id
        )
        db.session.add(expense)
        db.session.commit()
        return expense.to_dict(), 201


class ExpenseResource(Resource):
    @jwt_required()
    def delete(self, expense_id):
        if not admin_required():
            return {"message": "Admin access required."}, 403
        expense = Expense.query.get_or_404(expense_id)
        db.session.delete(expense)
        db.session.commit()
        return {"message": "Expense deleted"}, 200