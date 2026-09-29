from decimal import Decimal
from flask import request
from flask_restful import Resource
from models import Expense
from extensions import db
from datetime import datetime, timezone
from flask_jwt_extended import jwt_required
from utils.tenant import get_tenant_id, current_user_and_tenant, is_admin


class ExpenseListResource(Resource):

    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        department = request.args.get('department')
        query = Expense.query.filter_by(tenant_id=tenant_id)
        if department:
            query = query.filter(Expense.department == department)
        expenses = query.order_by(Expense.expense_date.desc()).all()
        return [e.to_dict() for e in expenses], 200

    @jwt_required()
    def post(self):
        user, tenant_id = current_user_and_tenant()
        if not user or not user.role == 'admin':
            return {"message": "Admin access required."}, 403

        data             = request.get_json() or {}
        description      = data.get("description", "").strip()
        amount           = data.get("amount")
        category         = data.get("category", "").strip()
        expense_date_str = data.get("expense_date")
        department       = data.get("department", "shop")

        if not description or amount is None or not category:
            return {"message": "Description, amount and category are required."}, 400

        try:
            amount = Decimal(str(amount))
        except (TypeError, ValueError):
            return {"message": "Amount must be a valid number."}, 400

        if amount <= 0:
            return {"message": "Amount must be greater than zero."}, 400

        expense_date = (
            datetime.fromisoformat(expense_date_str.replace("Z", "+00:00"))
            if expense_date_str
            else datetime.now(timezone.utc)
        )

        expense = Expense(
            tenant_id    = tenant_id,
            description  = description,
            amount       = amount,
            category     = category,
            department   = department,
            expense_date = expense_date,
            recorded_by  = user.id,
        )
        db.session.add(expense)
        db.session.commit()
        return expense.to_dict(), 201


class ExpenseResource(Resource):

    @jwt_required()
    def delete(self, expense_id):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        # ── SECURITY: scope lookup to tenant (IDOR guard) ─────────────────
        expense = Expense.query.filter_by(
            id=expense_id, tenant_id=tenant_id
        ).first()
        if not expense:
            return {"message": "Expense not found."}, 404
        db.session.delete(expense)
        db.session.commit()
        return {"message": "Expense deleted"}, 200