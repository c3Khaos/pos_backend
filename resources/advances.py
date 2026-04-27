from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import CashAdvance, User
from extensions import db
from datetime import datetime, timezone


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


class CashAdvanceListResource(Resource):
    """GET /advances   — list all advances
       POST /advances  — record new advance"""

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())  # 👈 fix
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        department = request.args.get('department')
        status     = request.args.get('status')
        show_all   = request.args.get('all') == 'true'

        query = CashAdvance.query

        if department:
            query = query.filter(CashAdvance.department == department)

        if show_all:
            # Return everything including returned
            if status:
                query = query.filter(CashAdvance.status == status)
        elif status:
            query = query.filter(CashAdvance.status == status)
        else:
            # Default: outstanding only
            query = query.filter(CashAdvance.status.in_(['pending', 'partial']))

        advances = query.order_by(CashAdvance.taken_at.desc()).all()
        return [a.to_dict() for a in advances], 200

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())  # 👈 fix
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        data = request.get_json()

        person_name = data.get('person_name', '').strip()
        amount      = data.get('amount')
        reason      = data.get('reason', '').strip()
        department  = data.get('department', 'shop')

        if not person_name:
            return {"message": "Person name is required."}, 400

        if amount is None:
            return {"message": "Amount is required."}, 400

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"message": "Invalid amount."}, 400

        if amount <= 0:
            return {"message": "Amount must be greater than 0."}, 400

        if department not in ('shop', 'hardware'):
            return {"message": "Department must be 'shop' or 'hardware'."}, 400

        advance = CashAdvance(
            person_name = person_name,
            amount      = amount,
            reason      = reason or None,
            department  = department,
            recorded_by = user_id,
        )
        db.session.add(advance)
        db.session.commit()
        return advance.to_dict(), 201


class CashAdvanceReturnResource(Resource):
    """POST /advances/<id>/return — record a return payment"""

    @jwt_required()
    def post(self, advance_id):
        user_id = int(get_jwt_identity())  # 👈 fix
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        advance = CashAdvance.query.get_or_404(advance_id)
        data    = request.get_json()

        if advance.status == 'returned':
            return {"message": "This advance has already been fully returned."}, 400

        amount_returning = data.get('amount')
        if amount_returning is None:
            return {"message": "Amount is required."}, 400

        try:
            amount_returning = float(amount_returning)
        except (TypeError, ValueError):
            return {"message": "Invalid amount."}, 400

        if amount_returning <= 0:
            return {"message": "Amount must be greater than 0."}, 400

        amount_still_owed = advance.amount - (advance.amount_returned or 0)

        if amount_returning > amount_still_owed:
            return {
                "message": f"Return exceeds amount owed (KSh {amount_still_owed:.2f})."
            }, 400

        try:
            advance.amount_returned = (advance.amount_returned or 0) + amount_returning

            if advance.amount_returned >= advance.amount:
                advance.status      = 'returned'
                advance.returned_at = datetime.now(timezone.utc)
            else:
                advance.status = 'partial'

            db.session.commit()

            return {
                "message":         "Return recorded successfully.",
                "advance":         advance.to_dict(),
                "amount_returned": advance.amount_returned,
                "amount_owed":     advance.amount - advance.amount_returned,
                "status":          advance.status,
            }, 200

        except Exception as e:
            db.session.rollback()
            return {"message": "An error occurred."}, 500


class CashAdvanceSummaryResource(Resource):
    """GET /advances/summary — totals for dashboard"""

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())  # 👈 fix
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        department = request.args.get('department')

        query = CashAdvance.query.filter(
            CashAdvance.status.in_(['pending', 'partial'])
        )

        if department:
            query = query.filter(CashAdvance.department == department)

        outstanding = query.all()

        total_taken    = sum(a.amount for a in outstanding)
        total_returned = sum(a.amount_returned or 0 for a in outstanding)
        total_owed     = total_taken - total_returned
        count          = len(outstanding)

        return {
            "total_taken":    round(total_taken,    2),
            "total_returned": round(total_returned, 2),
            "total_owed":     round(total_owed,     2),
            "count":          count,
        }, 200